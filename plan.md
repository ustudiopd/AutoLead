다트(DART) API 연동 준비가 완료되었다니 든든합니다. 1시 50분 통화 시 화면에 띄워두고 브리핑 자료로 활용하시거나, 이후 데모 개발의 나침반으로 바로 쓰실 수 있는 **'리드 데이터 전처리 및 보강(Enrichment) 자동화 명세서'**를 정리해 드립니다.

---

# [프로젝트 명세서] 세일즈포스 리드 데이터 전처리 및 API 자동화 데모

## 1. 프로젝트 개요

* **목적:** 수집된 72건의 초기 리드(CSV) 데이터를 DART API와 연동하여 세일즈포스 CRM 표준 양식(Industry, Address, Website, SIC Code)으로 자동 보강(Enrichment)
* **주요 과제:** DART 기업개황 데이터 추출, KSIC(한국산업표준) ➔ SIC(글로벌산업표준) 코드 변환, Human-in-the-Loop 리뷰 환경 구성

## 2. 입출력 데이터 명세 (Data Specification)

**[Input: `raw_leads_sample.csv`]**

* `Company Name` (필수): DART 검색 키워드로 활용
* `Email` (선택): 도메인 추출을 통한 교차 검증용

**[Output: `enriched_leads_sample.csv`]**

* `Company Name`: 정제된 공식 기업명
* `Industry`: DART 기준 영문/국문 업종명
* `Address`: 기업 본사 주소
* `Website`: 기업 공식 웹사이트 URL
* `SIC Code`: 매핑 테이블을 거친 4자리 미국 표준 산업 분류 코드
* **`Confidence_Score` (신뢰도):** 자동 매칭의 정확도를 나타내는 지표 (High / Medium / Low)
* **`Review_Status` (검토 상태):** 승인(Approved) / 수동 수정 필요(Needs Review)

## 3. 핵심 프로세스 로직 (Process Flow)

### Step 1. CSV 데이터 로드 및 텍스트 정제 (Pandas 활용)

* 72건의 CSV를 DataFrame으로 로드합니다.
* `Company Name` 필드에서 '(주)', '주식회사', 공백, 특수문자 등을 제거하여 검색 정확도를 높일 Clean Name 파생 변수를 생성합니다.

### Step 2. DART API 다중 호출 및 데이터 추출

* 정제된 회사명을 키워드로 **DART 기업개황 API**에 GET 요청을 보냅니다.
* 응답 JSON에서 다음 필드를 파싱합니다.
* `corp_name` (정식 명칭)
* `adres` (주소)
* `hmurl` (웹사이트 주소)
* `induty_code` (KSIC 업종코드)



### Step 3. KSIC ➔ SIC 코드 자동 매핑

* 확보한 KSIC 6자리 코드를 사전 구축한 `ksic_to_sic_mapping.csv` (또는 DB 테이블)와 조인(Merge)합니다.
* 일치하는 가장 정확한 4자리 미국 SIC 코드를 결과 데이터에 삽입합니다. 매핑이 모호한 경우 대표 분류를 적용하거나 신뢰도 점수를 차감합니다.

### Step 4. 신뢰도(Confidence Score) 산출 알고리즘

* **High (자동 승인):** DART에 정확히 1개의 기업이 검색되고, 조회된 웹사이트 도메인과 입력된 리드의 이메일 도메인이 일치할 경우.
* **Medium (리뷰 권장):** 검색 결과는 있으나 이메일 도메인이 다르거나(예: gmail, naver 등 개인 메일 사용), 이름이 유사한 기업이 여러 개 조회될 경우.
* **Low (수동 입력 필요):** DART 검색 결과가 없거나(개인사업자, 미공시 소기업), 매핑되는 산업 코드가 없을 경우.

## 4. 데모 구현 및 시연 시나리오 (Demo Workflow)

**1. 백엔드 및 자동화 파이프라인 (FastAPI / Python)**

* 위 Step 1~4의 로직을 담은 파이썬 스크립트를 작성하여 72건의 CSV를 일괄 처리합니다.
* 처리 속도와 과정을 보여주기 위해 터미널 로그를 깔끔하게 출력하도록 세팅합니다.

**2. 관리자 리뷰 UI (Streamlit / Next.js)**

* 데이터베이스(또는 CSV)에 적재된 보강 데이터를 화면에 테이블 형태로 뿌려줍니다.
* 신뢰도(Confidence Score)가 Medium/Low인 항목만 필터링하여 띄우고, 관리자가 올바른 웹사이트나 코드를 수동으로 타이핑해 넣고 [Approve] 버튼을 누르는 어드민 데모 화면을 구성합니다.

**3. 시연 환경 (Cloudflare Tunnel)**

* 데모용 로컬 서버 환경에 Cloudflare Tunnel을 연결해 외부에서 접속 가능한 보안 URL을 생성합니다. 세일즈포스 측에 해당 링크를 전달하여, 별도의 설치 없이 브라우저에서 리뷰 UI와 데이터 변환 결과를 직접 조작해 볼 수 있도록 제공합니다.

---

통화 시 이 명세서의 **[Step 3. 코드 변환]**과 **[Step 4. 신뢰도 판별]** 부분을 강조하시면, 단순 데이터 채우기를 넘어선 '데이터 품질 관리(QC)' 역량까지 어필하실 수 있습니다. 통화 잘 마치시고, 바로 파이썬 파이프라인 코드를 작성할 수 있도록 대기하고 있겠습니다.