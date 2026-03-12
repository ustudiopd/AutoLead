# 직원 수(No of Employees) 추출 - 프로젝트 컨텍스트 (AutoLead)

이 문서는 **ChatGPT / Gemini**에게 “직원 수(No of Employees)를 어떻게 더 잘 구할지”를 질문할 때, 모델이 이 프로젝트의 구조/제약/현재 상태를 빠르게 이해하도록 돕기 위한 컨텍스트입니다.

---

## 수정된 원칙 (핵심)

- **금지**: AI가 직원 수를 **추정해서 숫자를 만들어내는 것**. 범위값(`51-200`, `100+`)을 단일 숫자로 바꾸거나, 문맥상 그럴듯하다고 숫자를 생성하는 것.
- **허용**: **실제 웹페이지/실제 데이터 소스에 명시된 값**을 가져오는 것. 출처가 꼭 공식 사이트가 아니더라도 **근거가 명확하면 수집 가능**.
- **필수**: 출처(source), 추출 방식(method), 근거(evidence), 신뢰 등급(trust tier), URL을 반드시 함께 저장.

즉, **“공식/비공식”보다 “AI 추정이냐, 실제 근거값이냐”**가 기준이다.

---

## 목표 (What we want)

- 입력 리드(주로 Salesforce Export)에서 **회사별 직원 수**를 가능한 한 정확하게 채운다.
- **증거 기반 다중 소스 수집 + 출처 등급화**: 값 1개만 저장하는 것이 아니라, **증거 후보를 모은 뒤 우선순위로 1건 선택**하고, 선택된 값과 함께 **출처·등급·근거·URL**을 저장한다.
- 직원 수 숫자는 **AI가 생성/추정하지 말 것**. 실제 페이지/DB/원본에 **명시된 값만** 저장.

---

## 현재 파이프라인 요약 (How it works today)

### 주요 실행 흐름

- 처리 엔트리: `src/api/processor_service.py`, 테스트: `scripts/run_enrich_test.py`
- 단일 행 처리: `DataProcessor.process_lead()` in `src/data_processor.py`

### 직원 수: 증거 수집 → 1건 선택 → 출처 컬럼 저장

1. **증거 후보 수집**
   - `resolve_employee_count_from_original()`: 원본 입력값(placeholder/범위/추정값이면 제외)
   - `resolve_employee_count_from_nice()`: NICE DB (한글/영문/정규화/AI 한글명 추론 매칭)
   - `resolve_employee_count_from_web_evidence()`: 웹 크롤링(회사 사이트 등에서 단일 숫자만 추출)
2. **검증**: `validate_employee_count_value()` — 범위(`51-200`, `100+`), `약`, `over`, `about` 등 추정 표현 거부.
3. **선택**: `select_best_employee_count_evidence(evidences)` — 우선순위: 원본 > NICE > 공식 사이트 > 제3자/디렉토리 > 기타.
4. **저장**: 선택된 evidence의 `value`를 `No of Employees`에, 나머지를 출처 컬럼들에 저장.

### 허용 소스 (출처 등급과 함께 저장)

- `ORIGINAL` (원본 입력)
- `NICE_DB` (로컬 나이스 기업정보 엑셀)
- `OFFICIAL_WEBSITE` (회사 공식 사이트)
- `THIRD_PARTY_PROFILE`, `BUSINESS_DIRECTORY`, `PUBLIC_COMPANY_DB`, `NEWS_ARTICLE`, `OTHER_WEB_EVIDENCE` (추후 확장 시)
- `EMPTY` (미발견)

---

## 결과 컬럼 (저장 규칙 반영)

| 컬럼명 | 설명 | 예시 값 |
|--------|------|--------|
| `No of Employees` | 최종 채택된 직원 수(단일 숫자) 또는 빈칸 | `120`, `` |
| `Employee_Count_Source` | 출처 | `ORIGINAL`, `NICE_DB`, `OFFICIAL_WEBSITE`, `THIRD_PARTY_PROFILE`, … `EMPTY` |
| `Employee_Count_Source_Tier` | 신뢰 등급 | `HIGH`, `MEDIUM`, `LOW` |
| `Employee_Count_Match_Method` | 매칭/추출 방식 | `INPUT`, `NICE_EXACT`, `NICE_CLEANED`, `NICE_KR_INFERRED`, `TEXT_BLOCK_REGEX` 등 |
| `Employee_Count_Evidence` | 근거 문구 | `Original input value`, `NICE DB 한글업체명 exact match`, `Extracted from page: "120 employees"` 등 |
| `Employee_Count_Status` | 수용 여부 | `ACCEPTED`, `REJECTED_PLACEHOLDER`, `REJECTED_RANGE`, `REJECTED_ESTIMATED`, `NOT_FOUND` 등 |
| `Employee_Count_Source_URL` | 출처 URL (웹인 경우) | `https://...` 또는 `` |

---

## 저장/거부 규칙

- **수용 조건**: (1) 실제 페이지/DB에 숫자가 명시됨 (2) 문맥상 직원 수임이 확인됨 (3) 단일 숫자 (4) 범위/추정/애매 표현 아님.
- **거부**: `51-200`, `100+`, `약 200명`, `over 300 employees`, AI가 문맥 보고 임의 환산한 값, 출처 간 값 충돌 시 우선순위 판단 불가한 경우.

---

## 파일/코드 포인트 (Where to look)

- `src/data_processor.py`
  - `EmployeeCountEvidence` (dataclass), `validate_employee_count_value()`, `classify_employee_count_source()`, `select_best_employee_count_evidence()`
  - `resolve_employee_count_from_original()`, `resolve_employee_count_from_nice()`, `resolve_employee_count_from_web_evidence()`
  - `process_lead()` 내 직원수 블록: 증거 수집 → 선택 → 위 컬럼 저장
- NICE DB: `data/nice_company_db.xlsx` (한글업체명, 영문업체명, 종업원수)
- 회사명 매칭 보조(LLM): `src/gemini_client.py` — `infer_korean_company_name()` (직원 수 숫자 생성 금지)

---

## 제약/주의사항 (Constraints)

- 직원 수는 **LLM이 숫자를 만들어내면 안 됨**. LLM은 회사명 정규화·동일 회사 판별·페이지 내 직원 수 문맥 블록 식별 등 **매칭/구조화 보조**만 허용.
- **공식 사이트만**이 아니라, 실제 명시값이 있으면 비공식 소스도 수집 가능하되 **반드시 source, source_tier, evidence, url을 함께 저장**.

---

## ChatGPT / Gemini에게 붙여넣기 좋은 한 줄 (Cursor 지시문)

> 직원 수는 AI가 추정하지 말고, 실제 페이지나 DB에 명시된 값만 evidence로 수집하라. 공식 사이트가 아니어도 허용하되, 반드시 source, source_tier, evidence, url을 함께 저장하고, 범위값/추정값/충돌값은 reject하라.

---

## 원하는 결과물 (What we expect from you)

- “추측으로 숫자 생성” 금지 원칙 존중
- 오탐/과탐을 줄이는 매칭·검증 기준 명확히 제시
- 구현 가능한 수준의 알고리즘/데이터 구조 제안
- (가능하면) Python 기준 의사코드 또는 모듈 설계 제시
