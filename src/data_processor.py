"""
데이터 전처리 및 보강 모듈
CSV 데이터 로드, 정제, DART API 연동을 통한 보강
"""
import re
import pandas as pd
from typing import Dict, Optional
from urllib.parse import urlparse
from .dart_client import DartClient


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
        if cleaned_name or email_domain:
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
