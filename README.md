# ebook-ocr-batch

eBook 스크린샷을 Google Cloud Vision API로 OCR 처리해 텍스트 선택/검색이 가능한 Searchable PDF로 변환하는 도구입니다.

## 특징

- **Searchable PDF 생성**: 원본 이미지 위에 투명 텍스트 레이어를 입혀 텍스트 드래그/복사/검색 가능
- **한국어 + 영어 혼용** 자동 인식 (AWS 전문 용어 등)
- **`document_text_detection`**: 밀집 텍스트(책/문서)에 최적화된 OCR
- **멀티스레드** 병렬 처리로 빠른 변환
- **자연 정렬**: `page_1, page_2, ... page_10` 순서 보장
- 실시간 진행률 표시 (ETA 포함)

## 사전 준비

### 1. Google Cloud Vision API 활성화

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성합니다.
2. Cloud Vision API를 활성화합니다.
3. 서비스 계정 키(JSON)를 발급받아 다운로드합니다.
4. 환경 변수를 설정합니다:

```powershell
# Windows (PowerShell)
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\your-key.json"

# 영구 설정 (시스템 환경변수)
[System.Environment]::SetEnvironmentVariable("GOOGLE_APPLICATION_CREDENTIALS", "C:\path\to\your-key.json", "User")
```

> **비용**: 월 1,000건 무료. 595페이지 책 한 권은 무료 한도 안에 들어갑니다.

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

## 사용법

### Searchable PDF 생성 (가장 많이 쓰는 기능)

```bash
python ocr.py ./screenshots --pdf --pdf-name "AWS_SAA_C03.pdf"
```

PNG 이미지 폴더를 넣으면 텍스트 선택/복사/검색이 가능한 PDF가 생성됩니다.

```
원본 이미지 (눈에 보이는 레이어)
  + 투명 텍스트 (OCR 결과가 글자 위치에 정확히 겹침)
  = Searchable PDF
```

### 개별 텍스트 파일로 저장

```bash
python ocr.py ./screenshots
```

### 하나의 텍스트 파일로 병합

```bash
python ocr.py ./screenshots --merge --merge-name "AWS_SAA_C03.txt"
```

### PDF + 텍스트 동시 생성

```bash
python ocr.py ./screenshots --pdf --merge --pdf-name "book.pdf" --merge-name "book.txt"
```

### 전체 옵션

```
python ocr.py --help
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `input_dir` | 스크린샷 이미지 폴더 경로 | (필수) |
| `-o, --output-dir` | 결과 저장 폴더 | `<input_dir>/ocr_output` |
| `--pdf` | Searchable PDF 생성 | `false` |
| `--pdf-name` | PDF 파일명 | `output.pdf` |
| `--merge` | 모든 페이지를 텍스트 파일 하나로 병합 | `false` |
| `--merge-name` | 병합 파일명 | `merged_output.txt` |
| `--workers` | 동시 처리 스레드 수 | `4` |
| `--delay` | API 호출 간 대기(초) | `0.1` |

## 지원 이미지 형식

PNG, JPG, JPEG, BMP, TIFF, WEBP

## 폴더 구조 예시

```
screenshots/
├── page_001.png
├── page_002.png
├── ...
└── page_595.png

# python ocr.py ./screenshots --pdf --pdf-name "AWS_SAA_C03.pdf" 실행 후
screenshots/
└── ocr_output/
    └── AWS_SAA_C03.pdf   ← 텍스트 선택 가능한 PDF
```

## 주의사항

- **Google Cloud 서비스 계정 키(JSON)는 절대 공개 저장소에 커밋하지 마세요.** `.gitignore`에 이미 `*.json`이 포함되어 있습니다.
- 월 1,000건 초과 시 [Cloud Vision 가격 정책](https://cloud.google.com/vision/pricing)을 확인하세요.
- 4K 해상도 스크린샷을 사용하면 OCR 정확도가 올라갑니다.

## License

MIT License
