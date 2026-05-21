"""
ebook-ocr-batch: eBook 스크린샷 → 텍스트 자동 변환기
Google Cloud Vision API를 사용하여 캡처한 eBook 이미지를 OCR 처리합니다.
한국어 + 영어 혼용 텍스트를 자동 인식합니다.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from google.cloud import vision
except ImportError:
    print("❌ google-cloud-vision 패키지가 설치되지 않았습니다.")
    print("   다음 명령어로 설치하세요: pip install google-cloud-vision")
    sys.exit(1)


def ocr_single_image(client: vision.ImageAnnotatorClient, image_path: Path) -> str:
    """단일 이미지를 OCR 처리하여 텍스트를 반환합니다."""
    with open(image_path, "rb") as f:
        content = f.read()

    image = vision.Image(content=content)

    # document_text_detection: 밀집된 텍스트(책, 문서)에 최적화
    response = client.document_text_detection(
        image=image,
        image_context=vision.ImageContext(
            language_hints=["ko", "en"]  # 한국어 + 영어 혼용 힌트
        ),
    )

    if response.error.message:
        raise Exception(f"API 오류 ({image_path.name}): {response.error.message}")

    return response.full_text_annotation.text if response.full_text_annotation.text else ""


def get_image_files(input_dir: Path) -> list[Path]:
    """지원되는 이미지 파일 목록을 정렬된 순서로 반환합니다."""
    supported_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
    files = [
        f
        for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]
    # 파일명 기준 자연 정렬 (page_1, page_2, ... page_10 순서 보장)
    files.sort(key=lambda f: natural_sort_key(f.stem))
    return files


def natural_sort_key(text: str):
    """자연 정렬 키 (숫자를 올바르게 정렬)."""
    import re
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", text)
    ]


def process_batch(
    image_files: list[Path],
    output_dir: Path,
    merge: bool = False,
    merge_filename: str = "merged_output.txt",
    max_workers: int = 4,
    delay: float = 0.1,
):
    """이미지 배치를 OCR 처리합니다."""
    client = vision.ImageAnnotatorClient()
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(image_files)
    results: dict[int, tuple[Path, str]] = {}
    failed: list[tuple[Path, str]] = []

    print(f"\n📚 총 {total}개 이미지 OCR 시작")
    print(f"📂 입력: {image_files[0].parent}")
    print(f"📁 출력: {output_dir}")
    print(f"⚙️  동시 처리: {max_workers}개 스레드")
    print(f"{'─' * 50}")

    start_time = time.time()
    completed = 0

    def process_one(idx: int, img_path: Path) -> tuple[int, Path, str, str | None]:
        """단일 이미지 처리 (스레드에서 실행)."""
        try:
            text = ocr_single_image(client, img_path)
            time.sleep(delay)  # API rate limit 방지
            return (idx, img_path, text, None)
        except Exception as e:
            return (idx, img_path, "", str(e))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_one, idx, img): idx
            for idx, img in enumerate(image_files)
        }

        for future in as_completed(futures):
            idx, img_path, text, error = future.result()
            completed += 1

            if error:
                failed.append((img_path, error))
                status = "❌"
            else:
                results[idx] = (img_path, text)
                # 개별 텍스트 파일 저장
                if not merge:
                    txt_path = output_dir / f"{img_path.stem}.txt"
                    txt_path.write_text(text, encoding="utf-8")
                status = "✅"

            elapsed = time.time() - start_time
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (total - completed) / rate if rate > 0 else 0
            print(
                f"  {status} [{completed:>{len(str(total))}}/{total}] "
                f"{img_path.name:<30} "
                f"({elapsed:.0f}s / ETA {eta:.0f}s)"
            )

    # 병합 모드: 페이지 순서대로 하나의 파일에 합치기
    if merge:
        merged_path = output_dir / merge_filename
        with open(merged_path, "w", encoding="utf-8") as f:
            for idx in sorted(results.keys()):
                img_path, text = results[idx]
                f.write(f"{'=' * 60}\n")
                f.write(f"📄 Page {idx + 1} ({img_path.name})\n")
                f.write(f"{'=' * 60}\n\n")
                f.write(text)
                f.write("\n\n")
        print(f"\n📝 병합 파일 저장: {merged_path}")

    # 결과 요약
    elapsed_total = time.time() - start_time
    print(f"\n{'═' * 50}")
    print(f"✅ 완료: {len(results)}개 성공")
    if failed:
        print(f"❌ 실패: {len(failed)}개")
        for fpath, err in failed:
            print(f"   - {fpath.name}: {err}")
    print(f"⏱️  총 소요시간: {elapsed_total:.1f}초 ({elapsed_total / 60:.1f}분)")
    print(f"📊 평균 처리속도: {len(results) / elapsed_total:.1f}장/초")
    print(f"{'═' * 50}")

    return results, failed


def main():
    parser = argparse.ArgumentParser(
        description="📚 eBook 스크린샷 → 텍스트 변환기 (Google Cloud Vision OCR)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 개별 텍스트 파일로 저장 (이미지 1개 = 텍스트 1개)
  python ocr.py ./screenshots

  # 하나의 파일로 병합
  python ocr.py ./screenshots --merge

  # 출력 폴더 지정 + 병합 파일명 지정
  python ocr.py ./screenshots -o ./output --merge --merge-name "AWS_SAA_C03.txt"

  # 동시 처리 스레드 수 조절 (기본: 4)
  python ocr.py ./screenshots --workers 2
        """,
    )

    parser.add_argument(
        "input_dir",
        type=str,
        help="스크린샷 이미지가 들어있는 폴더 경로",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=None,
        help="OCR 결과 텍스트 저장 폴더 (기본: <input_dir>/ocr_output)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="모든 페이지를 하나의 텍스트 파일로 병합",
    )
    parser.add_argument(
        "--merge-name",
        type=str,
        default="merged_output.txt",
        help="병합 파일명 (기본: merged_output.txt)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="동시 처리 스레드 수 (기본: 4, API 무료 한도 고려 시 2 권장)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="API 호출 간 대기 시간(초) (기본: 0.1)",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    if not input_dir.is_dir():
        print(f"❌ 입력 폴더를 찾을 수 없습니다: {input_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_dir / "ocr_output"

    # 환경 변수 확인
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("⚠️  GOOGLE_APPLICATION_CREDENTIALS 환경 변수가 설정되지 않았습니다.")
        print("   서비스 계정 키 JSON 파일 경로를 설정해주세요:")
        print('   set GOOGLE_APPLICATION_CREDENTIALS="path/to/key.json"')
        print()
        print("   또는 gcloud CLI로 인증하세요:")
        print("   gcloud auth application-default login")
        sys.exit(1)

    image_files = get_image_files(input_dir)
    if not image_files:
        print(f"❌ 이미지 파일을 찾을 수 없습니다: {input_dir}")
        print("   지원 형식: PNG, JPG, JPEG, BMP, TIFF, WEBP")
        sys.exit(1)

    print(f"\n🔍 발견된 이미지: {len(image_files)}개")
    print(f"   첫 번째: {image_files[0].name}")
    print(f"   마지막:  {image_files[-1].name}")

    process_batch(
        image_files=image_files,
        output_dir=output_dir,
        merge=args.merge,
        merge_filename=args.merge_name,
        max_workers=args.workers,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
