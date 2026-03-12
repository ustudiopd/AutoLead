"""
오픈 웹 검색 기반 직원수(evidence) 수집.

- 목적: "공식/비공식"이 아니라 "실제 페이지에 명시된 단일 숫자"만 수집.
- 금지: LLM으로 숫자 생성/추정. 범위/추정 표현 수집 금지(검증은 호출 측에서 수행).

구현 메모:
- 외부 검색 API 키 없이도 동작시키기 위해 DuckDuckGo HTML 엔드포인트를 사용.
- 차단/레이트리밋 가능성이 있어 best-effort이며, 실패해도 파이프라인은 계속 진행되어야 함.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import os
import time
import threading


@dataclass
class WebEmployeeEvidence:
    value_raw: str
    url: str
    page_title: str
    snippet: str
    method: str


_openweb_kr_name_cache: dict[str, Optional[str]] = {}
_openweb_kr_name_lock = threading.Lock()


def _has_korean(s: str) -> bool:
    try:
        return any("가" <= ch <= "힣" for ch in (s or ""))
    except Exception:
        return False


def _safe_text(s: object) -> str:
    if s is None:
        return ""
    try:
        return str(s).strip()
    except Exception:
        return ""


def _is_http_url(u: str) -> bool:
    return bool(u) and (u.startswith("http://") or u.startswith("https://"))


def _domain(u: str) -> str:
    try:
        return (urlparse(u).netloc or "").lower()
    except Exception:
        return ""


def _norm_lookup(s: str) -> str:
    """회사명/도메인 비교를 위한 단순 정규화(영숫자만 + 공백 정리)."""
    try:
        import re
        t = _safe_text(s).lower()
        t = re.sub(r"[^0-9a-z가-힣]+", " ", t)
        t = " ".join(t.split())
        return t
    except Exception:
        return ""


def _resolve_ddg_redirect_url(href: str) -> Optional[str]:
    """DuckDuckGo /l/?uddg=실제URL 에서 실제 URL 추출."""
    if not href or not str(href).strip().startswith("http"):
        return None
    href = str(href).strip()
    if "duckduckgo.com/l/" in href and "uddg=" in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            uddg = (qs.get("uddg") or [None])[0]
            if uddg:
                return unquote(uddg)
        except Exception:
            pass
    return href if href.startswith("http") else None


def _fetch(url: str, timeout: int = 6) -> str:
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoLead/1.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }
    try:
        timeout = int(os.getenv("OPEN_WEB_HTTP_TIMEOUT", str(timeout)) or timeout)
    except Exception:
        pass
    r = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _fetch_rendered_text_playwright(url: str, timeout_sec: int = 8) -> str:
    """
    JS 렌더링이 필요한 페이지를 위해 Playwright로 렌더링된 텍스트를 가져온다.
    - 기본 OFF(환경변수로 활성화)
    - 실패해도 파이프라인을 중단하지 않도록 호출부에서 예외를 삼키는 형태로 사용
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(max(1000, int(timeout_sec * 1000)))
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=max(1000, int(timeout_sec * 1000)))
            except Exception:
                pass
            txt = page.inner_text("body")
            return " ".join((txt or "").split())
        finally:
            try:
                browser.close()
            except Exception:
                pass


