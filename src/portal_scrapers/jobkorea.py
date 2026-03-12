from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote_plus, urlparse
import re

import requests


@dataclass
class JobKoreaSearchResult:
    url: str
    title: str = ""


def _safe_text(x: object) -> str:
    if x is None:
        return ""
    try:
        return str(x).strip()
    except Exception:
        return ""


def _is_http_url(u: str) -> bool:
    return bool(u) and (u.startswith("http://") or u.startswith("https://"))


def _domain(u: str) -> str:
    try:
        return (urlparse(u).netloc or "").lower()
    except Exception:
        return ""


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoLead/1.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
        }
    )
    return s


def search_company_pages(company_name: str, timeout: int = 6, max_results: int = 3) -> List[str]:
    """
    잡코리아 내부 검색으로 기업정보 URL(`/recruit/co_read/c/<slug>`) 후보를 찾는다.
    - 외부 검색 엔진(DDG)에 의존하지 않아서 더 안정적인 편.
    - 페이지 구조 변경/차단 시 실패할 수 있으므로 best-effort.
    """
    name = _safe_text(company_name)
    if not name:
        return []

    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []

    s = _make_session()

    # 잡코리아 통합검색 페이지(비공식). 실패해도 파이프라인은 계속 가야 함.
    # 회사명 표기가 영문/기호를 포함하면 검색이 안 되는 경우가 있어 쿼리를 몇 가지 변형해 시도한다.
    def _normalize_query(q: str) -> str:
        t = _safe_text(q)
        t = re.sub(r"[^0-9a-zA-Z가-힣]+", " ", t)
        t = " ".join(t.split())
        return t

    norm = _normalize_query(name)
    # 흔한 법인 접미어 제거
    norm2 = " ".join([t for t in norm.split() if t.lower() not in {"co", "ltd", "inc", "corp", "co.,ltd", "limited"}])
    compact = re.sub(r"[^0-9a-zA-Z가-힣]+", "", name)
    # 슬러그 추정(영문 토큰을 이어붙이기): KB-ELEMENT.Co.,Ltd -> kbelement
    ascii_tokens = [t.lower() for t in norm.split() if re.fullmatch(r"[0-9a-zA-Z]{1,30}", t)]
    ascii_tokens = [t for t in ascii_tokens if t not in {"co", "ltd", "inc", "corp", "limited"}]
    slug_guess = "".join(ascii_tokens[:4]) if ascii_tokens else ""

    query_candidates = [name, norm, norm2, compact, slug_guess]
    query_candidates = [q for q in query_candidates if _safe_text(q)]

    # 검색이 잘 안 먹는 영문 회사의 경우, 슬러그 추정 URL을 후보로 먼저 제공(존재 여부는 호출부에서 fetch로 검증)
    guessed_urls: List[str] = []
    if slug_guess and re.fullmatch(r"[a-z0-9_-]{2,80}", slug_guess):
        guessed_urls.append(f"https://www.jobkorea.co.kr/recruit/co_read/c/{slug_guess}")
        if len(guessed_urls) >= max_results:
            return guessed_urls[:max_results]

    def _extract_urls_from_html(html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        found: List[str] = []
        seen: set[str] = set()

        # 1) a[href]에서 기업정보 패턴을 직접 캐치(있으면 가장 좋음)
        for a in soup.find_all("a", href=True):
            href = _safe_text(a.get("href"))
            if not href:
                continue
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith("/"):
                href = "https://www.jobkorea.co.kr" + href
            if not _is_http_url(href):
                continue
            if "jobkorea.co.kr" not in _domain(href):
                continue
            if "/recruit/co_read/c/" not in href:
                continue
            href = href.split("#", 1)[0]
            if href in seen:
                continue
            seen.add(href)
            found.append(href)
            if len(found) >= max_results:
                return found

        # 2) Next.js/CSR 페이지는 링크가 HTML에 없고, JSON 상태에 memberId가 들어있는 경우가 많음
        member_ids = re.findall(r'\\\"memberId\\\"\\s*:\\s*\\\"([a-zA-Z0-9_-]{2,80})\\\"', html)
        if not member_ids:
            member_ids = re.findall(r'"memberId"\s*:\s*"([a-zA-Z0-9_-]{2,80})"', html)
        if not member_ids:
            member_ids = []
            for m in re.finditer(r"memberId", html):
                seg = html[m.start() : min(len(html), m.start() + 200)]
                m2 = re.search(r"memberId[^a-zA-Z0-9_-]{0,60}([a-zA-Z0-9_-]{2,80})", seg)
                if m2:
                    member_ids.append(m2.group(1))
        for mid in member_ids:
            u = f"https://www.jobkorea.co.kr/recruit/co_read/c/{mid}"
            if u not in seen:
                seen.add(u)
                found.append(u)
                if len(found) >= max_results:
                    return found

        # 3) 혹시 HTML에 URL이 텍스트로만 있는 경우(희박)도 대응
        m = re.findall(r"https?://www\.jobkorea\.co\.kr/recruit/co_read/c/[a-zA-Z0-9_-]+", html)
        for u in m:
            u = _safe_text(u).split("#", 1)[0]
            if u and u not in seen:
                seen.add(u)
                found.append(u)
                if len(found) >= max_results:
                    break
        return found

    for q in query_candidates:
        url = f"https://www.jobkorea.co.kr/Search/?stext={quote_plus(q)}"
        try:
            r = s.get(url, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            html = r.text or ""
            if not html:
                continue
            urls = _extract_urls_from_html(html)
            if urls:
                out = guessed_urls + urls
                # 중복 제거
                uniq: List[str] = []
                seen2: set[str] = set()
                for u in out:
                    if u not in seen2:
                        uniq.append(u)
                        seen2.add(u)
                    if len(uniq) >= max_results:
                        break
                return uniq[:max_results]
        except Exception:
            continue

    return guessed_urls[:max_results]


def extract_employee_count_from_text(text: str) -> Optional[str]:
    """
    렌더링된 텍스트에서 '사원수 N명'을 추출.
    """
    t = " ".join(_safe_text(text).split())
    if not t:
        return None
    m = re.search(r"사원수\s*([\d,]{1,9})\s*명", t)
    if not m:
        return None
    raw = m.group(1).replace(",", "").strip()
    if not re.fullmatch(r"\d{1,9}", raw):
        return None
    try:
        n = int(raw)
        if n <= 0 or n >= 1000000:
            return None
    except Exception:
        return None
    return str(n)
