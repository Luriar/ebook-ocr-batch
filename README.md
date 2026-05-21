# 📚 ebook-ocr-batch

eBook 스크린샷을 Google Cloud Vision API로 OCR 처리하여 텍스트로 변환하는 도구입니다.

## ✨ 특징

- **한국어 + 영어 혼용** 자동 인식 (AWS 전문 용어 등)
- **`document_text_detection`** 사용 — 밀집 텍스트(책/문서)에 최적화된 OCR
- **멀티스레드** 병렬 처리로 빠른 변환
- **자연 정렬** — `page_1, page_2, ... page_10` 순서 보장
- **개별 저장** 또는 **하나의 파일로 병합** 선택 가능
- 실시간 진행률 표시 (ETA 포함)

## 🛠️ 사전 준비

### 1. Google Cloud Vision API 활성화

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성합니다.
2. **Cloud Vision API**를 활성화합니다.
3. **서비스 계정 키**(JSON)를 발급받아 다운로드합니다.
4. 환경 변수를 설정합니다:

```powershell
# Windows (PowerShell)
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\your-key.json"

# 영구 설정 (시스템 환경변수)
[System.Environment]::SetEnvironmentVariable("GOOGLE_APPLICATION_CREDENTIALS", "C:\path\to\your-key.json", "User")
```

> **💰 비용**: 월 **1,000건 무료**. 595페이지 책 한 권은 무료 한도 안에 들어갑니다.

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

## 🚀 사용법

### 기본 사용 (개별 텍스트 파일로 저장)

```bash
python ocr.py ./screenshots
```

이미지 1개당 텍스트 파일 1개가 `./screenshots/ocr_output/` 폴더에 생성됩니다.

### 하나의 파일로 병합

```bash
python ocr.py ./screenshots --merge --merge-name "AWS_SAA_C03.txt"
```

모든 페이지가 순서대로 하나의 텍스트 파일에 합쳐집니다.

### 출력 폴더 지정

```bash
python ocr.py ./screenshots -o ./output
```

### 전체 옵션

```
python ocr.py --help

사용 예시:
  # 개별 텍스트 파일로 저장 (이미지 1개 = 텍스트 1개)
  python ocr.py ./screenshots

  # 하나의 파일로 병합
  python ocr.py ./screenshots --merge

  # 출력 폴더 지정 + 병합 파일명 지정
  python ocr.py ./screenshots -o ./output --merge --merge-name "AWS_SAA_C03.txt"

  # 동시 처리 스레드 수 조절 (기본: 4)
  python ocr.py ./screenshots --workers 2
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `input_dir` | 스크린샷 이미지 폴더 경로 | (필수) |
| `-o, --output-dir` | OCR 결과 저장 폴더 | `<input_dir>/ocr_output` |
| `--merge` | 모든 페이지를 하나의 파일로 병합 | `false` |
| `--merge-name` | 병합 파일명 | `merged_output.txt` |
| `--workers` | 동시 처리 스레드 수 | `4` |
| `--delay` | API 호출 간 대기(초) | `0.1` |

## 📁 지원 이미지 형식

PNG, JPG, JPEG, BMP, TIFF, WEBP

## 📂 폴더 구조 예시

```
screenshots/
├── page_001.png
├── page_002.png
├── ...
└── page_595.png

# 실행 후
screenshots/
├── ocr_output/
│   ├── page_001.txt        # 개별 모드
│   ├── page_002.txt
│   ├── ...
│   └── AWS_SAA_C03.txt     # --merge 모드
├── page_001.png
└── ...
```

## ⚠️ 주의사항

- **Google Cloud 서비스 계정 키(JSON)는 절대 공개 저장소에 커밋하지 마세요.** `.gitignore`에 이미 `*.json`이 포함되어 있습니다.
- 월 1,000건 초과 시 [Cloud Vision 가격 정책](https://cloud.google.com/vision/pricing)을 확인하세요.
- 4K 해상도 스크린샷을 사용하면 OCR 정확도가 극대화됩니다.

## 📜 License

MIT License
