# Employee Count (No of Employees) — evidence-based enrichment

## Non‑negotiables
- **No AI estimation**: 직원 수는 LLM이 “그럴듯하게” 생성/추정 금지.
- **Only explicit values**: DB/웹페이지에 **명시된 단일 숫자**만 수용.
- **Always store provenance**: 값과 함께 **출처/등급/방법/근거/URL/상태**를 저장.
- **Reject**: 범위(`51-200`, `100+`), 추정(`약`, `about`, `estimated`, `over`) 및 애매 값.

## Output columns (always present)
- `No of Employees`
- `Employee_Count_Source`
- `Employee_Count_Source_Tier`
- `Employee_Count_Match_Method`
- `Employee_Count_Evidence`
- `Employee_Count_Status`
- `Employee_Count_Source_URL`

## Evidence sources & priority
Evidence 후보를 모은 뒤 1건 선택.
- **Priority**: ORIGINAL > NICE_DB > OFFICIAL_WEBSITE > (THIRD_PARTY / DIRECTORY / NEWS / OTHER_WEB_EVIDENCE) > EMPTY

## NICE DB matching
- **Data**: `data/nice_company_db.xlsx` (한글업체명/영문업체명/종업원수)
- **Methods**:
  - `NICE_EXACT`, `NICE_CLEANED`, `NICE_NORMALIZED_EN`
  - `NICE_KR_INFERRED`, `NICE_KR_INFERRED_CLEANED` (Gemini로 한글명 추정)
  - `NICE_FUZZY` (difflib 기반, 오탐 가능성 높음 → 게이트/튜닝 필요)
- **Risk**: `NICE_FUZZY`는 문자열 유사도 때문에 “전혀 다른 회사”에 붙을 수 있음 (예: Tech2worldwide → Cheil Worldwide 등).

## Open web employee evidence (best‑effort)
- 목적: 잡코리아/사람인/잡플래닛/인크루잇 등에서 “사원수/직원수” **명시 숫자**를 찾아 증거로 사용.
- 외부 검색은 환경/차단에 취약하므로 **시간 예산/페이지 수 상한**으로 제어.

### Speed guardrails (env)
- `DISABLE_OPEN_WEB` (기본 1이면 오픈웹 완전 비활성)
- `OPEN_WEB_EMPLOYEES=1` (오픈웹 증거 수집 on/off)
- `OPEN_WEB_TIME_BUDGET_SEC` (행당 오픈웹 최대 시간)
- `OPEN_WEB_MAX_RESULTS` (검색 결과 URL 상한)
- `OPEN_WEB_MAX_FETCH` (fetch할 페이지 수 상한)
- `OPEN_WEB_HTTP_TIMEOUT`, `OPEN_WEB_SEARCH_TIMEOUT` (짧게 유지)

## Concurrency
- 행 단위 병렬 처리: `PARALLEL_WORKERS`로 제한 (기본값 상향 가능)
- 주의: Windows(cp949) 콘솔에서 yaspin 스피너가 `UnicodeEncodeError`를 유발할 수 있으나, 작업 자체가 중단되지는 않음.

## Key code locations
- `src/data_processor.py`: evidence 수집/검증/선택/컬럼 저장
- `src/web_crawler.py`: 검색 URL 수집(DDG/DDGS 폴백), 페이지 텍스트 추출
- `src/open_web_employee_finder.py`: 오픈웹 증거 수집(시간 예산 포함)
- `src/api/processor_service.py`: 병렬 처리(`PARALLEL_WORKERS`)
- `scripts/run_enrich_test.py`: 테스트 실행(`PROCESS_ROW_LIMIT`, `TEST_INPUT_HINT/TEST_INPUT_PATH`)