def _ddg_search(query: str, max_results: int = 5, timeout: int = 8) -> List[Tuple[str, str, str]]:
    """
    DuckDuckGo HTML 검색 결과에서 (url, title, snippet) 리스트 반환.
    """
    try:
        html = _fetch(f"https://duckduckgo.com/html/?q={quote_plus(query)}", timeout=timeout)
    except Exception:
        return []

    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, str, str]] = []
    seen_urls: set[str] = set()

    def add_result(url: str, title: str, snippet: str) -> None:
        real = _resolve_ddg_redirect_url(url)
        if not real or real in seen_urls:
            return
        if "duckduckgo.com" in (urlparse(real).netloc or "").lower():
            return
        seen_urls.add(real)
        out.append((real, title, snippet))

    # 1) 기존 선택자 (DDG 결과 블록)
    for res in soup.select("div.result"):
        a = res.select_one("a.result__a")
        if not a:
            continue
        url = _safe_text(a.get("href"))
        title = _safe_text(a.get_text(" "))
        sn = res.select_one("a.result__snippet") or res.select_one("div.result__snippet")
        snippet = _safe_text(sn.get_text(" ")) if sn else ""
        add_result(url, title, snippet)
        if len(out) >= max_results:
            return out

    # 2) DDG가 링크를 /l/?uddg= 로 감싼 경우: 모든 a[href*="uddg="] 에서 실제 URL 추출
    if len(out) < max_results:
        for a in soup.find_all("a", href=True):
            href = _safe_text(a.get("href"))
            if "uddg=" not in href:
                continue
            title = _safe_text(a.get_text(" "))
            add_result(href, title, "")
            if len(out) >= max_results:
                break

    return out


