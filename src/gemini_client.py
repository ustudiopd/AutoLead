"""
Gemini API 클라이언트 모듈
회사명 매칭 정확도 향상을 위한 Gemini 활용
"""
import os
from typing import List, Dict, Optional
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class GeminiClient:
    """Gemini API를 통한 지능형 매칭 및 분류 클라이언트"""
    
    def __init__(self):
        """Gemini API 초기화"""
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY가 환경 변수에 설정되지 않았습니다.")
        
        genai.configure(api_key=api_key)
        # 사용 가능한 모델로 변경
        # 참고: google.generativeai 패키지는 deprecated되었지만 계속 사용 가능
        # 사용 가능한 모델: gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash 등
        model_names = ['gemini-2.5-flash', 'models/gemini-2.5-flash', 
                      'gemini-2.5-pro', 'models/gemini-2.5-pro',
                      'gemini-2.0-flash', 'models/gemini-2.0-flash']
        self.model = None
        
        for model_name in model_names:
            try:
                self.model = genai.GenerativeModel(model_name)
                # 모델이 실제로 작동하는지 간단히 테스트
                break
            except Exception:
                continue
        
        if self.model is None:
            print("Gemini 모델 초기화 실패 (기본 매핑 규칙만 사용)")
    
    def select_best_match(
        self,
        company_name: str,
        matches: List[Dict],
        email_domain: Optional[str] = None,
        industry_hint: Optional[str] = None
    ) -> Optional[Dict]:
        """
        다중 매칭 결과 중 최적 선택
        
        Args:
            company_name: 검색한 회사명
            matches: DART에서 매칭된 기업 리스트
            email_domain: 이메일 도메인 (선택)
            industry_hint: 업종 힌트 (선택)
            
        Returns:
            최적 매칭 결과 또는 None
        """
        if not matches or len(matches) == 0:
            return None
        
        if len(matches) == 1:
            return matches[0]
        
        # 컨텍스트 정보 구성
        context_parts = [f"검색한 회사명: {company_name}"]
        
        if email_domain:
            context_parts.append(f"이메일 도메인: {email_domain}")
        
        if industry_hint:
            context_parts.append(f"업종 힌트: {industry_hint}")
        
        context = "\n".join(context_parts)
        
        # 매칭 후보 정보 구성
        candidates_info = []
        for idx, match in enumerate(matches[:5]):  # 최대 5개만 고려
            candidates_info.append(
                f"{idx + 1}. {match.get('corp_name', '')} "
                f"(코드: {match.get('corp_code', '')})"
            )
        
        candidates_text = "\n".join(candidates_info)
        
        # Gemini 프롬프트 구성
        prompt = f"""다음 정보를 바탕으로 가장 적합한 기업을 선택해주세요.

{context}

매칭된 후보 기업들:
{candidates_text}

위 후보 중에서 검색한 회사명과 가장 일치하는 기업의 번호만 숫자로 답변해주세요.
특히 원본 회사명의 키워드(예: "올리브네트웍스", "olivenetworks" 등)가 포함된 기업을 우선 선택해주세요.
만약 모두 일치하지 않는다면 0을 답변해주세요.
답변은 숫자만 입력하세요 (예: 1, 2, 3, 또는 0)."""

        try:
            response = self.model.generate_content(prompt)
            answer = response.text.strip()
            
            # 숫자 추출
            import re
            numbers = re.findall(r'\d+', answer)
            
            if numbers:
                selected_idx = int(numbers[0]) - 1  # 1-based to 0-based
                
                if 0 <= selected_idx < len(matches):
                    return matches[selected_idx]
            
            # 매칭 실패 시 첫 번째 결과 반환
            return matches[0]
            
        except Exception as e:
            print(f"Gemini 매칭 선택 오류: {str(e)}")
            # 오류 시 첫 번째 결과 반환
            return matches[0]
    
    def refine_company_name(self, company_name: str) -> str:
        """
        회사명 정제 개선 (Gemini 활용)
        
        Args:
            company_name: 원본 회사명
            
        Returns:
            정제된 회사명
        """
        if not company_name or len(company_name.strip()) == 0:
            return ""
        
        if not self.model:
            return company_name
        
        prompt = f"""다음 회사명을 한국어 공식 기업명으로 정제해주세요.
약칭, 영문명, 오타가 있을 수 있습니다.
특히 영문 회사명은 한국어로 변환해주세요.

예시:
- cj-olivenetworks → 씨제이올리브네트웍스 또는 올리브네트웍스
- woongjin → 웅진
- moodys → 무디스

입력: {company_name}

정제된 회사명만 출력하세요. 설명이나 추가 텍스트는 포함하지 마세요."""

        try:
            response = self.model.generate_content(prompt)
            refined = response.text.strip()
            
            # 따옴표 제거
            refined = refined.strip('"').strip("'")
            
            return refined if refined else company_name
            
        except Exception as e:
            print(f"Gemini 회사명 정제 오류: {str(e)}")
            return company_name
    
    def infer_company_name_from_domain(self, domain: str, company_hint: Optional[str] = None) -> Optional[str]:
        """
        이메일 도메인으로부터 회사명 추론
        
        Args:
            domain: 이메일 도메인 (예: cj.net)
            company_hint: 회사명 힌트 (선택)
            
        Returns:
            추론된 회사명 또는 None
        """
        if not domain:
            return None
        
        if not self.model:
            return None
        
        context = f"이메일 도메인: {domain}"
        if company_hint:
            context += f"\n회사명 힌트: {company_hint}"
        
        prompt = f"""다음 이메일 도메인으로부터 한국 기업의 공식 회사명을 추론해주세요.

{context}

예시:
- cj.net → CJ올리브네트웍스 또는 CJ
- woongjin.co.kr → 웅진
- spc.co.kr → SPC그룹

공식 회사명만 출력하세요. 설명이나 추가 텍스트는 포함하지 마세요."""

        try:
            response = self.model.generate_content(prompt)
            company_name = response.text.strip()
            
            # 따옴표 제거
            company_name = company_name.strip('"').strip("'")
            
            return company_name if company_name else None
            
        except Exception as e:
            print(f"Gemini 도메인→회사명 추론 오류 ({domain}): {str(e)}")
            return None
    
    def infer_industry(
        self,
        company_name: str,
        description: Optional[str] = None
    ) -> Optional[str]:
        """
        회사명과 설명으로부터 업종 추론
        
        Args:
            company_name: 회사명
            description: 추가 설명 (선택)
            
        Returns:
            추론된 업종명 또는 None
        """
        context = f"회사명: {company_name}"
        if description:
            context += f"\n설명: {description}"
        
        prompt = f"""다음 정보를 바탕으로 기업의 업종을 추론해주세요.

{context}

한국어 업종명만 출력하세요. 예: "소프트웨어 개발", "금융 서비스", "제조업" 등."""

        try:
            response = self.model.generate_content(prompt)
            industry = response.text.strip()
            
            # 따옴표 제거
            industry = industry.strip('"').strip("'")
            
            return industry if industry else None
            
        except Exception as e:
            print(f"Gemini 업종 추론 오류: {str(e)}")
            return None

    def pick_industry_from_choices(
        self,
        *,
        company_name: str,
        website: Optional[str],
        description: Optional[str],
        choices: List[str],
    ) -> Optional[str]:
        """
        주어진 선택지(엑셀 Industry 탭) 중 하나를 반드시 골라 반환.
        """
        if not self.model or not choices:
            return None

        name = (company_name or "").strip()
        site = (website or "").strip()
        desc = (description or "").strip()
        # 너무 긴 선택지는 토큰 낭비라 상한
        choices_clean = [c.strip() for c in choices if c and str(c).strip()]

        prompt = f"""아래 회사 정보를 보고, 주어진 업종 선택지 중에서 가장 적합한 **하나**를 골라주세요.

회사명: {name or "(없음)"}
웹사이트: {site or "(없음)"}
설명: {desc[:500] or "(없음)"}

업종 선택지(이 중에서만 답변):
{chr(10).join("- " + c for c in choices_clean)}

규칙:
- 반드시 위 선택지 중 하나를 그대로 출력하세요.
- 확신이 없으면 Other를 선택하세요.
"""
        try:
            resp = self.model.generate_content(prompt)
            ans = (resp.text or "").strip().strip('"').strip("'")
            # 선택지 그대로 매칭
            for c in choices_clean:
                if ans == c:
                    return c
            # 대소문자/공백 정규화 매칭
            ans_n = " ".join(ans.split()).lower()
            for c in choices_clean:
                if ans_n == " ".join(c.split()).lower():
                    return c
            # 실패 시 Other
            for c in choices_clean:
                if c.strip().lower() == "other":
                    return c
            return choices_clean[0]
        except Exception as e:
            print(f"Gemini 업종 선택 오류: {str(e)}")
            return None

    def infer_employee_count(
        self,
        *,
        company_name: str,
        website: Optional[str],
        description: Optional[str],
    ) -> Optional[str]:
        """
        직원 수를 추정해 실제 숫자만 반환. (예: '50', '120', '1000') 범위(1-10 등) 사용 금지.
        """
        if not self.model:
            return None
        name = (company_name or "").strip()
        site = (website or "").strip()
        desc = (description or "").strip()
        prompt = f"""아래 회사 정보를 보고, 해당 회사의 직원 수를 추정한 **정확한 숫자 하나**만 답하세요.

회사명: {name or "(없음)"}
웹사이트: {site or "(없음)"}
설명: {desc[:700] or "(없음)"}

규칙:
- 답변은 반드시 숫자만 출력하세요. 예: 50, 120, 1000
- 범위(1-10, 51-200 등)나 설명은 쓰지 마세요.
- 알 수 없으면 빈칸으로 두거나 0만 출력하세요.
"""
        try:
            import re
            resp = self.model.generate_content(prompt)
            ans = (resp.text or "").strip().splitlines()[0].strip()
            ans = ans.strip('"').strip("'").replace(",", "")
            # 숫자만 추출 (첫 번째 정수)
            m = re.search(r"\b(\d{1,7})\b", ans)
            if m:
                num = m.group(1)
                if int(num) > 0:
                    return num
            return None
        except Exception as e:
            print(f"Gemini 직원수 추정 오류: {str(e)}")
            return None

    def infer_korean_company_name(self, company_name: str) -> Optional[str]:
        """
        영문/혼용 회사명을 보고 나이스 DB용 한글 회사명(공식명) 하나만 추론.
        같은 회사를 찾을 때 사용. 모르면 None.
        """
        if not self.model or not (company_name or "").strip():
            return None
        name = (company_name or "").strip()
        prompt = f"""다음 회사명은 한국에 있는 회사의 영문/영문표기 이름입니다.
이 회사의 **한국어 공식 회사명**(한글업체명)을 하나만 답하세요. 예: 삼성전자(주), 현대자동차, SK텔레콤.

회사명: {name}

규칙:
- 반드시 한글 회사명만 출력하세요. (주), (유) 등은 포함해도 됨.
- 다른 회사가 아니고 이 회사와 동일한 회사인지 확실할 때만 답하세요.
- 모르거나 확실하지 않으면 NONE만 답하세요.
- 답변은 회사명 한 줄만."""
        try:
            resp = self.model.generate_content(prompt)
            ans = (resp.text or "").strip().splitlines()[0].strip().strip('"').strip("'")
            if not ans or ans.upper() == "NONE":
                return None
            return ans
        except Exception as e:
            print(f"Gemini 한글회사명 추론 오류: {str(e)}")
            return None

    def infer_company_website(
        self,
        company_name: str,
        description: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Optional[str]:
        """
        회사명(및 설명·국가)으로 공식 웹사이트 URL을 추론.
        검색 결과에 나올 만한 실제 회사 사이트 하나만 반환.
        """
        if not self.model or not (company_name or "").strip():
            return None
        import re
        name = (company_name or "").strip()
        desc = (description or "").strip()[:500]
        country_str = (country or "").strip()
        context = f"회사명: {name}"
        if desc:
            context += f"\n설명: {desc}"
        if country_str:
            context += f"\n국가/지역: {country_str}"
        prompt = f"""다음 기업의 **공식 웹사이트 URL** 하나만 알려주세요.

{context}

규칙:
- 반드시 실제로 존재하는 기업 공식/소개 페이지 URL만 답하세요.
- 검색엔진·포털 메인 페이지는 쓰지 마세요. (예: Google이면 google.com 검색창이 아니라 about.google 같은 회사 소개 페이지, 네이버면 naver.com이 아니라 해당 회사의 공식 사이트)
- 대기업/유명 기업은 회사 소개·About·코퍼레이트 페이지를 우선하세요. (예: about.google, www.samsung.com, about.amazon)
- 개인 이메일/메일서비스 도메인(gmail, naver, maver 등)은 답하지 마세요.
- 존재하지 않거나 확실하지 않은 사이트는 답하지 마세요. 모르면 NONE만 답하세요.
- 답변은 URL만 한 줄로 출력하세요. 설명 없이 URL만."""
        try:
            resp = self.model.generate_content(prompt)
            ans = (resp.text or "").strip().splitlines()[0].strip().strip('"').strip("'")
            if not ans or ans.upper() == "NONE":
                return None
            # https 없으면 추가
            if not ans.startswith("http://") and not ans.startswith("https://"):
                ans = "https://" + ans
            # 유효한 URL 형태인지 (도메인 포함)
            if re.search(r"^https?://[^\s/]+", ans):
                return ans
            return None
        except Exception as e:
            print(f"Gemini 웹사이트 추론 오류: {str(e)}")
            return None
    
    def convert_ksic_to_sic(
        self,
        ksic_code: str,
        ksic_description: Optional[str] = None
    ) -> Optional[Dict]:
        """
        KSIC 코드를 SIC 코드로 변환 (Gemini 활용)
        
        Args:
            ksic_code: KSIC 코드 (5자리)
            ksic_description: KSIC 설명 (선택)
            
        Returns:
            SIC 코드 정보 딕셔너리 또는 None
        """
        if not ksic_code or len(str(ksic_code).strip()) == 0:
            return None
        
        ksic_str = str(ksic_code).strip()
        
        # KSIC 코드 설명 구성
        context = f"KSIC 코드: {ksic_str}"
        if ksic_description:
            context += f"\nKSIC 설명: {ksic_description}"
        
        prompt = f"""다음 KSIC(한국표준산업분류) 코드를 SIC(미국 표준 산업 분류) 코드로 변환해주세요.

{context}

SIC 코드는 4자리 숫자입니다. 다음 형식으로만 답변해주세요:
SIC_CODE: 4자리 숫자
SIC_DESCRIPTION: 영어 설명

예시:
SIC_CODE: 7371
SIC_DESCRIPTION: Computer Programming Services

만약 정확한 매핑이 어렵다면 가장 유사한 대분류의 SIC 코드를 제공해주세요."""

        try:
            response = self.model.generate_content(prompt)
            answer = response.text.strip()
            
            # SIC 코드와 설명 추출
            import re
            sic_code_match = re.search(r'SIC_CODE:\s*(\d{4})', answer, re.IGNORECASE)
            sic_desc_match = re.search(r'SIC_DESCRIPTION:\s*(.+)', answer, re.IGNORECASE)
            
            if sic_code_match:
                sic_code = sic_code_match.group(1)
                sic_description = sic_desc_match.group(1).strip() if sic_desc_match else ''
                
                return {
                    'SIC_Code': sic_code,
                    'SIC_Description': sic_description
                }
            
            return None
            
        except Exception as e:
            print(f"Gemini KSIC→SIC 변환 오류 ({ksic_code}): {str(e)}")
            return None
