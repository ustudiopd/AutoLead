"""
데이터 전처리 및 보강 모듈
CSV 데이터 로드, 정제, DART API 연동을 통한 보강
직원수(No of Employees): AI 추정 금지, 실제 명시값만 증거 기반 수집 + 출처 등급화.
"""
import re
import pandas as pd
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
from .dart_client import DartClient

# --- 직원수 증거·출처 상수 (evidence-based multi-source) ---
EMP_SOURCE_ORIGINAL = "ORIGINAL"
EMP_SOURCE_NICE_DB = "NICE_DB"
EMP_SOURCE_OFFICIAL_WEBSITE = "OFFICIAL_WEBSITE"
EMP_SOURCE_THIRD_PARTY_PROFILE = "THIRD_PARTY_PROFILE"
EMP_SOURCE_BUSINESS_DIRECTORY = "BUSINESS_DIRECTORY"
EMP_SOURCE_PUBLIC_COMPANY_DB = "PUBLIC_COMPANY_DB"
EMP_SOURCE_NEWS_ARTICLE = "NEWS_ARTICLE"
EMP_SOURCE_OTHER_WEB_EVIDENCE = "OTHER_WEB_EVIDENCE"
EMP_SOURCE_EMPTY = "EMPTY"

EMP_TIER_HIGH = "HIGH"
EMP_TIER_MEDIUM = "MEDIUM"
EMP_TIER_LOW = "LOW"

EMP_STATUS_ACCEPTED = "ACCEPTED"
EMP_STATUS_REJECTED_PLACEHOLDER = "REJECTED_PLACEHOLDER"
EMP_STATUS_REJECTED_RANGE = "REJECTED_RANGE"
EMP_STATUS_REJECTED_ESTIMATED = "REJECTED_ESTIMATED"
EMP_STATUS_REJECTED_AMBIGUOUS = "REJECTED_AMBIGUOUS"
EMP_STATUS_REJECTED_CONFLICTING_EVIDENCE = "REJECTED_CONFLICTING_EVIDENCE"
EMP_STATUS_NOT_FOUND = "NOT_FOUND"


@dataclass
class EmployeeCountEvidence:
    """직원수 1건의 증거: 값 + 출처 + 등급 + 방식 + 근거 문구 + URL."""
    value: str
    source: str
    source_tier: str
    method: str
    evidence: str
    url: str

# 나이스 DB 경로 (data/nice_company_db.xlsx). output/docs에서 복사해 둔 파일 사용.
_NICE_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "nice_company_db.xlsx"
_nice_employees_cache: Optional[Dict[str, str]] = None

# 회사별 웹사이트 오버라이드 (data/company_website_overrides.csv). Codiplan, KB-ELEMENT 등 실제 사이트 보강용.
_WEBSITE_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "company_website_overrides.csv"
_website_overrides_cache: Optional[Dict[str, str]] = None

# NICE 한글 회사명 추정(Gemini) 결과 캐시/락 (병렬 처리 시 실패율↓)
_nice_kr_name_cache: Dict[str, Optional[str]] = {}
_nice_kr_name_lock = threading.Lock()


def _load_website_overrides() -> Dict[str, str]:
    """company_name(정규화) -> website. 프로세스당 1회 캐시."""
    global _website_overrides_cache
    if _website_overrides_cache is not None:
        return _website_overrides_cache
    out: Dict[str, str] = {}
    if not _WEBSITE_OVERRIDES_PATH.exists():
        _website_overrides_cache = out
        return out
    try:
        df = pd.read_csv(_WEBSITE_OVERRIDES_PATH, encoding="utf-8-sig")
        if "company_name" not in df.columns or "website" not in df.columns:
            _website_overrides_cache = out
            return out
        for _, r in df.iterrows():
            name = (r.get("company_name") or "")
            url = (r.get("website") or "")
            if pd.isna(name) or pd.isna(url) or not str(url).strip().startswith("http"):
                continue
            name = str(name).strip()
            url = str(url).strip()
            if name:
                out[name] = url
                out[_normalize_for_lookup(name)] = url
        _website_overrides_cache = out
    except Exception:
        _website_overrides_cache = out
    return out


