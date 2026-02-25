"""
KSIC(한국산업표준) → SIC(미국 표준 산업 분류) 코드 매핑 모듈
"""
import pandas as pd
import os
from typing import Optional, Dict

# Gemini 클라이언트는 선택적 임포트
try:
    from .gemini_client import GeminiClient
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class KSICSICMapper:
    """KSIC 코드를 SIC 코드로 변환하는 매퍼"""
    
    def __init__(self, mapping_file_path: Optional[str] = None, use_gemini: bool = True):
        """
        매핑 테이블 초기화
        
        Args:
            mapping_file_path: KSIC→SIC 매핑 CSV 파일 경로
            use_gemini: Gemini API 사용 여부 (기본값: True)
        """
        if mapping_file_path and os.path.exists(mapping_file_path):
            self.mapping_df = pd.read_csv(mapping_file_path)
        else:
            # 기본 빈 매핑 테이블 생성
            self.mapping_df = pd.DataFrame(columns=['KSIC_Code', 'SIC_Code', 'SIC_Description'])
            self._create_template_mapping_file(mapping_file_path)
        
        # Gemini 클라이언트 초기화 (선택적)
        self.gemini_client = None
        if use_gemini and GEMINI_AVAILABLE:
            try:
                self.gemini_client = GeminiClient()
            except Exception as e:
                print(f"Gemini 클라이언트 초기화 실패 (계속 진행): {str(e)}")
                self.gemini_client = None
        
        # 기본 매핑 규칙 초기화
        self._init_default_mapping_rules()
    
    def _create_template_mapping_file(self, file_path: Optional[str]):
        """템플릿 매핑 파일 생성"""
        if file_path:
            template_df = pd.DataFrame({
                'KSIC_Code': [],
                'SIC_Code': [],
                'SIC_Description': []
            })
            template_df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print(f"매핑 테이블 템플릿 생성: {file_path}")
    
    def _init_default_mapping_rules(self):
        """기본 매핑 규칙 초기화 (KSIC 대분류 → SIC 대분류)"""
        # KSIC 대분류(첫 1-2자리) → SIC 대분류 매핑
        self.default_mapping = {
            # 제조업 (10-33) → Manufacturing (2000-3999)
            '10': {'sic_range': '2000-2999', 'description': 'Food and Kindred Products'},
            '11': {'sic_range': '2000-2099', 'description': 'Food and Kindred Products'},
            '13': {'sic_range': '2200-2299', 'description': 'Textile Mill Products'},
            '14': {'sic_range': '2300-2399', 'description': 'Apparel and Other Textile Products'},
            '15': {'sic_range': '2400-2499', 'description': 'Lumber and Wood Products'},
            '16': {'sic_range': '2500-2599', 'description': 'Furniture and Fixtures'},
            '17': {'sic_range': '2600-2699', 'description': 'Paper and Allied Products'},
            '18': {'sic_range': '2700-2799', 'description': 'Printing and Publishing'},
            '19': {'sic_range': '2800-2899', 'description': 'Chemicals and Allied Products'},
            '20': {'sic_range': '3000-3099', 'description': 'Rubber and Miscellaneous Plastics'},
            '21': {'sic_range': '3100-3199', 'description': 'Leather and Leather Products'},
            '22': {'sic_range': '3200-3299', 'description': 'Stone, Clay, and Glass Products'},
            '23': {'sic_range': '3300-3399', 'description': 'Primary Metal Industries'},
            '24': {'sic_range': '3400-3499', 'description': 'Fabricated Metal Products'},
            '25': {'sic_range': '3500-3599', 'description': 'Industrial Machinery and Equipment'},
            '26': {'sic_range': '3600-3699', 'description': 'Electronic and Other Electrical Equipment'},
            '27': {'sic_range': '3700-3799', 'description': 'Transportation Equipment'},
            '28': {'sic_range': '3800-3899', 'description': 'Instruments and Related Products'},
            '29': {'sic_range': '3900-3999', 'description': 'Miscellaneous Manufacturing Industries'},
            
            # 건설업 (41-43) → Construction (1500-1799)
            '41': {'sic_range': '1500-1599', 'description': 'General Building Contractors'},
            '42': {'sic_range': '1600-1699', 'description': 'Heavy Construction Contractors'},
            '43': {'sic_range': '1700-1799', 'description': 'Special Trade Contractors'},
            
            # 도매 및 소매업 (45-47) → Wholesale/Retail Trade (5000-5999)
            '45': {'sic_range': '5000-5099', 'description': 'Wholesale Trade - Durable Goods'},
            '46': {'sic_range': '5100-5199', 'description': 'Wholesale Trade - Non-Durable Goods'},
            '47': {'sic_range': '5200-5999', 'description': 'Retail Trade'},
            
            # 운수업 (49-53) → Transportation (4000-4999)
            '49': {'sic_range': '4000-4099', 'description': 'Railroad Transportation'},
            '50': {'sic_range': '4100-4199', 'description': 'Local and Interurban Passenger Transit'},
            '51': {'sic_range': '4200-4299', 'description': 'Trucking and Warehousing'},
            '52': {'sic_range': '4400-4499', 'description': 'Water Transportation'},
            '53': {'sic_range': '4500-4599', 'description': 'Transportation by Air'},
            
            # 숙박 및 음식점업 (55-56) → Hotels and Other Lodging Places (7000-7099)
            '55': {'sic_range': '7000-7099', 'description': 'Hotels and Other Lodging Places'},
            '56': {'sic_range': '5800-5899', 'description': 'Eating and Drinking Places'},
            
            # 정보통신업 (58-63) → Information Services (7000-7999)
            '58': {'sic_range': '2700-2799', 'description': 'Printing and Publishing'},
            '59': {'sic_range': '4800-4899', 'description': 'Communications'},
            '60': {'sic_range': '4800-4899', 'description': 'Communications'},
            '61': {'sic_range': '4800-4899', 'description': 'Communications'},
            '62': {'sic_range': '7370-7379', 'description': 'Computer Programming and Data Processing'},
            '63': {'sic_range': '7370-7379', 'description': 'Computer Programming and Data Processing'},
            
            # 금융 및 보험업 (64-66) → Finance, Insurance, and Real Estate (6000-6999)
            '64': {'sic_range': '6000-6099', 'description': 'Depository Institutions'},
            '65': {'sic_range': '6100-6199', 'description': 'Nondepository Institutions'},
            '66': {'sic_range': '6300-6399', 'description': 'Insurance Carriers'},
            
            # 부동산업 (68) → Real Estate (6500-6599)
            '68': {'sic_range': '6500-6599', 'description': 'Real Estate'},
            
            # 전문, 과학 및 기술 서비스업 (69-75) → Business Services (7000-7999)
            '69': {'sic_range': '7300-7399', 'description': 'Business Services'},
            '70': {'sic_range': '7300-7399', 'description': 'Business Services'},
            '71': {'sic_range': '7300-7399', 'description': 'Business Services'},
            '72': {'sic_range': '7000-7099', 'description': 'Hotels and Other Lodging Places'},
            '73': {'sic_range': '7300-7399', 'description': 'Business Services'},
            '74': {'sic_range': '7300-7399', 'description': 'Business Services'},
            '75': {'sic_range': '8700-8799', 'description': 'Engineering and Management Services'},
            
            # 사업시설 관리 및 사업지원 서비스업 (77-82) → Business Services (7000-7999)
            '77': {'sic_range': '7300-7399', 'description': 'Business Services'},
            '78': {'sic_range': '7800-7899', 'description': 'Motion Pictures'},
            '79': {'sic_range': '7900-7999', 'description': 'Amusement and Recreation Services'},
            '80': {'sic_range': '8000-8099', 'description': 'Health Services'},
            '81': {'sic_range': '8200-8299', 'description': 'Educational Services'},
            '82': {'sic_range': '8300-8399', 'description': 'Social Services'},
            
            # 공공행정, 국방 및 사회보장 행정 (84) → Executive, Legislative, and General Government (9100-9199)
            '84': {'sic_range': '9100-9199', 'description': 'Executive, Legislative, and General Government'},
            
            # 교육 서비스업 (85) → Educational Services (8200-8299)
            '85': {'sic_range': '8200-8299', 'description': 'Educational Services'},
            
            # 보건업 및 사회복지 서비스업 (86-88) → Health Services (8000-8099)
            '86': {'sic_range': '8000-8099', 'description': 'Health Services'},
            '87': {'sic_range': '8000-8099', 'description': 'Health Services'},
            '88': {'sic_range': '8300-8399', 'description': 'Social Services'},
            
            # 예술, 스포츠 및 여가관련 서비스업 (90) → Amusement and Recreation Services (7900-7999)
            '90': {'sic_range': '7900-7999', 'description': 'Amusement and Recreation Services'},
        }
    
    def _get_default_sic_code(self, ksic_code: str) -> Optional[Dict]:
        """
        기본 매핑 규칙을 사용하여 SIC 코드 추론
        
        Args:
            ksic_code: KSIC 코드
            
        Returns:
            SIC 코드 정보 딕셔너리 또는 None
        """
        if not ksic_code or len(str(ksic_code).strip()) < 1:
            return None
        
        ksic_str = str(ksic_code).strip()
        
        # 첫 1-2자리로 대분류 확인
        if len(ksic_str) >= 2:
            prefix_2 = ksic_str[:2]
            if prefix_2 in self.default_mapping:
                mapping = self.default_mapping[prefix_2]
                # SIC 범위에서 중간값 선택 (예: 2000-2999 → 2500)
                sic_range = mapping['sic_range']
                if '-' in sic_range:
                    start, end = sic_range.split('-')
                    sic_code = str((int(start) + int(end)) // 2).zfill(4)
                else:
                    sic_code = sic_range[:4]
                
                return {
                    'SIC_Code': sic_code,
                    'SIC_Description': mapping['description']
                }
        
        # 첫 1자리로 대분류 확인
        if len(ksic_str) >= 1:
            prefix_1 = ksic_str[0]
            if prefix_1 in self.default_mapping:
                mapping = self.default_mapping[prefix_1]
                sic_range = mapping['sic_range']
                if '-' in sic_range:
                    start, end = sic_range.split('-')
                    sic_code = str((int(start) + int(end)) // 2).zfill(4)
                else:
                    sic_code = sic_range[:4]
                
                return {
                    'SIC_Code': sic_code,
                    'SIC_Description': mapping['description']
                }
        
        return None
    
    def map_ksic_to_sic(
        self,
        ksic_code: str,
        ksic_description: Optional[str] = None
    ) -> Optional[Dict]:
        """
        KSIC 코드를 SIC 코드로 매핑 (하이브리드 접근)
        
        전략:
        1. 매핑 테이블에서 검색
        2. 없으면 Gemini API로 변환
        3. 없으면 기본 매핑 규칙 적용
        
        Args:
            ksic_code: KSIC 코드 (5자리)
            ksic_description: KSIC 설명 (선택, Gemini 변환 시 사용)
            
        Returns:
            SIC 코드 정보 딕셔너리 또는 None
        """
        if not ksic_code or pd.isna(ksic_code):
            return None
        
        ksic_str = str(ksic_code).strip()
        
        # KSIC 코드가 비어있으면 None 반환
        if not ksic_str or ksic_str == '':
            return None
        
        # 1. 매핑 테이블에서 검색
        if not self.mapping_df.empty:
            # 정확히 일치하는 경우
            exact_match = self.mapping_df[
                self.mapping_df['KSIC_Code'] == ksic_str
            ]
            
            if not exact_match.empty:
                return {
                    'SIC_Code': exact_match.iloc[0]['SIC_Code'],
                    'SIC_Description': exact_match.iloc[0].get('SIC_Description', '')
                }
            
            # 앞 4자리로 매칭 시도
            if len(ksic_str) >= 4:
                prefix_match = self.mapping_df[
                    self.mapping_df['KSIC_Code'].str.startswith(ksic_str[:4])
                ]
                
                if not prefix_match.empty:
                    return {
                        'SIC_Code': prefix_match.iloc[0]['SIC_Code'],
                        'SIC_Description': prefix_match.iloc[0].get('SIC_Description', '')
                    }
        
        # 2. Gemini API로 변환 시도
        if self.gemini_client:
            try:
                gemini_result = self.gemini_client.convert_ksic_to_sic(
                    ksic_str, ksic_description
                )
                if gemini_result:
                    # 변환 결과를 매핑 테이블에 저장 (다음번에 재사용)
                    self.add_mapping(
                        ksic_str,
                        gemini_result['SIC_Code'],
                        gemini_result.get('SIC_Description', '')
                    )
                    return gemini_result
            except Exception as e:
                print(f"Gemini 변환 오류 ({ksic_str}): {str(e)}")
        
        # 3. 기본 매핑 규칙 적용
        default_result = self._get_default_sic_code(ksic_str)
        if default_result:
            return default_result
        
        return None
    
    def add_mapping(self, ksic_code: str, sic_code: str, sic_description: str = ''):
        """
        새로운 매핑 추가
        
        Args:
            ksic_code: KSIC 코드
            sic_code: SIC 코드
            sic_description: SIC 설명
        """
        new_row = pd.DataFrame({
            'KSIC_Code': [ksic_code],
            'SIC_Code': [sic_code],
            'SIC_Description': [sic_description]
        })
        
        self.mapping_df = pd.concat([self.mapping_df, new_row], ignore_index=True)
