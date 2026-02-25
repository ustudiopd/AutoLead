"""
웹 크롤러 모듈
이메일 도메인으로 웹사이트를 크롤링하여 회사명 추출
"""
import requests
from bs4 import BeautifulSoup
from typing import Optional
from urllib.parse import urlparse
import time


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
        
        # 개인 이메일 도메인 제외
        personal_domains = ['gmail.com', 'naver.com', 'daum.net', 'hanmail.net', 
                           'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com']
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
