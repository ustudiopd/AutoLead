# Active Context

## 현재 작업 포커스

- DART API + Gemini API 통합 완료
- 다음 단계: 실제 데이터로 테스트 및 검증 (직원수 evidence 기반 포함)

## 최근 변경사항

### 2026-03-12
- **직원수(No of Employees) evidence 기반 보강 추가**
  - NICE DB + (공식/오픈웹) 증거 후보 수집 → 검증 → 1건 선택 → 출처 컬럼 저장
  - 결과 컬럼: `Employee_Count_*` (source/tier/method/evidence/status/url)
- **행 단위 병렬 처리 도입**
  - `src/api/processor_service.py`에서 ThreadPool 기반, `PARALLEL_WORKERS`로 제한
- **오픈웹 검색/추출 안정화 시도**
  - DDG 리다이렉트(`uddg=`) 해석, DDGS 폴백
  - 속도 이슈로 `DISABLE_OPEN_WEB` / 시간예산(`OPEN_WEB_TIME_BUDGET_SEC`) 등 가드레일 추가
  - 잡코리아/사람인/잡플래닛/인크루잇 도메인 우선(락인) + 콤마 숫자(1,234) 추출 보강
- **테스트 러너 개선**
  - `scripts/run_enrich_test.py`에서 `TEST_INPUT_PATH`/`TEST_INPUT_HINT`로 TEST1/TEST2 전환, `PROCESS_ROW_LIMIT` 지원

### 2026-02-25 (오후)
- **Gemini API 통합 완료**
  - Gemini API 클라이언트 모듈 구현 (`src/gemini_client.py`)
  - DART 클라이언트에 Gemini 통합 (다중 매칭 시 최적 선택)
  - 데이터 프로세서에 Gemini 컨텍스트 전달 로직 추가
  - 환경 변수에 `GOOGLE_API_KEY` 추가
  - `requirements.txt`에 `google-generativeai` 추가
  - README 및 memory_bank 문서 업데이트

### 2026-02-25 (오전)
- 프로젝트 초기화 완료 (AGENTS.md, Cursor Rules, memory_bank 구조 생성)
- DART API 클라이언트 모듈 구현 (`src/dart_client.py`)
- 데이터 전처리 및 보강 모듈 구현 (`src/data_processor.py`)
- KSIC→SIC 매핑 모듈 구현 (`src/ksic_sic_mapper.py`)
- 메인 실행 스크립트 구현 (`src/main.py`)
- 환경 설정 파일 생성 (`.env`, `requirements.txt`, `.gitignore`)
- memory_bank 문서 업데이트 (projectbrief, techContext, productContext)
