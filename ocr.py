"""
ebook-ocr-batch: eBook 스크린샷 → Searchable PDF / 텍스트 자동 변환기
Google Cloud Vision API를 사용하여 캡처한 eBook 이미지를 OCR 처리합니다.
한국어 + 영어 혼용 텍스트를 자동 인식합니다.
"""

import argparse
import io
import os
import re
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from google.cloud import vision
except ImportError:
    print("❌ google-cloud-vision 패키지가 설치되지 않았습니다.")
    print("   pip install google-cloud-vision")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("❌ Pillow 패키지가 설치되지 않았습니다.")
    print("   pip install Pillow")
    sys.exit(1)

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
except ImportError:
    print("❌ reportlab 패키지가 설치되지 않았습니다.")
    print("   pip install reportlab")
    sys.exit(1)

try:
    from PyPDF2 import PdfWriter, PdfReader
except ImportError:
    try:
        from pypdf import PdfWriter, PdfReader
    except ImportError:
        print("❌ PyPDF2 또는 pypdf 패키지가 설치되지 않았습니다.")
        print("   pip install pypdf")
        sys.exit(1)


# ─────────────────────────────────────────────
# OCR 함수
# ─────────────────────────────────────────────

def ocr_single_image(client: vision.ImageAnnotatorClient, image_path: Path):
    """단일 이미지를 OCR 처리하여 full API response를 반환합니다."""
    with open(image_path, "rb") as f:
        content = f.read()

    image = vision.Image(content=content)

    response = client.document_text_detection(
        image=image,
        image_context=vision.ImageContext(
            language_hints=["ko", "en"]
        ),
    )

    if response.error.message:
        raise Exception(f"API 오류 ({image_path.name}): {response.error.message}")

    return response


def get_plain_text(response) -> str:
    """API 응답에서 전체 텍스트만 추출합니다."""
    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text
    return ""


def get_word_boxes(response) -> list[dict]:
    """
    API 응답에서 단어별 텍스트 + 바운딩 박스 좌표를 추출합니다.
    반환: [{"text": "단어", "x": 좌상단X, "y": 좌상단Y, "w": 너비, "h": 높이}, ...]
    """
    words = []
    if not response.full_text_annotation:
        return words

    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = "".join([s.text for s in word.symbols])
                    vertices = word.bounding_box.vertices
                    xs = [v.x for v in vertices]
                    ys = [v.y for v in vertices]
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    words.append({
                        "text": text,
                        "x": x_min,
                        "y": y_min,
                        "w": x_max - x_min,
                        "h": y_max - y_min,
                    })
    return words


# ─────────────────────────────────────────────
# Searchable PDF 생성
# ─────────────────────────────────────────────