def _extract_employee_mentions(page_text: str) -> List[str]:
    """
    페이지 텍스트에서 직원수 후보 문자열 리스트를 추출.
    영/한/표 형태 등 다양한 표현 수집. 범위·추정 거부는 호출 측에서 수행.
    """
    import re

    t = " ".join((page_text or "").split())
    if not t:
        return []

    candidates: List[str] = []

    def _clean_num(x: str) -> Optional[str]:
        if not x:
            return None
        s = str(x).strip().replace(",", "")
        if not re.fullmatch(r"\d{1,9}", s):
            return None
        # 너무 큰 값은 직원수로 보기 어려움(안전장치)
        try:
            n = int(s)
            if n <= 0 or n >= 1000000:
                return None
        except Exception:
            return None
        return s

    # 키워드 근처 단일 숫자(1~6자리). 영문·한글·혼용 확장
    # 주의: 잡코리아 등에서 1,234 형태(콤마 포함)가 흔해 콤마 허용
    patterns = [
        r"(employees|employee|staff|headcount|workforce)\s*[:\-]?\s*([\d,]{1,9})",
        r"([\d,]{1,9})\s*(employees|employee|staff|headcount|people)\b",
        r"(number of employees|company size|team size)\s*[:\-]?\s*([\d,]{1,9})",
        r"(종업원수|직원\s*수|임직원\s*수|사원\s*수|사원수)\s*[:\-]?\s*([\d,]{1,9})",
        r"([\d,]{1,9})\s*명\s*(직원|임직원|종업원|사원)?\b",
        r"(전체\s*인원|인력\s*규모|회사\s*규모)\s*[:\-]?\s*([\d,]{1,9})",
        r"([\d,]{1,9})\s*(명|인|people)\b",
        r"(인력|종업원)\s*[:\-]?\s*([\d,]{1,9})\s*명",
        r"([\d,]{1,9})\s*여\s*명\s*(직원|임직원)?",
        r"about\s+([\d,]{1,9})\s+(employees|staff)\b",
        r"([\d,]{1,9})\s*\+?\s*(employees|staff)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, t, flags=re.IGNORECASE):
            nums = []
            for g in m.groups():
                if not g:
                    continue
                cn = _clean_num(str(g))
                if cn:
                    nums.append(cn)
            if nums:
                candidates.append(nums[0])

    # 중복 제거(순서 유지)
    seen = set()
    uniq: List[str] = []
    for c in candidates:
        if c not in seen:
            uniq.append(c)
            seen.add(c)
    return uniq


def _extract_jobkorea_employee_count(html: str) -> Optional[str]:
    """
    잡코리아 기업정보 페이지에서 '사원수 25명' 같은 명시값 추출.
    (JS 렌더링이 아닌 정적 텍스트에 포함되는 케이스를 우선 지원)
    """
    if not html:
        return None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = " ".join(str(html).split())
    import re
    m = re.search(r"사원수\s*([\d,]{1,9})\s*명", text)
    if not m:
        return None
    raw = m.group(1)
    raw = raw.replace(",", "").strip()
    if not re.fullmatch(r"\d{1,9}", raw):
        return None
    try:
        n = int(raw)
        if n <= 0 or n >= 1000000:
            return None
    except Exception:
        return None
    return str(n)


def _urls_from_web_crawler_search(company_name: str, country_hint: Optional[str], max_results: int) -> List[str]:
    """DDG 실패 시 WebCrawler.search_web 폴백."""
    try:
        from .web_crawler import WebCrawler
        c = WebCrawler(timeout=8)
        q = f"{_safe_text(company_name)} employees"
        if country_hint:
            q += f" {_safe_text(country_hint)}"
        return c.search_web(q, max_results=max_results)
    except Exception:
        return []


def find_employee_evidence_open_web(
    company_name: str,
    country_hint: Optional[str] = None,
    official_domain_hint: Optional[str] = None,
    max_search_results: int = 14,
    max_pages_to_fetch: int = 8,
) -> List[WebEmployeeEvidence]:
    """
    오픈 웹에서 직원수 후보를 찾아 evidence로 반환.
    검색 쿼리 다변화 + DDG 실패 시 WebCrawler 검색 폴백.
    """
    name = _safe_text(company_name)
    if not name:
        return []

    started = time.monotonic()
    try:
        budget_sec = float(os.getenv("OPEN_WEB_TIME_BUDGET_SEC", "8") or "8")
        budget_sec = max(1.0, min(30.0, budget_sec))
    except Exception:
        budget_sec = 8.0

    # 검색 쿼리 다변화 (영/한 + 회사소개/about us)
    ch = _safe_text(country_hint) if country_hint else ""
    queries = [
        f"{name} employees",
        f"{name} company size workforce",
        f"{name} staff headcount",
        f"{name} 종업원 인력",
        f"{name} 직원 수",
        f"{name} 잡코리아 사원수",
        f"{name} 사람인 사원수",
        f"{name} 잡플래닛 직원수",
        f"{name} 인크루잇 직원수",
        f"{name} jobkorea employees",
        f"{name} saramin employees",
        f"{name} jobplanet employees",
        f"{name} incruit employees",
        f"{name} about us company",
        f"{name} 회사소개 기업정보",
        f"{name} company profile",
    ]
    if ch:
        queries = [f"{q} {ch}" for q in queries] + queries

    results: List[Tuple[str, str, str]] = []
    seen_urls: set[str] = set()

    # 0) 잡코리아는 외부 검색엔진이 불안정할 수 있어, 내부 검색으로 기업정보 URL을 먼저 후보로 넣는다.
    try:
        jk_first = os.getenv("OPEN_WEB_JOBKOREA_INTERNAL_SEARCH", "1").strip().lower() in {"1", "true", "yes", "y", "on"}
    except Exception:
        jk_first = True
    name_for_jobkorea_match = name
    if jk_first:
        try:
            from .portal_scrapers.jobkorea import search_company_pages

            try:
                jk_timeout = int(os.getenv("OPEN_WEB_HTTP_TIMEOUT", "6") or "6")
            except Exception:
                jk_timeout = 6

            jk_urls = search_company_pages(name, timeout=jk_timeout, max_results=3)

            # 영문 표기 회사는 잡코리아 내부검색이 안 잡히는 경우가 많아서 KR 힌트가 있으면 한글명 추정 후 재시도
            if not jk_urls and (country_hint or "").upper().startswith("KR") and not _has_korean(name):
                try:
                    allow_kr = os.getenv("OPEN_WEB_ALLOW_GEMINI_KR", "1").strip().lower() in {"1", "true", "yes", "y", "on"}
                except Exception:
                    allow_kr = True
                if allow_kr:
                    with _openweb_kr_name_lock:
                        cached = _openweb_kr_name_cache.get(name)
                    kr_name = cached
                    if kr_name is None:
                        try:
                            from .gemini_client import GeminiClient
                            gc = GeminiClient()
                            kr_name = gc.infer_korean_company_name(name)
                        except Exception:
                            kr_name = None
                        with _openweb_kr_name_lock:
                            _openweb_kr_name_cache[name] = kr_name
                    if kr_name:
                        name_for_jobkorea_match = kr_name
                        jk_urls = search_company_pages(kr_name, timeout=jk_timeout, max_results=3)

            for u in jk_urls:
                if u not in seen_urls:
                    seen_urls.add(u)
                    results.append((u, "JOBKOREA_INTERNAL_SEARCH", ""))
        except Exception:
            pass

    # URL을 이미 알고 있는 경우(예: 잡코리아 링크를 사용자가 제공) 강제 주입
    direct_url = (os.getenv("OPEN_WEB_DIRECT_URL", "") or "").strip()
    direct_for = (os.getenv("OPEN_WEB_DIRECT_URL_FOR", "") or "").strip()
    if direct_url and _is_http_url(direct_url):
        if direct_for:
            # 지정된 회사명(부분문자열)일 때만 direct URL 적용
            if _norm_lookup(direct_for) not in _norm_lookup(name):
                direct_url = ""
    if direct_url and _is_http_url(direct_url):
        results.append((direct_url, "DIRECT_URL", ""))
        seen_urls.add(direct_url)
        # direct URL이 있으면 검색 엔진 의존을 피하고 빠르게 해당 페이지만 처리
        # (검색 단계가 환경에 따라 매우 느려질 수 있음)
        max_search_results = 0

    # 1) WebCrawler.search_web(DDGS)을 먼저 실행해 실제 URL 확보 (DDG HTML은 차단 시 0건)
    try:
        from .web_crawler import WebCrawler
        try:
            wc_timeout = int(os.getenv("OPEN_WEB_SEARCH_TIMEOUT", "4") or "4")
        except Exception:
            wc_timeout = 4
        if max_search_results <= 0 or (time.monotonic() - started) > budget_sec:
            raise Exception("skip_search")

        c = WebCrawler(timeout=wc_timeout)
        base_queries = [f"{name} employees", f"{name} company size", f"{name} headcount", f"{name} 종업원 인력"]

        # 디렉토리 도메인만 강제 검색(site:)해서 "읽을 수 있게" 락인 (URL 공유 없이도 동작)
        lockin_dirs = os.getenv("OPEN_WEB_LOCKIN_DIRECTORIES", "1").strip().lower() in {"1", "true", "yes", "y", "on"}
        if lockin_dirs:
            dir_domains = ["jobkorea.co.kr", "saramin.co.kr", "jobplanet.co.kr", "incruit.com"]
            forced = []
            for d in dir_domains:
                forced.append(f"site:{d} {name} 사원수")
                forced.append(f"site:{d} {name} 직원수")
                forced.append(f"site:{d} {name} company employees")
            base_queries = forced + base_queries

        for q in base_queries:
            if (time.monotonic() - started) > budget_sec:
                break
            for u in c.search_web(q, max_results=max_search_results):
                if u not in seen_urls:
                    seen_urls.add(u)
                    results.append((u, "", ""))
            if len(results) >= max_search_results * 2:
                break
    except Exception:
        pass

    # 1.5) 잡코리아/사람인/잡플래닛/인크루잇 도메인을 우선으로 당기기 (락인)
    preferred = ("jobkorea.co.kr", "saramin.co.kr", "jobplanet.co.kr", "incruit.com")
    try:
        results.sort(
            key=lambda x: (
                0 if any(d in _domain(x[0]) for d in preferred) else 1,
                len(x[0] or ""),
            )
        )
    except Exception:
        pass

    # 2) DDG HTML 검색으로 제목/스니펫 보강 (있으면 병합)
    # direct URL 모드(max_search_results<=0)에서는 검색 단계 자체를 건너뜀(속도/안정성)
    if max_search_results > 0:
        for q in queries:
            if (time.monotonic() - started) > budget_sec:
                break
            part = _ddg_search(q, max_results=max_search_results, timeout=10)
            for url, title, snippet in part:
                if url not in seen_urls:
                    seen_urls.add(url)
                    results.append((url, title, snippet))
            if len(results) >= max_search_results * 3:
                break

    # 3) 공식 도메인 있으면 about/company 경로를 최우선 후보로 추가
    if official_domain_hint:
        base = official_domain_hint.lower().replace("www.", "").strip()
        if base and not base.startswith("http"):
            for path in ["/about", "/about-us", "/company", "/회사소개", "/about/company"]:
                u = f"https://{base}{path}"
                if u not in seen_urls:
                    seen_urls.add(u)
                    results.insert(0, (u, "", ""))
            for path in ["/about", "/company"]:
                u = f"https://www.{base}{path}"
                if u not in seen_urls:
                    seen_urls.add(u)
                    results.insert(0, (u, "", ""))

    evidences: List[WebEmployeeEvidence] = []
    # 검색 결과 스니펫/제목에서 직원수 추출 (페이지 fetch 없이)
    for url, title, snippet in results:
        if (time.monotonic() - started) > budget_sec:
            break
        combined = f"{title} {snippet}"
        for v in _extract_employee_mentions(combined):
            evidences.append(WebEmployeeEvidence(value_raw=v, url=url, page_title=title[:200] or "", snippet=(snippet or "")[:300], method="OPEN_WEB_SNIPPET"))

    fetched = 0
    for url, title, snippet in results:
        if fetched >= max_pages_to_fetch:
            break
        if (time.monotonic() - started) > budget_sec:
            break
        dom = _domain(url)
        if dom and official_domain_hint and dom.replace("www.", "").endswith(official_domain_hint.lower().replace("www.", "")):
            method = "OPEN_WEB_SEARCH_OFFICIAL"
        else:
            method = "OPEN_WEB_SEARCH"

        try:
            html = _fetch(url, timeout=9)
            fetched += 1
        except Exception:
            continue

        # 잡코리아 내부검색은 후보가 섞일 수 있어, 페이지 자체가 회사와 무관하면 아예 스킵한다.
        if "jobkorea.co.kr" in _domain(url):
            try:
                from bs4 import BeautifulSoup
                page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            except Exception:
                page_text = ""
            # 영문 회사명은 페이지에 그대로 안 나오는 케이스가 많아(한글 표기) 잡코리아 내부검색에서 한글명을 추정했다면 그걸 우선 사용
            base_for_match = name_for_jobkorea_match if name_for_jobkorea_match else name
            tokens = [t for t in _norm_lookup(base_for_match).split(" ") if len(t) >= 3]
            if tokens and page_text:
                pn = _norm_lookup(page_text)
                if not any(t in pn for t in tokens[:4]):
                    continue

        # 잡코리아는 정적 텍스트에 '사원수 N명'이 노출되는 케이스가 있어 전용 파서 우선 적용
        try:
            if "jobkorea.co.kr" in _domain(url):
                jk = _extract_jobkorea_employee_count(html)
                if jk:
                    evidences.append(
                        WebEmployeeEvidence(
                            value_raw=str(jk),
                            url=url,
                            page_title=title[:200] if title else "",
                            snippet="jobkorea: 사원수",
                            method="OPEN_WEB_JOBKOREA",
                        )
                    )
                    # 전용 파서가 성공하면 추가 파싱은 생략
                    continue
        except Exception:
            pass

        # 잡코리아(및 JS-heavy 페이지) 렌더링 폴백: Playwright가 켜져있고, 예산이 남아있을 때만
        try:
            use_pw = os.getenv("OPEN_WEB_USE_PLAYWRIGHT", "0").strip().lower() in {"1", "true", "yes", "y", "on"}
        except Exception:
            use_pw = False
        if use_pw and (time.monotonic() - started) <= budget_sec and ("jobkorea.co.kr" in _domain(url)):
            try:
                try:
                    pw_timeout = float(os.getenv("OPEN_WEB_PLAYWRIGHT_TIMEOUT_SEC", "8") or "8")
                    pw_timeout = max(2.0, min(20.0, pw_timeout))
                except Exception:
                    pw_timeout = 8.0
                rendered = _fetch_rendered_text_playwright(url, timeout_sec=int(pw_timeout))
                jk2 = _extract_employee_mentions(rendered)
                # 전용 표현(사원수 N명)을 우선
                jk_direct = None
                try:
                    import re as re_mod
                    m = re_mod.search(r"사원수\s*([\d,]{1,9})\s*명", rendered)
                    if m:
                        jk_direct = m.group(1)
                except Exception:
                    jk_direct = None
                if jk_direct:
                    jk_direct = jk_direct.replace(",", "").strip()
                    if jk_direct.isdigit():
                        evidences.append(
                            WebEmployeeEvidence(
                                value_raw=str(int(jk_direct)),
                                url=url,
                                page_title=title[:200] if title else "",
                                snippet="jobkorea: 사원수 (playwright)",
                                method="OPEN_WEB_JOBKOREA",
                            )
                        )
                        continue
                for v in jk2[:2]:
                    evidences.append(
                        WebEmployeeEvidence(
                            value_raw=v,
                            url=url,
                            page_title=title[:200] if title else "",
                            snippet="jobkorea: rendered (playwright)",
                            method="OPEN_WEB_JOBKOREA",
                        )
                    )
            except Exception:
                pass

        try:
            from bs4 import BeautifulSoup
            import json
            import re as re_mod
            soup = BeautifulSoup(html, "html.parser")
            # 1) JSON-LD / 메타에서 직원수 추출 (단일 숫자만)
            for script in soup.select("script[type='application/ld+json']"):
                try:
                    data = json.loads(script.get_text("", strip=True))
                    if isinstance(data, dict) and "numberOfEmployees" in data:
                        n = data["numberOfEmployees"]
                        if isinstance(n, (int, float)) and 0 < n < 1000000:
                            evidences.append(WebEmployeeEvidence(value_raw=str(int(n)), url=url, page_title=title[:200] or "", snippet="JSON-LD numberOfEmployees", method=method))
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "numberOfEmployees" in item:
                                n = item["numberOfEmployees"]
                                if isinstance(n, (int, float)) and 0 < n < 1000000:
                                    evidences.append(WebEmployeeEvidence(value_raw=str(int(n)), url=url, page_title=title[:200] or "", snippet="JSON-LD numberOfEmployees", method=method))
                                    break
                except Exception:
                    pass
            # 메타 프로퍼티 (일부 사이트)
            for meta in soup.select("meta[property='og:numberOfEmployees'], meta[name='numberOfEmployees']"):
                c = (meta.get("content") or "").strip()
                if re_mod.fullmatch(r"\d{1,6}", c) and 0 < int(c) < 1000000:
                    evidences.append(WebEmployeeEvidence(value_raw=c, url=url, page_title=title[:200] or "", snippet="meta numberOfEmployees", method=method))
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            text = " ".join(text.split())
        except Exception:
            text = ""

        for v in _extract_employee_mentions(text):
            evidences.append(
                WebEmployeeEvidence(
                    value_raw=v,
                    url=url,
                    page_title=title[:200] if title else "",
                    snippet=(snippet or "")[:300],
                    method=method,
                )
            )

    return evidences

