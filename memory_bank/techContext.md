# Technical Context

## 기술 스택

- **Python 3.8+**: 메인 개발 언어
- **dart-fss**: DART API 연동 라이브러리
- **google-generativeai**: Gemini API 연동 라이브러리
- **pandas**: 데이터 처리 및 CSV 조작
- **python-dotenv**: 환경 변수 관리
- **requests**: HTTP 요청 처리

## 개발 환경

### 환경 변수 설정
- `.env` 파일에 다음 키 설정 필요:
  - `DART_API_KEY`: DART API 키 (필수)
  - `GOOGLE_API_KEY`: Google API 키 (선택, Gemini 활용 시)
- DART API 키는 Open DART 사이트(https://opendart.fss.or.kr/)에서 발급
- Google API 키는 Google AI Studio(https://makersuite.google.com/app/apikey)에서 발급

### 프로젝트 구조
```
AutoLead/
├── src/                    # 소스 코드
│   ├── dart_client.py      # DART API 클라이언트
│   ├── gemini_client.py    # Gemini API 클라이언트 (지능형 매칭)
│   ├── data_processor.py  # 데이터 전처리 및 보강
│   ├── ksic_sic_mapper.py # KSIC→SIC 매핑
│   └── main.py            # 메인 실행 스크립트
├── csv/                    # 입력 CSV 파일
├── data/                   # 매핑 테이블 등 데이터 파일
│   └── ksic_to_sic_mapping.csv
├── output/                 # 출력 결과 파일
└── .env                    # 환경 변수 (gitignore)
```

### 설치 방법
```bash
pip install -r requirements.txt
```

### 실행 방법
```bash
python src/main.py
```

## DART API 연동

### API 인증
- Open DART 사이트에서 API 키 발급
- `dart-fss` 라이브러리를 통한 인증 및 호출

### 주요 API 사용
- `dart.get_corp_code()`: 기업 코드 목록 조회
- `dart.api.filings.get_corp_info(corp_code)`: 기업개황 정보 조회

### API 제한사항
- API 호출 시 요청 간 딜레이 필요 (0.1초)
- 일일 호출 제한 존재 (API 키별로 상이)

## Gemini API 연동

### API 인증
- Google AI Studio에서 API 키 발급
- `google-generativeai` 라이브러리를 통한 인증 및 호출
- 모델: `gemini-2.0-flash-exp`

### 주요 기능
- **다중 매칭 시 최적 선택**: 여러 기업이 매칭될 때 컨텍스트를 고려한 지능형 선택
- **회사명 정제 개선**: 약칭, 영문명, 오타 처리
- **업종 추론**: KSIC 코드가 없을 때 회사명으로 업종 추론

### API 제한사항
- API 호출 비용 발생 가능
- 처리 시간 증가 가능
- 선택적 사용 (없어도 기본 기능 동작)

## 제약사항

- DART API는 상장사 및 일부 비상장사만 포함 (개인사업자, 미공시 소기업 제외)
- KSIC→SIC 매핑 테이블은 수동 구축 필요
- API 호출 속도 제한으로 인한 처리 시간 고려 필요