def _normalize_for_lookup(s: str) -> str:
    """회사명 매칭용 정규화 (공백·특수문자 정리, 소문자)."""
    if not s or not str(s).strip():
        return ""
    t = re.sub(r"\(주\)|주식회사|\(유\)|유한회사|co\.?|ltd\.?|inc\.?", "", str(s).strip(), flags=re.IGNORECASE)
    t = re.sub(r"[^\w\s\-_]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _token_jaccard(a: str, b: str) -> float:
    """간단 토큰 겹침 비율(Jaccard). NICE 퍼지 오탐 방지용."""
    sa = set([t for t in _normalize_for_lookup(a).split(" ") if t])
    sb = set([t for t in _normalize_for_lookup(b).split(" ") if t])
    uni = sa.union(sb)
    if not uni:
        return 0.0
    return len(sa.intersection(sb)) / len(uni)


def _string_similarity(a: str, b: str) -> float:
    """문자열 유사도(0~1). difflib 기반."""
    try:
        import difflib
        return difflib.SequenceMatcher(None, _normalize_for_lookup(a), _normalize_for_lookup(b)).ratio()
    except Exception:
        return 0.0


def _load_nice_employees() -> Dict[str, str]:
    """나이스 DB에서 한글업체명·영문업체명(정규화) -> 종업원수 로딩. 프로세스당 1회 캐시."""
    global _nice_employees_cache
    if _nice_employees_cache is not None:
        return _nice_employees_cache
    out: Dict[str, str] = {}
    if not _NICE_DB_PATH.exists():
        _nice_employees_cache = out
        return out
    try:
        df = pd.read_excel(_NICE_DB_PATH, sheet_name=0, header=1)
        if "한글업체명" not in df.columns or "종업원수" not in df.columns:
            _nice_employees_cache = out
            return out
        cols = ["한글업체명", "종업원수"]
        if "영문업체명" in df.columns:
            cols.append("영문업체명")
        df = df[cols]
    except Exception:
        _nice_employees_cache = out
        return out
    for _, r in df.iterrows():
        name = (r.get("한글업체명") or "")
        if pd.isna(name):
            continue
        name = str(name).strip()
        if not name:
            continue
        emp = r.get("종업원수")
        if pd.isna(emp):
            continue
        try:
            n = int(float(emp))
            if n <= 0:
                continue
            val = str(n)
        except Exception:
            continue
        out[name] = val
        cleaned = re.sub(r"\(주\)|주식회사|\(유\)|유한회사|\(합\)|합자회사", "", name, flags=re.IGNORECASE)
        cleaned = re.sub(r"[^\w\s\-_]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and cleaned != name:
            out[cleaned] = val
        en = r.get("영문업체명")
        if not pd.isna(en) and en:
            en_norm = _normalize_for_lookup(str(en))
            if en_norm and en_norm not in out:
                out[en_norm] = val
    _nice_employees_cache = out
    return out


def _url_exists(url: str, timeout: int = 3) -> bool:
    """HEAD 요청으로 URL 존재 여부 확인. 2xx면 True."""
    if not url or not url.startswith("http"):
        return False
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; AutoLead/1.0)")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= getattr(r, "status", 200) < 400
    except Exception:
        return False


def validate_employee_count_value(value: str) -> Tuple[bool, str]:
    """
    직원수 값이 수용 가능한 단일 숫자인지 검증.
    Returns:
        (True, EMP_STATUS_ACCEPTED) 또는 (False, reject_status)
    """
    if not value or not str(value).strip():
        return False, EMP_STATUS_REJECTED_PLACEHOLDER
    v = str(value).strip()
    v_lower = v.lower()
    if v_lower in ("unknown", "n/a", "na", "-", "—", ""):
        return False, EMP_STATUS_REJECTED_PLACEHOLDER
    if re.search(r"^\d+\s*-\s*\d+", v) or re.search(r"^\d+\+", v):
        return False, EMP_STATUS_REJECTED_RANGE
    for est in ("약", "about", "approximately", "~", "over ", "above ", "over ", "above", "circa", "around", "est.", "estimated"):
        if est in v_lower or v_lower.startswith(est.strip()):
            return False, EMP_STATUS_REJECTED_ESTIMATED
    try:
        n = int(float(v))
        if n <= 0:
            return False, EMP_STATUS_REJECTED_AMBIGUOUS
        return True, EMP_STATUS_ACCEPTED
    except Exception:
        return False, EMP_STATUS_REJECTED_AMBIGUOUS


def classify_employee_count_source(web_url: str, page_type_hint: str = "") -> Tuple[str, str]:
    """
    웹 출처의 소스 타입·등급 분류.
    현재는 회사 공식 사이트 1종만 크롤링하므로 OFFICIAL_WEBSITE / HIGH 반환.
    page_type_hint: 추후 확장용 (third_party, directory, news 등).
    """
    if page_type_hint and page_type_hint.upper() in (
        "THIRD_PARTY_PROFILE", "BUSINESS_DIRECTORY", "NEWS_ARTICLE", "OTHER_WEB_EVIDENCE"
    ):
        tier = EMP_TIER_MEDIUM if page_type_hint.upper() in ("THIRD_PARTY_PROFILE", "BUSINESS_DIRECTORY") else EMP_TIER_LOW
        return page_type_hint.upper(), tier
    u = (web_url or "").lower()
    dom = ""
    try:
        dom = (urlparse(u).netloc or "").lower()
    except Exception:
        dom = ""
    # 간단한 도메인 기반 휴리스틱 (오픈 웹 확장 대비)
    if any(k in dom for k in ("wikipedia.org", "crunchbase.com", "zoominfo.com", "opencorporates.com", "dnb.com")):
        return EMP_SOURCE_THIRD_PARTY_PROFILE, EMP_TIER_MEDIUM
    if any(k in dom for k in ("jobkorea.co.kr", "saramin.co.kr", "wanted.co.kr", "rocketpunch.com", "jobplanet.co.kr", "incruit.com")):
        return EMP_SOURCE_BUSINESS_DIRECTORY, EMP_TIER_LOW
    if any(k in dom for k in ("news", "press", "journal", "koreatimes", "yonhap", "mk.co.kr", "hankyung")):
        return EMP_SOURCE_NEWS_ARTICLE, EMP_TIER_LOW
    # 기본: 공식 사이트로 단정하지 않고 기타 웹 증거로 둠 (오픈 웹 검색 결과 포함)
    if u.startswith("http"):
        return EMP_SOURCE_OTHER_WEB_EVIDENCE, EMP_TIER_LOW
    return EMP_SOURCE_OFFICIAL_WEBSITE, EMP_TIER_HIGH


def select_best_employee_count_evidence(evidences: List[EmployeeCountEvidence]) -> Optional[EmployeeCountEvidence]:
    """
    우선순위: 원본 > NICE > 공식 사이트 > 제3자/디렉토리 > 기타.
    동일 회사 복수 근거 시 최고 tier 선택, tier 동일 시 지정 순서(ORIGINAL, NICE_DB, OFFICIAL_WEBSITE, ...) 우선.
    """
    if not evidences:
        return None
    tier_order = {EMP_TIER_HIGH: 0, EMP_TIER_MEDIUM: 1, EMP_TIER_LOW: 2}
    source_priority = {
        EMP_SOURCE_ORIGINAL: 0,
        EMP_SOURCE_NICE_DB: 1,
        EMP_SOURCE_OFFICIAL_WEBSITE: 2,
        EMP_SOURCE_THIRD_PARTY_PROFILE: 3,
        EMP_SOURCE_BUSINESS_DIRECTORY: 4,
        EMP_SOURCE_PUBLIC_COMPANY_DB: 5,
        EMP_SOURCE_NEWS_ARTICLE: 6,
        EMP_SOURCE_OTHER_WEB_EVIDENCE: 7,
    }
    def key(e: EmployeeCountEvidence) -> Tuple[int, int]:
        return (tier_order.get(e.source_tier, 99), source_priority.get(e.source, 99))
    return min(evidences, key=key)


class DataProcessor:
    """리드 데이터 전처리 및 보강 처리기"""
    
    def __init__(self):
        self.dart_client = DartClient()
    
    def clean_company_name(self, company_name: str) -> str:
        """
        회사명 정제
        - '(주)', '주식회사', 공백, 특수문자 제거
        
        Args:
            company_name: 원본 회사명
            
        Returns:
            정제된 회사명
        """
        if pd.isna(company_name) or not company_name:
            return ""
        
        cleaned = str(company_name).strip()
        
        # '(주)', '주식회사' 제거
        cleaned = re.sub(r'\(주\)|주식회사|\(유\)|유한회사|\(합\)|합자회사', '', cleaned, flags=re.IGNORECASE)
        
        # 특수문자 제거 (하이픈, 언더스코어는 유지)
        cleaned = re.sub(r'[^\w\s\-_]', '', cleaned)
        
        # 연속된 공백 제거
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        return cleaned.strip()
    
    def extract_email_domain(self, email: str) -> Optional[str]:
        """
        이메일에서 도메인 추출
        
        Args:
            email: 이메일 주소
            
        Returns:
            도메인 또는 None
        """
        if pd.isna(email) or not email:
            return None
        
        email_str = str(email).strip()
        
        # 이메일 형식 검증 및 도메인 추출
        email_pattern = r'^[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$'
        match = re.match(email_pattern, email_str)
        
        if match:
            return match.group(1).lower()
        
        return None
    
    def extract_website_domain(self, website_url: str) -> Optional[str]:
        """
        웹사이트 URL에서 도메인 추출
        
        Args:
            website_url: 웹사이트 URL
            
        Returns:
            도메인 또는 None
        """
        if pd.isna(website_url) or not website_url:
            return None
        
        url_str = str(website_url).strip()
        
        # http:// 또는 https://가 없으면 추가
        if not url_str.startswith(('http://', 'https://')):
            url_str = 'https://' + url_str
        
        try:
            parsed = urlparse(url_str)
            domain = parsed.netloc.lower()
            
            # www. 제거
            if domain.startswith('www.'):
                domain = domain[4:]
            
            return domain if domain else None
            
        except Exception:
            return None
    
    def calculate_confidence_score(
        self,
        dart_info: Optional[Dict],
        email_domain: Optional[str],
        website_domain: Optional[str]
    ) -> str:
        """
        신뢰도 점수 계산
        
        Args:
            dart_info: DART API에서 조회한 기업 정보
            email_domain: 이메일 도메인
            website_domain: 웹사이트 도메인
            
        Returns:
            'High', 'Medium', 'Low' 중 하나
        """
        if not dart_info:
            return 'Low'
        
        match_count = dart_info.get('match_count', 0)
        
        # High: 정확히 1개 매칭 + 도메인 일치
        if match_count == 1:
            if email_domain and website_domain:
                if email_domain == website_domain:
                    return 'High'
            
            # 도메인이 없어도 정확히 1개 매칭이면 High
            if match_count == 1 and dart_info.get('corp_name'):
                return 'High'
        
        # Medium: 검색 결과는 있으나 도메인 불일치 또는 다중 결과
        if match_count > 1:
            return 'Medium'
        
        if email_domain and website_domain:
            if email_domain != website_domain:
                return 'Medium'
        
        # Low: 검색 결과 없음
        return 'Low'

    def resolve_employee_count_from_original(self, row: pd.Series, enriched: Dict) -> Optional[EmployeeCountEvidence]:
        """원본 입력에서 직원수 추출. placeholder/범위/추정값이면 None."""
        raw = (enriched.get("No of Employees") or row.get("No of Employees") or "")
        raw = str(raw).strip() if raw is not None and not (isinstance(raw, float) and pd.isna(raw)) else ""
        ok, status = validate_employee_count_value(raw)
        if not ok:
            return None
        try:
            val = str(int(float(raw)))
        except Exception:
            return None
        return EmployeeCountEvidence(
            value=val,
            source=EMP_SOURCE_ORIGINAL,
            source_tier=EMP_TIER_HIGH,
            method="INPUT",
            evidence="Original input value",
            url="",
        )

    def resolve_employee_count_from_nice(self, company_name: str) -> Optional[EmployeeCountEvidence]:
        """나이스 DB에서 직원수 조회. 매칭 방식(method) 기록."""
        nice = _load_nice_employees()
        if not nice:
            return None
        key = (company_name or "").strip()
        if key and key in nice:
            return EmployeeCountEvidence(
                value=nice[key],
                source=EMP_SOURCE_NICE_DB,
                source_tier=EMP_TIER_HIGH,
                method="NICE_EXACT",
                evidence="NICE DB 한글업체명 exact match",
                url="",
            )
        cleaned = self.clean_company_name(company_name or "")
        if cleaned and cleaned in nice:
            return EmployeeCountEvidence(
                value=nice[cleaned],
                source=EMP_SOURCE_NICE_DB,
                source_tier=EMP_TIER_HIGH,
                method="NICE_CLEANED",
                evidence="NICE DB cleaned name match",
                url="",
            )
        key_en = _normalize_for_lookup(company_name or "")
        if key_en and key_en in nice:
            return EmployeeCountEvidence(
                value=nice[key_en],
                source=EMP_SOURCE_NICE_DB,
                source_tier=EMP_TIER_HIGH,
                method="NICE_NORMALIZED_EN",
                evidence="NICE DB normalized English name match",
                url="",
            )
        korean_name: Optional[str] = None
        try:
            # 병렬 처리 시 Gemini 호출이 흔들릴 수 있어 캐시/락 적용
            # 기본값은 OFF: 한글 추정이 퍼지 오탐을 유발할 수 있어 안전하게 막아둠
            allow_kr = os.getenv("NICE_ALLOW_GEMINI_KR", "0").strip().lower() not in {"0", "false", "no", "n", "off"}
            if allow_kr:
                with _nice_kr_name_lock:
                    if company_name in _nice_kr_name_cache:
                        korean_name = _nice_kr_name_cache[company_name]
                    else:
                        from .gemini_client import GeminiClient
                        gc = GeminiClient()
                        korean_name = gc.infer_korean_company_name(company_name or "")
                        _nice_kr_name_cache[company_name] = korean_name
            if korean_name and korean_name in nice:
                return EmployeeCountEvidence(
                    value=nice[korean_name],
                    source=EMP_SOURCE_NICE_DB,
                    source_tier=EMP_TIER_HIGH,
                    method="NICE_KR_INFERRED",
                    evidence="NICE DB match via AI-inferred Korean company name",
                    url="",
                )
            if korean_name:
                k_cleaned = self.clean_company_name(korean_name)
                if k_cleaned and k_cleaned in nice:
                    return EmployeeCountEvidence(
                        value=nice[k_cleaned],
                        source=EMP_SOURCE_NICE_DB,
                        source_tier=EMP_TIER_HIGH,
                        method="NICE_KR_INFERRED_CLEANED",
                        evidence="NICE DB match via AI-inferred Korean name (cleaned)",
                        url="",
                    )
        except Exception:
            pass
        # 퍼지 매칭: 유사도 임계값으로 한 건 채택 (환경변수 NICE_FUZZY_CUTOFF, 기본 0.72)
        import difflib
        try:
            cutoff = float(os.getenv("NICE_FUZZY_CUTOFF", "0.72") or "0.72")
            cutoff = max(0.65, min(0.95, cutoff))
        except Exception:
            cutoff = 0.72
        # 퍼지 매칭 오탐 방지용 추가 게이트(기본 ON)
        try:
            min_sim = float(os.getenv("NICE_FUZZY_MIN_SIM", "0.78") or "0.78")
        except Exception:
            min_sim = 0.78
        try:
            min_tok = float(os.getenv("NICE_FUZZY_MIN_TOKEN_J", "0.15") or "0.15")
        except Exception:
            min_tok = 0.15

        candidates_to_try = [key, cleaned, key_en]
        if korean_name:
            candidates_to_try.append(korean_name)
            candidates_to_try.append(self.clean_company_name(korean_name))
        nice_keys = list(nice.keys())
        for cand in candidates_to_try:
            if not cand or len(cand) < 2:
                continue
            matches = difflib.get_close_matches(cand, nice_keys, n=1, cutoff=cutoff)
            if matches:
                # “안 맞는 것 같은” 퍼지 매칭은 취소 (값 채우지 않음)
                sim = _string_similarity(cand, matches[0])
                tok = _token_jaccard(cand, matches[0])
                if sim < min_sim and tok < min_tok:
                    continue
                return EmployeeCountEvidence(
                    value=nice[matches[0]],
                    source=EMP_SOURCE_NICE_DB,
                    source_tier=EMP_TIER_HIGH,
                    method="NICE_FUZZY",
                    evidence=f"NICE DB fuzzy match ({cand[:30]}... -> {matches[0][:30]}...) [sim={sim:.2f}, tokJ={tok:.2f}]",
                    url="",
                )
        return None

    def resolve_employee_count_from_web_evidence(
        self, website_domain_or_url: str, company_website_url: str = "", company_name: str = "", country_hint: str = ""
    ) -> List[EmployeeCountEvidence]:
        """웹 크롤링으로 직원수 추출(공식 + 오픈웹). 단일 숫자만 수용. 출처 등급·URL 기록."""
        if not website_domain_or_url:
            return []
        out: List[EmployeeCountEvidence] = []
        try:
            from .web_crawler import WebCrawler
            crawler = WebCrawler(timeout=5)
            meta = crawler.fetch_site_metadata(website_domain_or_url)
            emp_raw = meta.get("employees")
            if not emp_raw:
                emp_raw = None
            emp_str = str(emp_raw).strip()
            if emp_raw:
                ok, _ = validate_employee_count_value(emp_str)
                if ok:
                    try:
                        val = str(int(float(emp_str)))
                        url = meta.get("website") or company_website_url or ""
                        source, tier = classify_employee_count_source(url, "OFFICIAL_WEBSITE")
                        out.append(
                            EmployeeCountEvidence(
                                value=val,
                                source=source,
                                source_tier=tier,
                                method="TEXT_BLOCK_REGEX",
                                evidence=f'Extracted from official site text: "{emp_str}"',
                                url=url or "",
                            )
                        )
                    except Exception:
                        pass
            # 공식 사이트 메인에서 못 찾으면 /about, /company 경로 추가 수집
            if not out and company_website_url:
                try:
                    base_url = (company_website_url or "").strip()
                    if base_url.startswith("http"):
                        parsed = urlparse(base_url)
                        scheme = parsed.scheme or "https"
                        for path in ["/about", "/about-us", "/company", "/about/company", "/회사소개"]:
                            u = f"{scheme}://{parsed.netloc}{path}"
                            m2 = crawler.fetch_site_metadata(u)
                            emp2 = m2.get("employees")
                            if emp2:
                                ok2, _ = validate_employee_count_value(str(emp2).strip())
                                if ok2:
                                    try:
                                        val2 = str(int(float(str(emp2).strip())))
                                        out.append(
                                            EmployeeCountEvidence(
                                                value=val2,
                                                source=EMP_SOURCE_OFFICIAL_WEBSITE,
                                                source_tier=EMP_TIER_HIGH,
                                                method="TEXT_BLOCK_REGEX_ABOUT",
                                                evidence=f'Extracted from {path}: "{emp2}"',
                                                url=u,
                                            )
                                        )
                                        break
                                    except Exception:
                                        pass
                        if out:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        # 오픈 웹 검색 기반 증거 (환경변수로 on/off)
        # 현재는 속도 이슈로 오픈웹 기능을 기본적으로 막아둠 (DISABLE_OPEN_WEB=1 기본)
        if (
            os.getenv("DISABLE_OPEN_WEB", "1").strip().lower() not in {"1", "true", "yes", "y", "on"}
            and os.getenv("OPEN_WEB_EMPLOYEES", "").strip().lower() in {"1", "true", "yes", "y", "on"}
        ):
            try:
                from .open_web_employee_finder import find_employee_evidence_open_web

                max_results = int(os.getenv("OPEN_WEB_MAX_RESULTS", "6") or "6")
                max_fetch = int(os.getenv("OPEN_WEB_MAX_FETCH", "3") or "3")
                official_dom = ""
                try:
                    if company_website_url:
                        official_dom = urlparse(company_website_url).netloc.lower()
                        official_dom = official_dom.replace("www.", "")
                except Exception:
                    official_dom = ""
                web_evs = find_employee_evidence_open_web(
                    company_name=company_name or "",
                    country_hint=country_hint or None,
                    official_domain_hint=official_dom or None,
                    max_search_results=max_results,
                    max_pages_to_fetch=max_fetch,
                )
                for we in web_evs:
                    ok, _ = validate_employee_count_value(we.value_raw)
                    if not ok:
                        continue
                    try:
                        val = str(int(float(we.value_raw)))
                    except Exception:
                        continue
                    src, tier = classify_employee_count_source(we.url, "")
                    out.append(
                        EmployeeCountEvidence(
                            value=val,
                            source=src,
                            source_tier=tier,
                            method=we.method,
                            evidence=f'{we.page_title} | {we.snippet}'.strip(" |"),
                            url=we.url,
                        )
                    )
            except Exception:
                pass

        return out

    def process_lead(self, row: pd.Series) -> Dict:
        """
        단일 리드 데이터 처리 및 보강
        
        Args:
            row: 리드 데이터 행
            
        Returns:
            보강된 리드 데이터 딕셔너리
        """
        # 원본 데이터 복사
        enriched = row.to_dict()
        
        # 회사명 정제
        company_name = str(row.get('Company name', '')).strip()
        cleaned_name = self.clean_company_name(company_name)
        
        # 이메일 도메인 추출
        email = row.get('Work email', '')
        email_domain = self.extract_email_domain(email)
        
        # Industry 힌트 추출
        industry_hint = row.get('Industry', '')
        
        # DART API로 기업 정보 조회
        # 전략: enrich_company_data 내부에서 1차 도메인 크롤링 → 2차 회사명 검색 자동 수행
        dart_info = None
        if (cleaned_name or email_domain) and os.getenv("SKIP_DART", "").strip().lower() not in {"1", "true", "yes", "y", "on"}:
            dart_info = self.dart_client.enrich_company_data(
                cleaned_name if cleaned_name else '',
                email_domain=email_domain,
                industry_hint=industry_hint if industry_hint else None
            )
        
        # 보강 데이터 추가
        if dart_info:
            enriched['DART_Corp_Name'] = dart_info.get('corp_name', '')
            enriched['DART_Address'] = dart_info.get('adres', '')
            enriched['DART_Website'] = dart_info.get('hmurl', '')
            enriched['DART_KSIC_Code'] = dart_info.get('induty_code', '')
            enriched['Match_Count'] = dart_info.get('match_count', 0)
            enriched['Search_Method'] = dart_info.get('search_method', 'company_name')
        else:
            enriched['DART_Corp_Name'] = ''
            enriched['DART_Address'] = ''
            enriched['DART_Website'] = ''
            enriched['DART_KSIC_Code'] = ''
            enriched['Match_Count'] = 0
            enriched['Search_Method'] = 'none'

        # 출력에 필요한 컬럼 4개를 항상 포함 + 비어 있으면 채우기
        def _safe_str(v) -> str:
            if v is None:
                return ""
            try:
                if pd.isna(v):
                    return ""
            except Exception:
                pass
            return str(v).strip()

        # Ensure columns exist + normalize NaN to ""
        enriched["Industry"] = _safe_str(enriched.get("Industry")) or _safe_str(row.get("Industry", ""))
        enriched["Website"] = _safe_str(enriched.get("Website")) or _safe_str(row.get("Website", ""))
        enriched["No of Employees"] = _safe_str(enriched.get("No of Employees")) or _safe_str(row.get("No of Employees", ""))
        enriched["Description"] = _safe_str(enriched.get("Description")) or _safe_str(row.get("Description", ""))

        # 입력이 기본값/범위면 비어 있는 걸로 간주 → AI·크롤링으로 덮어쓸 것
        def _is_placeholder_employees(v: str) -> bool:
            if not v:
                return True
            v = v.strip().lower()
            if v in ("unknown", "n/a", "-", "—"):
                return True
            # 범위 형식(1-10, 51-200 등)이면 실제 숫자가 아님
            if re.search(r"^\d+\s*-\s*\d+", v) or re.search(r"^\d+\+", v):
                return True
            return False

        def _is_placeholder_desc(v: str) -> bool:
            if not v:
                return True
            v = v.strip().lower()
            return v in ("not available", "n/a", "na", "-", "—")

        if _is_placeholder_desc(enriched.get("Description") or ""):
            enriched["Description"] = ""
        # Industry는 API(processor_service)에서 무조건 Gemini로 채움. 여기서 Other 넣지 않음.
        if (enriched.get("Industry") or "").strip().lower() in ("other", "n/a", ""):
            enriched["Industry"] = ""

        # Website: 오버라이드(CSV) → DART → 이메일 도메인 → AI 추론(검증 후) 순으로 채움.
        if not _safe_str(enriched.get("Website")):
            overrides = _load_website_overrides()
            if overrides:
                key = (company_name or "").strip()
                if key and key in overrides:
                    enriched["Website"] = overrides[key]
                if not _safe_str(enriched.get("Website")):
                    key_norm = _normalize_for_lookup(company_name or "")
                    if key_norm and key_norm in overrides:
                        enriched["Website"] = overrides[key_norm]
        if not _safe_str(enriched.get("Website")):
            dart_site = _safe_str(enriched.get("DART_Website"))
            if dart_site:
                enriched["Website"] = dart_site
            elif email_domain:
                free = {
                    "gmail.com", "googlemail.com", "naver.com", "hanmail.net", "daum.net",
                    "outlook.com", "hotmail.com", "live.com", "icloud.com", "yahoo.com", "yahoo.co.kr",
                    "maver.com", "nate.com", "kakao.com", "kakao.co.kr",
                }
                if email_domain.lower() not in free:
                    enriched["Website"] = f"https://{email_domain.lower()}"
            if not _safe_str(enriched.get("Website")) and company_name:
                try:
                    from .gemini_client import GeminiClient
                    gc = GeminiClient()
                    country_hint = _safe_str(row.get("Country") or row.get("Country code") or "")
                    inferred_url = gc.infer_company_website(
                        company_name=company_name,
                        description=_safe_str(enriched.get("Description")),
                        country=country_hint or None,
                    )
                    # AI 추론 URL은 실제 접속 가능할 때만 사용 (없는 사이트 방지)
                    if inferred_url and _url_exists(inferred_url):
                        enriched["Website"] = inferred_url
                except Exception:
                    pass

        # 직원수: 증거 기반 다중 소스 수집 → 1건 선택 → 출처·등급·근거 저장
        evidences: List[EmployeeCountEvidence] = []
        orig_ev = self.resolve_employee_count_from_original(row, enriched)
        if orig_ev:
            evidences.append(orig_ev)
        nice_ev = self.resolve_employee_count_from_nice(company_name)
        if nice_ev:
            evidences.append(nice_ev)
        web_seed = self.extract_website_domain(_safe_str(enriched.get("Website"))) or email_domain or ""
        web_evs = self.resolve_employee_count_from_web_evidence(
            web_seed,
            _safe_str(enriched.get("Website", "")),
            company_name=company_name,
            country_hint=_safe_str(row.get("Country") or row.get("Country code") or ""),
        )
        evidences.extend(web_evs)
        best = select_best_employee_count_evidence(evidences)
        if best:
            enriched["No of Employees"] = best.value
            enriched["Employee_Count_Source"] = best.source
            enriched["Employee_Count_Source_Tier"] = best.source_tier
            enriched["Employee_Count_Match_Method"] = best.method
            enriched["Employee_Count_Evidence"] = best.evidence
            enriched["Employee_Count_Status"] = EMP_STATUS_ACCEPTED
            enriched["Employee_Count_Source_URL"] = best.url or ""
        else:
            enriched["No of Employees"] = ""
            enriched["Employee_Count_Source"] = EMP_SOURCE_EMPTY
            enriched["Employee_Count_Source_Tier"] = ""
            enriched["Employee_Count_Match_Method"] = ""
            enriched["Employee_Count_Evidence"] = ""
            enriched["Employee_Count_Status"] = EMP_STATUS_NOT_FOUND
            enriched["Employee_Count_Source_URL"] = ""

        # Description(비어 있을 때만): 크롤링으로 채움
        try:
            from .web_crawler import WebCrawler
            crawler = WebCrawler(timeout=5)
            seed = self.extract_website_domain(_safe_str(enriched.get("Website"))) or email_domain or ""
            meta = crawler.fetch_site_metadata(seed)
            if not _safe_str(enriched.get("Description")) and meta.get("description"):
                enriched["Description"] = _safe_str(meta.get("description"))
        except Exception:
            pass
        
        # 웹사이트 도메인 추출
        website_domain = None
        if enriched.get('DART_Website'):
            website_domain = self.extract_website_domain(enriched['DART_Website'])
        
        # 신뢰도 점수 계산
        confidence = self.calculate_confidence_score(
            dart_info, email_domain, website_domain
        )
        enriched['Confidence_Score'] = confidence
        
        # 검토 상태 설정
        if confidence == 'High':
            enriched['Review_Status'] = 'Approved'
        else:
            enriched['Review_Status'] = 'Needs Review'
        
        return enriched
    
    def process_csv(self, input_path: str, output_path: str) -> pd.DataFrame:
        """
        CSV 파일 일괄 처리
        
        Args:
            input_path: 입력 CSV 파일 경로
            output_path: 출력 CSV 파일 경로
            
        Returns:
            보강된 데이터프레임
        """
        print(f"CSV 파일 로드 중: {input_path}")
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        
        print(f"총 {len(df)}건의 리드 데이터 처리 시작...")
        
        enriched_rows = []
        for idx, row in df.iterrows():
            print(f"[{idx + 1}/{len(df)}] 처리 중: {row.get('Company name', 'N/A')}")
            
            try:
                enriched_row = self.process_lead(row)
                enriched_rows.append(enriched_row)
            except Exception as e:
                print(f"  오류 발생: {str(e)}")
                # 오류 발생 시 원본 데이터 유지
                enriched_rows.append(row.to_dict())
        
        # 결과 데이터프레임 생성
        enriched_df = pd.DataFrame(enriched_rows)
        
        # 결과 저장
        enriched_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"\n처리 완료! 결과 저장: {output_path}")
        
        # 통계 출력
        print("\n=== 처리 통계 ===")
        print(f"총 처리 건수: {len(enriched_df)}")
        print(f"High 신뢰도: {len(enriched_df[enriched_df['Confidence_Score'] == 'High'])}건")
        print(f"Medium 신뢰도: {len(enriched_df[enriched_df['Confidence_Score'] == 'Medium'])}건")
        print(f"Low 신뢰도: {len(enriched_df[enriched_df['Confidence_Score'] == 'Low'])}건")
        
        return enriched_df
