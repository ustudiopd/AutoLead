"""
DART API 클라이언트 모듈
기업 정보 조회를 위한 DART API 연동
"""
import os
import time
from typing import Dict, List, Optional
import dart_fss as dart
from dotenv import load_dotenv

load_dotenv()

# Gemini 클라이언트는 선택적 임포트 (없어도 동작)
try:
    from .gemini_client import GeminiClient
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class DartClient:
    """DART API를 통한 기업 정보 조회 클라이언트"""
    
    def __init__(self, use_gemini: bool = True):
        """
        DART API 키 초기화
        
        Args:
            use_gemini: Gemini API 사용 여부 (기본값: True)
        """
        api_key = os.getenv('DART_API_KEY')
        if not api_key:
            raise ValueError("DART_API_KEY가 환경 변수에 설정되지 않았습니다.")
        dart.set_api_key(api_key=api_key)
        self.api_key = api_key
        
        # Gemini 클라이언트 초기화 (선택적)
        self.gemini_client = None
        if use_gemini and GEMINI_AVAILABLE:
            try:
                self.gemini_client = GeminiClient()
            except Exception as e:
                print(f"Gemini 클라이언트 초기화 실패 (계속 진행): {str(e)}")
                self.gemini_client = None
        
    def search_company_by_name(self, company_name: str) -> List[Dict]:
        """
        회사명으로 기업 검색
        
        Args:
            company_name: 검색할 회사명
            
        Returns:
            검색된 기업 정보 리스트
        """
        try:
            # DART에 등록된 모든 기업 리스트 조회
            corp_list = dart.get_corp_list()
            
            # 회사명으로 검색 (부분 일치)
            matched = corp_list.find_by_corp_name(company_name, exactly=False)
            
            # None 체크
            if matched is None:
                return []
            
            matched_companies = []
            for corp in matched:
                matched_companies.append({
                    'corp_code': corp.corp_code,
                    'corp_name': corp.corp_name,
                    'stock_code': corp.stock_code,
                    'modify_date': corp.modify_date
                })
            
            # API 호출 제한을 위한 딜레이
            time.sleep(0.1)
            
            return matched_companies
            
        except Exception as e:
            print(f"DART 검색 오류 ({company_name}): {str(e)}")
            return []
    
    def get_company_info(self, corp_code: str) -> Optional[Dict]:
        """
        기업 고유번호로 기업개황 정보 조회
        
        Args:
            corp_code: DART 기업 고유번호 (8자리)
            
        Returns:
            기업개황 정보 딕셔너리
        """
        try:
            company_info = dart.api.filings.get_corp_info(corp_code=corp_code)
            
            if company_info:
                return {
                    'corp_name': company_info.get('corp_name', ''),
                    'corp_name_eng': company_info.get('corp_name_eng', ''),
                    'adres': company_info.get('adres', ''),
                    'hmurl': company_info.get('hmurl', ''),
                    'induty_code': company_info.get('induty_code', ''),  # KSIC 코드
                    'ceo_nm': company_info.get('ceo_nm', ''),
                    'corp_cls': company_info.get('corp_cls', ''),
                }
            
            # API 호출 제한을 위한 딜레이
            time.sleep(0.1)
            return None
            
        except Exception as e:
            print(f"DART 기업개황 조회 오류 ({corp_code}): {str(e)}")
            return None
    
    def enrich_company_data(
        self,
        company_name: str,
        email_domain: Optional[str] = None,
        industry_hint: Optional[str] = None
    ) -> Optional[Dict]:
        """
        회사명으로 기업 정보 보강
        
        전략:
        1차: 이메일 도메인으로 웹 크롤링 → 회사명 추출 → DART 검색
        2차: 원본 회사명으로 DART 검색
        
        Args:
            company_name: 검색할 회사명
            email_domain: 이메일 도메인 (1차 검색용, 선택)
            industry_hint: 업종 힌트 (Gemini 매칭 개선용, 선택)
            
        Returns:
            보강된 기업 정보 또는 None
        """
        matched_companies = []
        search_method = None
        
        # 1차: 이메일 도메인으로 웹 크롤링 → 회사명 추출 → 검색
        if email_domain:
            try:
                from .web_crawler import WebCrawler
                crawler = WebCrawler()
                
                # 웹 크롤링으로 회사명 추출
                crawled_name = crawler.extract_company_name_from_domain(email_domain)
                
                if crawled_name:
                    print(f"도메인 크롤링 성공 ({email_domain} → {crawled_name})")
                    
                    # Gemini로 정제 (가능한 경우)
                    if self.gemini_client:
                        try:
                            refined_name = self.gemini_client.refine_company_name(crawled_name)
                            if refined_name:
                                crawled_name = refined_name
                        except Exception:
                            pass
                    
                    # 전략: 원본 회사명을 Gemini로 한국어 변환 후 검색
                    # 원본 회사명이 있으면 그것을 우선 사용
                    if company_name and company_name.strip():
                        # 1) 원본 회사명 그대로 검색
                        matched_companies = self.search_company_by_name(company_name.strip())
                        
                        # 2) 검색 실패 시 Gemini로 한국어 변환 후 검색
                        if not matched_companies and self.gemini_client:
                            try:
                                refined_original = self.gemini_client.refine_company_name(company_name.strip())
                                if refined_original and refined_original != company_name.strip():
                                    print(f"원본 회사명 한국어 변환 ({company_name} → {refined_original})")
                                    matched_companies = self.search_company_by_name(refined_original)
                            except Exception as e:
                                print(f"Gemini 회사명 변환 오류: {str(e)}")
                        
                        if matched_companies:
                            # 여러 매칭이 있으면 원본 회사명 + 도메인 힌트로 최적 선택
                            if len(matched_companies) > 1 and self.gemini_client:
                                try:
                                    selected = self.gemini_client.select_best_match(
                                        company_name=company_name,
                                        matches=matched_companies,
                                        email_domain=email_domain,
                                        industry_hint=industry_hint
                                    )
                                    if selected:
                                        matched_companies = [selected]
                                        search_method = 'domain_crawl'
                                        print(f"도메인 크롤링 힌트로 원본 회사명 매칭 성공 ({email_domain} → {crawled_name}, 원본: {company_name})")
                                except Exception as e:
                                    print(f"Gemini 매칭 선택 오류: {str(e)}")
                            
                            if matched_companies:
                                search_method = 'domain_crawl'
                                print(f"도메인 크롤링 힌트로 원본 회사명 검색 성공 ({email_domain} → {crawled_name})")
                    
                    # 원본 회사명 검색 실패 시, 크롤링된 회사명으로 검색
                    if not matched_companies:
                        matched_companies = self.search_company_by_name(crawled_name)
                        if matched_companies:
                            # 여러 매칭이 있으면 원본 회사명 힌트로 최적 선택
                            if len(matched_companies) > 1 and self.gemini_client:
                                try:
                                    selected = self.gemini_client.select_best_match(
                                        company_name=company_name if company_name else crawled_name,
                                        matches=matched_companies,
                                        email_domain=email_domain,
                                        industry_hint=industry_hint
                                    )
                                    if selected:
                                        matched_companies = [selected]
                                        search_method = 'domain_crawl'
                                        print(f"도메인 크롤링으로 회사명 발견 + 원본 힌트로 정확한 매칭 ({email_domain} → {crawled_name}, 원본: {company_name})")
                                except Exception as e:
                                    print(f"Gemini 매칭 선택 오류: {str(e)}")
                            
                            if matched_companies:
                                search_method = 'domain_crawl'
                                print(f"도메인 크롤링으로 회사명 발견 ({email_domain} → {crawled_name})")
                
                # 크롤링 실패 시 Gemini로 도메인→회사명 추론
                if not matched_companies and self.gemini_client:
                    try:
                        inferred_name = self.gemini_client.infer_company_name_from_domain(
                            email_domain, company_hint=company_name
                        )
                        if inferred_name:
                            matched_companies = self.search_company_by_name(inferred_name)
                            if matched_companies:
                                # 여러 매칭이 있으면 원본 회사명 힌트로 최적 선택
                                if len(matched_companies) > 1:
                                    try:
                                        selected = self.gemini_client.select_best_match(
                                            company_name=company_name,
                                            matches=matched_companies,
                                            email_domain=email_domain,
                                            industry_hint=industry_hint
                                        )
                                        if selected:
                                            matched_companies = [selected]
                                    except Exception:
                                        pass
                                
                                if matched_companies:
                                    search_method = 'domain_inference'
                                    print(f"도메인 추론으로 회사명 발견 ({email_domain} → {inferred_name})")
                    except Exception as e:
                        print(f"도메인 추론 오류: {str(e)}")
                        
            except ImportError:
                # web_crawler 모듈이 없으면 건너뜀
                pass
            except Exception as e:
                print(f"도메인 크롤링 오류: {str(e)}")
        
        # 2차: 원본 회사명으로 검색 (1차 실패 시)
        if not matched_companies:
            matched_companies = self.search_company_by_name(company_name)
            search_method = 'company_name'
        
        if not matched_companies:
            return None
        
        # 2. 첫 번째 매칭 결과의 상세 정보 조회
        if len(matched_companies) == 1:
            corp_code = matched_companies[0]['corp_code']
            company_info = self.get_company_info(corp_code)
            
            if company_info:
                result = {
                    **company_info,
                    'match_count': 1,
                    'matched_corp_name': matched_companies[0]['corp_name']
                }
                if search_method:
                    result['search_method'] = search_method
                return result
        
        # 3. 여러 개 매칭된 경우 Gemini로 최적 선택 (가능한 경우)
        elif len(matched_companies) > 1:
            selected_match = None
            
            # Gemini를 사용하여 최적 매칭 선택
            if self.gemini_client:
                try:
                    selected_match = self.gemini_client.select_best_match(
                        company_name=company_name,
                        matches=matched_companies,
                        email_domain=email_domain,
                        industry_hint=industry_hint
                    )
                except Exception as e:
                    print(f"Gemini 매칭 선택 오류 (첫 번째 결과 사용): {str(e)}")
                    selected_match = matched_companies[0]
            else:
                # Gemini가 없으면 첫 번째 결과 사용
                selected_match = matched_companies[0]
            
            if selected_match:
                corp_code = selected_match['corp_code']
                company_info = self.get_company_info(corp_code)
                
                if company_info:
                    result = {
                        **company_info,
                        'match_count': len(matched_companies),
                        'matched_corp_name': selected_match['corp_name'],
                        'all_matches': [c['corp_name'] for c in matched_companies],
                        'gemini_selected': self.gemini_client is not None
                    }
                    if search_method:
                        result['search_method'] = search_method
                    return result
        
        return None