def create_searchable_pdf(
    image_files: list[Path],
    ocr_results: dict[int, dict],
    output_path: Path,
):
    """
    이미지 + OCR 결과를 합쳐서 Searchable PDF를 생성합니다.
    각 페이지: 원본 이미지(배경) + 투명 텍스트 레이어(선택/검색용)
    """
    # 한국어 지원을 위한 CID 폰트 등록
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    korean_font = "HYSMyeongJo-Medium"

    writer = PdfWriter()
    total = len(ocr_results)

    print(f"\n📄 Searchable PDF 생성 중... ({total}페이지)")

    for idx in sorted(ocr_results.keys()):
        data = ocr_results[idx]
        img_path = data["image_path"]
        word_boxes = data["word_boxes"]
        img_width = data["img_width"]
        img_height = data["img_height"]

        # ── 1) 이미지 레이어 PDF ──
        img_buf = io.BytesIO()
        img_canvas = canvas.Canvas(img_buf, pagesize=(img_width, img_height))
        img_canvas.drawImage(
            str(img_path), 0, 0, width=img_width, height=img_height
        )
        img_canvas.showPage()
        img_canvas.save()
        img_buf.seek(0)
        img_page = PdfReader(img_buf).pages[0]

        # ── 2) 투명 텍스트 레이어 PDF ──
        txt_buf = io.BytesIO()
        txt_canvas = canvas.Canvas(txt_buf, pagesize=(img_width, img_height))
        txt_canvas.setFillAlpha(0)  # 완전 투명

        for word in word_boxes:
            text = word["text"]
            x = word["x"]
            # Vision API는 좌상단 기준, PDF는 좌하단 기준 → Y 좌표 반전
            y = img_height - word["y"] - word["h"]
            w = word["w"]
            h = word["h"]

            if not text.strip() or w <= 0 or h <= 0:
                continue

            # 글자 크기를 바운딩 박스 높이에 맞춤
            font_size = max(h * 0.85, 4)

            txt_canvas.setFont(korean_font, font_size)

            # 텍스트 너비를 바운딩 박스에 맞춰 수평 스케일 조정
            reported_width = txt_canvas.stringWidth(text, korean_font, font_size)
            if reported_width > 0:
                h_scale = (w / reported_width) * 100
            else:
                h_scale = 100

            txt_canvas.saveState()
            txt_canvas.translate(x, y)
            txt_canvas.setHorizScale(h_scale)
            txt_canvas.drawString(0, 0, text)
            txt_canvas.restoreState()

        txt_canvas.showPage()
        txt_canvas.save()
        txt_buf.seek(0)
        txt_page = PdfReader(txt_buf).pages[0]

        # ── 3) 이미지 위에 텍스트 레이어 병합 ──
        img_page.merge_page(txt_page)
        writer.add_page(img_page)

        # 진행률
        done = list(sorted(ocr_results.keys())).index(idx) + 1
        print(f"  📄 [{done}/{total}] {img_path.name}", end="\r")

    # PDF 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n\n✅ Searchable PDF 저장 완료: {output_path}")
    print(f"   📦 파일 크기: {file_size_mb:.1f} MB")


# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────

def get_image_files(input_dir: Path) -> list[Path]:
    """지원되는 이미지 파일 목록을 정렬된 순서로 반환합니다."""
    supported_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
    files = [
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]
    files.sort(key=lambda f: natural_sort_key(f.stem))
    return files


