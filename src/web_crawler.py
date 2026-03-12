"""
웹 크롤러 모듈
이메일 도메인으로 웹사이트를 크롤링하여 회사명 추출
"""
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote
import time


def _resolve_ddg_redirect_url(href: str) -> Optional[str]:
    """
    DuckDuckGo HTML 검색 결과의 링크는 https://duckduckgo.com/l/?uddg=실제URL 형태.
    실제 URL을 추출해 반환. DDG 링크가 아니면 href 그대로 반환.
    """
    if not href or not href.strip().startswith("http"):
        return None
    href = href.strip()
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


class WebCrawler:
    """웹사이트 크롤링을 통한 회사명 추출"""
    
    def __init__(self, timeout: int = 10):
        """
        웹 크롤러 초기화
        
        Args:
            timeout: 요청 타임아웃 (초) - 기본값 10초로 증가
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # 연결 재시도 설정
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def search_web(self, query: str, max_results: int = 5) -> list[str]:
        """
        오픈 웹 검색(간이): DuckDuckGo HTML을 사용해 결과 URL을 수집.
        DDG는 링크를 /l/?uddg=실제URL 로 감싸므로, 실제 URL을 추출해 반환.
        """
        if not query:
            return []
        q = " ".join(str(query).split())
        urls: list[str] = []
        try:
            r = self.session.get(
                "https://duckduckgo.com/html/",
                params={"q": q},
                timeout=self.timeout,
                allow_redirects=True,
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            # 1) 기존 선택자
            for a in soup.select("a.result__a"):
                href = (a.get("href") or "").strip()
                real = _resolve_ddg_redirect_url(href)
                if real:
                    urls.append(real)
            # 2) DDG 리다이렉트 링크가 있으면 모든 a[href*="uddg="] 에서 실제 URL 추출
            if len(urls) < max_results:
                for a in soup.find_all("a", href=True):
                    href = (a.get("href") or "").strip()
                    real = _resolve_ddg_redirect_url(href)
                    if real and real not in urls and not real.startswith("https://duckduckgo.com"):
                        urls.append(real)
                    if len(urls) >= max_results * 3:
                        break
        except Exception:
            return []

        out: list[str] = []
        seen: set[str] = set()
        for u in urls:
            if u in seen or not u.startswith("http"):
                continue
            try:
                dom = urlparse(u).netloc or ""
                if "duckduckgo.com" in dom:
                    continue
            except Exception:
                continue
            seen.add(u)
            out.append(u)
            if len(out) >= max_results:
                break

        # DuckDuckGo/Bing 직접 요청이 실패하면 duckduckgo-search 패키지 사용 (실제 URL 반환)
        if len(out) < max_results:
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    for row in ddgs.text(q, max_results=max_results, region="us-en"):
                        link = (row.get("href") or row.get("link") or "").strip()
                        if link.startswith("http") and link not in seen:
                            try:
                                if "duckduckgo.com" in (urlparse(link).netloc or ""):
                                    continue
                            except Exception:
                                pass
                            seen.add(link)
                            out.append(link)
                            if len(out) >= max_results:
                                break
            except Exception:
                pass

        return out

    def fetch_page_text(self, url: str) -> tuple[str, str]:
        """
        임의 URL 페이지의 텍스트를 가져와 정제.
        Returns:
            (final_url, visible_text)
        """
        if not url or not str(url).strip().startswith("http"):
            return ("", "")
        try:
            r = self.session.get(str(url).strip(), timeout=self.timeout, allow_redirects=True)
            r.raise_for_status()
            final_url = r.url or str(url).strip()
            soup = BeautifulSoup(r.text, "html.parser")
            # 스크립트/스타일 제거
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            text = " ".join(text.split())
            return (final_url, text)
        except Exception:
            return ("", "")

    def extract_employee_count_from_text(self, text: str) -> tuple[Optional[str], str]:
        """
        페이지 텍스트에서 직원수로 보이는 단일 숫자를 추출.
        영/한/다양한 표현 지원. Returns: (value, evidence_snippet)
        """
        if not text:
            return (None, "")
        import re

        t = " ".join(str(text).split())
        patterns = [
            r"(?:employees|employee|staff|headcount|workforce)\s*[:\-]?\s*(\d{1,6})",
            r"(\d{1,6})\s*(?:employees|employee|staff|headcount|people)\b",
            r"(?:number of employees|company size|team size)\s*[:\-]?\s*(\d{1,6})",
            r"(?:임직원|직원\s*수|종업원수|사원\s*수)\s*[:\-]?\s*(\d{1,6})",
            r"(\d{1,6})\s*명\s*(?:임직원|직원|종업원|사원)?\b",
            r"(?:전체\s*인원|인력\s*규모|회사\s*규모)\s*[:\-]?\s*(\d{1,6})",
            r"(\d{1,6})\s*(?:명|인|people)\b",
            r"(?:인력|종업원)\s*[:\-]?\s*(\d{1,6})\s*명",
            r"(?:직원|인원|팀원|멤버)\s*[:\-]?\s*(\d{1,6})\s*명",
            r"(\d{1,6})\s*(?:직원|인원|팀원)\b",
            r"(?:members?|팀\s*구성)\s*[:\-]?\s*(\d{1,6})",
        ]
        for p in patterns:
            m = re.search(p, t, re.IGNORECASE)
            if m:
                val = m.group(1)
                s, e = max(m.start() - 40, 0), min(m.end() + 40, len(t))
                return (val, t[s:e])
        return (None, "")
    
    def extract_company_name_from_domain(self, domain: str) -> Optional[str]:
        """
        도메인으로 웹사이트를 크롤링하여 회사명 추출
        
        Args:
            domain: 이메일 도메인 (예: cj.net)
            
        Returns:
            추출된 회사명 또는 None
        """
        if not domain:
            return None
        
        # 개인/메일서비스 이메일 도메인 제외 (회사 사이트로 오인 방지)
        personal_domains = ['gmail.com', 'naver.com', 'daum.net', 'hanmail.net', 
                           'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com',
                           'maver.com', 'nate.com', 'kakao.com', 'kakao.co.kr']
        if domain.lower() in personal_domains:
            return None
        
        # 웹사이트 URL 생성 시도
        urls_to_try = [
            f'https://{domain}',
            f'https://www.{domain}',
            f'http://{domain}',
            f'http://www.{domain}'
        ]
        
        for url in urls_to_try:
            try:
                company_name = self._crawl_website(url)
                if company_name:
                    return company_name
            except requests.exceptions.Timeout:
                # 타임아웃은 다음 URL 시도
                continue
            except requests.exceptions.RequestException as e:
                # 네트워크 오류는 다음 URL 시도
                continue
            except Exception as e:
                # 기타 오류는 로그만 남기고 계속
                continue
        
        return None

    def fetch_site_metadata(self, domain_or_url: str) -> dict:
        """
        홈페이지에서 메타 description/간단 소개/직원수 힌트 등을 추출.
        Returns:
            {"website": str|None, "description": str|None, "employees": str|None}
        """
        if not domain_or_url:
            return {"website": None, "description": None, "employees": None}

        s = str(domain_or_url).strip()
        # 도메인이면 URL 후보 생성
        urls_to_try = []
        if "://" in s:
            urls_to_try = [s]
        else:
            d = s.lower()
            urls_to_try = [f"https://{d}", f"https://www.{d}", f"http://{d}", f"http://www.{d}"]

        for url in urls_to_try:
            try:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                r.raise_for_status()
                final_url = r.url or url
                soup = BeautifulSoup(r.text, "html.parser")

                # description 후보: meta description → og:description → 첫 문장(h1/p)
                desc = None
                m = soup.find("meta", attrs={"name": "description"})
                if m and m.get("content"):
                    desc = m.get("content", "").strip()
                if not desc:
                    ogd = soup.find("meta", property="og:description")
                    if ogd and ogd.get("content"):
                        desc = ogd.get("content", "").strip()
                if not desc:
                    p = soup.find("p")
                    if p:
                        t = " ".join(p.get_text(" ").split())
                        if t and len(t) >= 30:
                            desc = t[:400]

                # 직원수 힌트(매우 단순): "employees" 또는 "직원" 주변 숫자
                employees = None
                text = soup.get_text(" ", strip=True)
                text = " ".join(text.split())
                # 영문 패턴
                import re
                m1 = re.search(r"(\\d{1,6})\\s*(employees|employee)", text, re.IGNORECASE)
                if m1:
                    employees = m1.group(1)
                # 한글 패턴
                if not employees:
                    m2 = re.search(r"(직원\\s*수\\s*[:\\-]?\\s*)(\\d{1,6})", text)
                    if m2:
                        employees = m2.group(2)
                if not employees:
                    m3 = re.search(r"(\\d{1,6})\\s*명\\s*(직원)?", text)
                    if m3:
                        employees = m3.group(1)

                return {
                    "website": final_url,
                    "description": desc or None,
                    "employees": employees or None,
                }
            except Exception:
                continue

        return {"website": None, "description": None, "employees": None}
    
    def _crawl_website(self, url: str) -> Optional[str]:
        """
        웹사이트를 크롤링하여 회사명 추출
        
        Args:
            url: 웹사이트 URL
            
        Returns:
            추출된 회사명 또는 None
        """
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()
            
            # HTML 파싱
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. og:site_name 메타 태그 확인
            og_site_name = soup.find('meta', property='og:site_name')
            if og_site_name and og_site_name.get('content'):
                company_name = og_site_name.get('content').strip()
                if company_name:
                    return company_name
            
            # 2. og:title 메타 태그 확인
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title.get('content').strip()
                # "회사명 - 설명" 형식에서 회사명만 추출
                if ' - ' in title:
                    company_name = title.split(' - ')[0].strip()
                    if company_name:
                        return company_name
            
            # 3. title 태그 확인
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text().strip()
                # 일반적인 패턴 제거
                title_text = title_text.replace(' | ', ' - ').replace(' |', '').replace('| ', '')
                if ' - ' in title_text:
                    company_name = title_text.split(' - ')[0].strip()
                else:
                    company_name = title_text
                
                # 너무 긴 경우 제외
                if company_name and len(company_name) < 100:
                    return company_name
            
            # 4. h1 태그 확인 (메인 페이지인 경우)
            h1_tag = soup.find('h1')
            if h1_tag:
                h1_text = h1_tag.get_text().strip()
                if h1_text and len(h1_text) < 100:
                    return h1_text
            
            # 5. meta name="application-name" 확인
            app_name = soup.find('meta', attrs={'name': 'application-name'})
            if app_name and app_name.get('content'):
                company_name = app_name.get('content').strip()
                if company_name:
                    return company_name
            
            # 6. meta name="author" 확인
            author = soup.find('meta', attrs={'name': 'author'})
            if author and author.get('content'):
                author_text = author.get('content').strip()
                # 회사명 형식인지 확인
                if author_text and len(author_text) < 100 and not '@' in author_text:
                    return author_text
            
            return None
            
        except requests.exceptions.RequestException:
            return None
        except Exception as e:
            return None
    
    def extract_company_name_from_url(self, url: str) -> Optional[str]:
        """
        웹사이트 URL에서 직접 회사명 추출
        
        Args:
            url: 웹사이트 URL
            
        Returns:
            추출된 회사명 또는 None
        """
        return self._crawl_website(url)
