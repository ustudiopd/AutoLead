# AutoLead - 리드 데이터 자동 보강 시스템

세일즈포스 리드 데이터를 DART API와 연동하여 자동으로 보강(Enrichment)하는 시스템입니다.

## 프로젝트 개요

수집된 리드 데이터(CSV)를 DART API를 통해 자동으로 보강하여 세일즈포스 CRM 표준 양식으로 변환합니다.

### 주요 기능
- 회사명 기반 DART API 자동 검색
- 기업 정보 자동 추출 (회사명, 주소, 웹사이트, KSIC 코드)
- **Gemini AI를 활용한 지능형 매칭** (다중 매칭 시 최적 선택)
- 신뢰도 점수 자동 계산 (High/Medium/Low)
- KSIC→SIC 코드 자동 변환 (매핑 테이블 기반)

## 설치 방법

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일에 API 키를 설정하세요:
```
DART_API_KEY=your_dart_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
```

- DART API 키는 [Open DART 사이트](https://opendart.fss.or.kr/)에서 발급받을 수 있습니다.
- Google API 키는 [Google AI Studio](https://makersuite.google.com/app/apikey)에서 발급받을 수 있습니다.
  - Gemini API는 선택 사항입니다. 없어도 기본 기능은 동작하지만, 다중 매칭 시 정확도가 향상됩니다.

## 사용 방법

### 웹 UI 실행 (권장)
```bash
python run_server.py
```
브라우저에서 `http://localhost:8000` 접속

### CLI 실행
```bash
python src/main.py
```

### 입력 파일
- 웹 UI: 브라우저에서 CSV 파일 업로드
- CLI: 입력 CSV 파일은 `csv/` 디렉토리에 배치
- 기본 입력 파일: `csv/FY26 Q4 _CIO Summit_post_01190208__CIO Summit_post_01190208_leads_20250210_20260211.csv`

### 출력 파일
- 웹 UI: 브라우저에서 다운로드 또는 결과 뷰어에서 확인
- CLI: 보강된 결과는 `output/enriched_leads_sample.csv`에 저장됩니다.

## 프로젝트 구조

```
AutoLead/
├── src/                          # 소스 코드
│   ├── api/                      # FastAPI 웹 서버
│   │   ├── main.py              # FastAPI 앱
│   │   ├── models.py            # Pydantic 모델
│   │   ├── job_manager.py      # 작업 관리자
│   │   ├── processor_service.py # 처리 서비스
│   │   └── routes/              # API 라우트
│   │       ├── upload.py        # 파일 업로드
│   │       ├── process.py       # 처리 시작/상태
│   │       ├── results.py       # 결과 조회
│   │       └── websocket.py    # WebSocket 진행 상황
│   ├── dart_client.py           # DART API 클라이언트
│   ├── gemini_client.py         # Gemini API 클라이언트 (지능형 매칭)
│   ├── data_processor.py        # 데이터 전처리 및 보강
│   ├── ksic_sic_mapper.py       # KSIC→SIC 매핑
│   └── main.py                  # CLI 메인 실행 스크립트
├── static/                       # 웹 UI 정적 파일
│   ├── index.html               # 메인 페이지
│   ├── css/
│   │   └── style.css            # 모노톤 디자인 스타일
│   └── js/
│       └── app.js               # 프론트엔드 로직
├── csv/                          # 입력 CSV 파일 (CLI용)
├── uploads/                      # 업로드된 파일 (웹 UI용)
├── data/                         # 데이터 파일
│   └── ksic_to_sic_mapping.csv  # KSIC→SIC 매핑 테이블
├── output/                       # 출력 결과 파일
├── memory_bank/                  # 프로젝트 컨텍스트 문서
├── .env                          # 환경 변수 (gitignore)
├── requirements.txt              # Python 의존성
├── run_server.py                 # 웹 서버 실행 스크립트
└── README.md                     # 프로젝트 문서
```

## 신뢰도 점수 기준

- **High**: DART에 정확히 1개 기업이 검색되고, 이메일/웹사이트 도메인이 일치하는 경우
- **Medium**: 검색 결과는 있으나 도메인이 다르거나, 유사한 기업이 여러 개 조회되는 경우
- **Low**: DART 검색 결과가 없거나 매핑이 실패한 경우

## Gemini AI 활용

이 프로젝트는 Gemini 2.0 Flash API를 활용하여 매칭 정확도를 향상시킵니다:

- **다중 매칭 시 최적 선택**: DART에서 여러 기업이 매칭될 때, 이메일 도메인과 업종 정보를 고려하여 가장 적합한 기업을 자동 선택
- **컨텍스트 기반 매칭**: 단순 문자열 매칭이 아닌 의미적 유사도를 고려한 지능형 매칭

Gemini API가 없어도 기본 기능은 정상 동작하지만, 다중 매칭 상황에서 정확도가 향상됩니다.

## 주의사항

- DART API는 상장사 및 일부 비상장사만 포함합니다 (개인사업자, 미공시 소기업 제외)
- API 호출 제한으로 인해 처리 시간이 소요될 수 있습니다
- Gemini API 사용 시 추가 비용이 발생할 수 있습니다
- KSIC→SIC 매핑 테이블은 수동으로 구축해야 합니다

## 라이선스

이 프로젝트는 내부 사용을 위한 것입니다.