def natural_sort_key(text: str):
    """자연 정렬 키 (숫자를 올바르게 정렬)."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", text)
    ]


# ─────────────────────────────────────────────
# 메인 처리
# ─────────────────────────────────────────────

def process_batch(
    image_files: list[Path],
    output_dir: Path,
    merge: bool = False,
    merge_filename: str = "merged_output.txt",
    pdf: bool = False,
    pdf_name: str = "output.pdf",
    max_workers: int = 4,
    delay: float = 0.1,
):
    """이미지 배치를 OCR 처리합니다."""
    client = vision.ImageAnnotatorClient()
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(image_files)
    # OCR 결과 저장: {idx: {"image_path", "text", "word_boxes", "img_width", "img_height"}}
    results: dict[int, dict] = {}
    failed: list[tuple[Path, str]] = []

    print(f"\n📚 총 {total}개 이미지 OCR 시작")
    print(f"📂 입력: {image_files[0].parent}")
    print(f"📁 출력: {output_dir}")
    if pdf:
        print(f"📄 PDF: {pdf_name}")
    print(f"⚙️  동시 처리: {max_workers}개 스레드")
    print(f"{'─' * 50}")

    start_time = time.time()
    completed = 0

    def process_one(idx: int, img_path: Path):
        """단일 이미지 처리 (스레드에서 실행)."""
        try:
            response = ocr_single_image(client, img_path)
            text = get_plain_text(response)
            word_boxes = get_word_boxes(response) if pdf else []

            # 이미지 크기 읽기
            with Image.open(img_path) as img:
                img_width, img_height = img.size

            time.sleep(delay)
            return (idx, img_path, text, word_boxes, img_width, img_height, None)
        except Exception as e:
            return (idx, img_path, "", [], 0, 0, str(e))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_one, idx, img): idx
            for idx, img in enumerate(image_files)
        }

        for future in as_completed(futures):
            idx, img_path, text, word_boxes, w, h, error = future.result()
            completed += 1

            if error:
                failed.append((img_path, error))
                status = "❌"
            else:
                results[idx] = {
                    "image_path": img_path,
                    "text": text,
                    "word_boxes": word_boxes,
                    "img_width": w,
                    "img_height": h,
                }
                # 개별 텍스트 파일 저장
                if not merge and not pdf:
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

    # 텍스트 병합 모드
    if merge:
        merged_path = output_dir / merge_filename
        with open(merged_path, "w", encoding="utf-8") as f:
            for idx in sorted(results.keys()):
                data = results[idx]
                f.write(f"{'=' * 60}\n")
                f.write(f"📄 Page {idx + 1} ({data['image_path'].name})\n")
                f.write(f"{'=' * 60}\n\n")
                f.write(data["text"])
                f.write("\n\n")
        print(f"\n📝 병합 텍스트 저장: {merged_path}")

    # Searchable PDF 생성
    if pdf:
        pdf_path = output_dir / pdf_name
        create_searchable_pdf(image_files, results, pdf_path)

    # 결과 요약
    elapsed_total = time.time() - start_time
    print(f"\n{'═' * 50}")
    print(f"✅ 완료: {len(results)}개 성공")
    if failed:
        print(f"❌ 실패: {len(failed)}개")
        for fpath, err in failed:
            print(f"   - {fpath.name}: {err}")
    print(f"⏱️  총 소요시간: {elapsed_total:.1f}초 ({elapsed_total / 60:.1f}분)")
    if elapsed_total > 0:
        print(f"📊 평균 처리속도: {len(results) / elapsed_total:.1f}장/초")
    print(f"{'═' * 50}")

    return results, failed


def main():
    parser = argparse.ArgumentParser(
        description="📚 eBook 스크린샷 → Searchable PDF / 텍스트 변환기 (Google Cloud Vision OCR)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # ⭐ Searchable PDF 생성 (텍스트 선택/검색 가능)
  python ocr.py ./screenshots --pdf --pdf-name "AWS_SAA_C03.pdf"

  # 개별 텍스트 파일로 저장
  python ocr.py ./screenshots

  # 하나의 텍스트 파일로 병합
  python ocr.py ./screenshots --merge --merge-name "AWS_SAA_C03.txt"

  # PDF + 텍스트 동시 생성
  python ocr.py ./screenshots --pdf --merge

  # 동시 처리 스레드 수 조절 (기본: 4)
  python ocr.py ./screenshots --pdf --workers 2
        """,
    )

    parser.add_argument(
        "input_dir",
        type=str,
        help="스크린샷 이미지가 들어있는 폴더 경로",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=None,
        help="결과 저장 폴더 (기본: <input_dir>/ocr_output)",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Searchable PDF 생성 (이미지 + 투명 텍스트 레이어)",
    )
    parser.add_argument(
        "--pdf-name",
        type=str,
        default="output.pdf",
        help="PDF 파일명 (기본: output.pdf)",
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
        help="동시 처리 스레드 수 (기본: 4)",
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

    # --pdf도 --merge도 없으면 기본 개별 txt
    if not args.pdf and not args.merge:
        print("💡 모드가 지정되지 않았습니다. 개별 텍스트 파일로 저장합니다.")
        print("   Searchable PDF를 원하시면: --pdf")
        print("   텍스트 병합을 원하시면:    --merge")

    print(f"\n🔍 발견된 이미지: {len(image_files)}개")
    print(f"   첫 번째: {image_files[0].name}")
    print(f"   마지막:  {image_files[-1].name}")

    process_batch(
        image_files=image_files,
        output_dir=output_dir,
        merge=args.merge,
        merge_filename=args.merge_name,
        pdf=args.pdf,
        pdf_name=args.pdf_name,
        max_workers=args.workers,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
