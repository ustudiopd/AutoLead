"""
처리 서비스 - 실제 데이터 처리 로직
"""
import asyncio
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_processor import DataProcessor
from src.ksic_sic_mapper import KSICSICMapper
from .job_manager import job_manager
from .models import ProgressUpdate, JobStatus


def _safe_print(msg: str) -> None:
    """cp949 등 콘솔 인코딩에서 한글 오류 방지"""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc))


class ProcessorService:
    """데이터 처리 서비스"""
    
    # 병렬 처리 동시 실행 수 (API 부하 고려)
    PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", "10") or "10")

    def __init__(self):
        self.data_processor = DataProcessor()

    def _process_single_row(
        self,
        idx: int,
        row,
        allowed_industries: Optional[list],
    ):
        """한 행 동기 처리. 병렬 실행용. (idx, enriched_row) 반환."""
        import re
        import pandas as pd
        company_name = row.get("Company name", "N/A")

        def _clear_placeholders(r: dict) -> None:
            ind = (r.get("Industry") or "").strip().lower()
            if ind in ("other", "n/a", ""):
                r["Industry"] = ""
            emp = (r.get("No of Employees") or "").strip()
            if not emp or emp.lower() == "unknown" or re.search(r"^\d+\s*-\s*\d+", emp) or re.search(r"^\d+\+", emp):
                r["No of Employees"] = ""
            desc = (r.get("Description") or "").strip().lower()
            if desc in ("not available", "n/a", "na", ""):
                r["Description"] = ""

        try:
            enriched_row = self.data_processor.process_lead(row)
            _clear_placeholders(enriched_row)
            try:
                from src.gemini_client import GeminiClient
                gc = GeminiClient()
                cname = str(row.get("Company name") or row.get("Company") or "")
                desc = str(enriched_row.get("Description") or row.get("Description") or "")
                if allowed_industries:
                    picked = gc.pick_industry_from_choices(
                        company_name=cname,
                        website=str(enriched_row.get("Website") or row.get("Website") or ""),
                        description=desc,
                        choices=allowed_industries,
                    )
                    if picked:
                        enriched_row["Industry"] = picked
                else:
                    inferred = gc.infer_industry(company_name=cname, description=desc or None)
                    if inferred:
                        enriched_row["Industry"] = inferred
            except Exception:
                pass
            dart_corp_name = enriched_row.get("DART_Corp_Name", "")
            if not dart_corp_name:
                _safe_print(f"경고: {company_name} - DART 회사명을 찾지 못했습니다.")
            return (idx, enriched_row)
        except Exception as e:
            import traceback
            _safe_print(f"오류 발생 ({company_name}): {str(e)}")
            _safe_print(f"상세 오류:\n{traceback.format_exc()}")
            enriched_row = row.to_dict()
            enriched_row["DART_Corp_Name"] = ""
            enriched_row["DART_Address"] = ""
            enriched_row["DART_Website"] = ""
            enriched_row["DART_KSIC_Code"] = ""
            enriched_row["Match_Count"] = 0
            enriched_row["Search_Method"] = "error"
            def _s(v):
                try:
                    if pd.isna(v):
                        return ""
                except Exception:
                    pass
                return str(v).strip() if v is not None else ""
            enriched_row["Industry"] = _s(enriched_row.get("Industry") or row.get("Industry") or "")
            enriched_row["Website"] = _s(enriched_row.get("Website") or row.get("Website") or "")
            if not enriched_row["Website"]:
                em = _s(row.get("Work email") or row.get("Email Address") or "")
                dom = em.split("@")[-1].lower() if "@" in em else ""
                if dom and dom not in {"gmail.com","naver.com","daum.net","hanmail.net","outlook.com","hotmail.com","icloud.com","yahoo.com","maver.com","nate.com","kakao.com","kakao.co.kr"}:
                    enriched_row["Website"] = f"https://{dom}"
            enriched_row["No of Employees"] = _s(enriched_row.get("No of Employees") or row.get("No of Employees") or "")
            enriched_row["Description"] = _s(enriched_row.get("Description") or row.get("Description") or "")
            for ec_col in ("Employee_Count_Source", "Employee_Count_Source_Tier", "Employee_Count_Match_Method", "Employee_Count_Evidence", "Employee_Count_Status", "Employee_Count_Source_URL"):
                enriched_row[ec_col] = ""
            _clear_placeholders(enriched_row)
            return (idx, enriched_row)

    async def process_file_async(
        self,
        job_id: str,
        input_path: str,
        output_path: str,
        progress_callback: Optional[Callable] = None
    ):
        """
        파일 비동기 처리
        
        Args:
            job_id: 작업 ID
            input_path: 입력 파일 경로
            output_path: 출력 파일 경로
            progress_callback: 진행 상황 콜백 함수
        """
        try:
            import pandas as pd
            import difflib
            
            input_path_obj = Path(input_path)
            suffix = input_path_obj.suffix.lower()

            allowed_industries = None

            # CSV/XLSX 파일 로드
            if suffix in (".xlsx", ".xlsm", ".xls"):
                xl = pd.ExcelFile(input_path)
                sheet = None
                for name in xl.sheet_names:
                    n = (name or "").strip()
                    if n.startswith("ListUploadROE_Template"):
                        sheet = name
                        break
                if sheet is None:
                    sheet = xl.sheet_names[0]

                # 템플릿은 2번째 줄이 실제 헤더인 케이스가 많음
                df = pd.read_excel(input_path, sheet_name=sheet, header=1)

                # Industry 탭 허용값 로드
                try:
                    ind_df = pd.read_excel(input_path, sheet_name="Industry")
                    if ind_df is not None and ind_df.shape[1] >= 1:
                        col0 = ind_df.columns[0]
                        vals = (
                            ind_df[col0]
                            .dropna()
                            .astype(str)
                            .map(lambda x: x.strip())
                            .tolist()
                        )
                        allowed_industries = [v for v in vals if v]
                except Exception:
                    allowed_industries = None
            else:
                df = pd.read_csv(input_path, encoding='utf-8-sig')

            # 테스트 모드: 상단 N줄만 처리 (환경변수 PROCESS_ROW_LIMIT)
            try:
                limit = int(os.getenv("PROCESS_ROW_LIMIT", "0") or "0")
            except Exception:
                limit = 0
            if limit and limit > 0:
                df = df.head(limit)

            # 내부 처리 컬럼 정규화 (템플릿 ↔ 내부 파이프라인, 나이스 엑셀 등)
            if "Company name" not in df.columns and "Company" in df.columns:
                df["Company name"] = df["Company"]
            if "Company name" not in df.columns and "한글업체명" in df.columns:
                df["Company name"] = df["한글업체명"].fillna("").astype(str)
            if "Work email" not in df.columns and "Email Address" in df.columns:
                df["Work email"] = df["Email Address"]
            # 템플릿/CSV 어느 쪽이든 Website/Industry/Employees/Description 컬럼 유지
            if "Website" not in df.columns and "Website " in df.columns:
                df["Website"] = df["Website "]
            if "Website" not in df.columns and "홈페이지" in df.columns:
                df["Website"] = df["홈페이지"].fillna("").astype(str).map(lambda x: ("https://" + x) if x and not str(x).startswith("http") else x)
            if "Industry" not in df.columns and "Industry " in df.columns:
                df["Industry"] = df["Industry "]
            if "Industry" not in df.columns and "대분류산업명" in df.columns:
                df["Industry"] = df["대분류산업명"].fillna("").astype(str)
            if "No of Employees" not in df.columns and "종업원수" in df.columns:
                df["No of Employees"] = df["종업원수"].fillna("").astype(str).map(lambda x: str(int(float(x))) if str(x).replace(".", "").isdigit() else "")

            # 출력에 필요한 컬럼(4개) 없으면 생성
            for col in ("Industry", "Website", "No of Employees", "Description"):
                if col not in df.columns:
                    df[col] = ""

            # Industry는 템플릿 Industry 탭 값 중에서만 선택되게 강제
            if allowed_industries:
                # 엑셀에 값이 있어도 허용 목록으로 교정만 하고,
                # 엑셀이 비어 있으면 Gemini가 회사명/웹/설명 기반으로 허용 목록 중 하나를 선택
                allowed_norm = {(" ".join(v.split())).lower(): v for v in allowed_industries}
                keys = list(allowed_norm.keys())

                def _coerce_ind(v: object) -> str:
                    s = "" if pd.isna(v) else str(v)
                    s = " ".join(s.strip().split())
                    if not s:
                        return ""
                    k = s.lower()
                    if k in allowed_norm:
                        return allowed_norm[k]
                    m = difflib.get_close_matches(k, keys, n=1, cutoff=0.82)
                    if m:
                        return allowed_norm[m[0]]
                    return ""

                df["Industry"] = df["Industry"].map(_coerce_ind)

            total = len(df)
            
            job_manager.update_progress(
                job_id, 0, total, "파일 로드 완료"
            )
            if progress_callback:
                await progress_callback(job_id, 0, total, "파일 로드 완료")
            
            # 각 행 병렬 처리 (스레드 풀, 동시 실행 수 제한)
            loop = asyncio.get_event_loop()
            sem = asyncio.Semaphore(self.PARALLEL_WORKERS)
            rows_list = list(df.iterrows())
            executor = ThreadPoolExecutor(max_workers=self.PARALLEL_WORKERS)

            async def process_one(idx, row):
                async with sem:
                    return await loop.run_in_executor(
                        executor,
                        self._process_single_row,
                        idx,
                        row,
                        allowed_industries,
                    )

            try:
                tasks = [process_one(idx, row) for idx, row in rows_list]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # gather 순서 = tasks 순서이므로 그대로 사용
                enriched_rows = []
                for i, r in enumerate(results):
                    if isinstance(r, Exception):
                        _, fallback = self._process_single_row(
                            rows_list[i][0], rows_list[i][1], allowed_industries
                        )
                        enriched_rows.append(fallback)
                    else:
                        enriched_rows.append(r[1])
            finally:
                executor.shutdown(wait=True)

            completed = len(enriched_rows)
            job_manager.update_progress(job_id, completed, total, "병렬 처리 완료")
            if progress_callback:
                await progress_callback(job_id, completed, total, "병렬 처리 완료")

            # 결과 데이터프레임 생성
            enriched_df = pd.DataFrame(enriched_rows)
            # 필수 컬럼 + 직원수 출처 컬럼 존재 보장
            required_cols = (
                "Industry", "Website", "No of Employees", "Description",
                "Employee_Count_Source", "Employee_Count_Source_Tier", "Employee_Count_Match_Method",
                "Employee_Count_Evidence", "Employee_Count_Status", "Employee_Count_Source_URL",
            )
            for col in required_cols:
                if col not in enriched_df.columns:
                    enriched_df[col] = ""
                else:
                    enriched_df[col] = enriched_df[col].fillna("").astype(str).map(lambda x: x.strip())
            # 저장 직전 플레이스홀더 최종 제거 (원본 컬럼이 그대로 남은 경우 대비)
            import re
            def _clear_cell(v, col):
                s = (v or "").strip()
                if col == "Industry" and s.lower() in ("other", "n/a", ""):
                    return ""
                if col == "No of Employees" and (not s or s.lower() == "unknown" or re.match(r"^\d+\s*-\s*\d+", s) or re.match(r"^\d+\+", s)):
                    return ""
                if col == "Description" and s.lower() in ("not available", "n/a", "na", ""):
                    return ""
                return s
            for col in ("Industry", "No of Employees", "Description"):
                if col in enriched_df.columns:
                    enriched_df[col] = enriched_df[col].map(lambda x: _clear_cell(x, col))
            # 명시적 문자열 치환 (플레이스홀더 → 빈칸)
            if "Industry" in enriched_df.columns:
                enriched_df["Industry"] = enriched_df["Industry"].astype(str).str.strip().replace(["Other", "other", "N/A", "n/a"], "")
            if "No of Employees" in enriched_df.columns:
                enriched_df["No of Employees"] = enriched_df["No of Employees"].astype(str).str.strip().replace("Unknown", "")
                enriched_df["No of Employees"] = enriched_df["No of Employees"].replace(re.compile(r"^\d+\s*-\s*\d+"), "", regex=True)
            if "Description" in enriched_df.columns:
                enriched_df["Description"] = enriched_df["Description"].astype(str).str.strip().replace(["Not available", "not available", "N/A", "n/a"], "")

            # Website가 여전히 비어 있으면 DART_Website → Work email 도메인 기반 URL로 채움
            if "DART_Website" in enriched_df.columns:
                dw = enriched_df["DART_Website"].fillna("").astype(str).map(lambda x: x.strip())
                enriched_df.loc[enriched_df["Website"] == "", "Website"] = dw
            if "Work email" in enriched_df.columns:
                def _dom(email: str) -> str:
                    s = (email or "").strip()
                    return s.split("@")[-1].lower() if "@" in s else ""
                free = {"gmail.com","naver.com","daum.net","hanmail.net","outlook.com","hotmail.com","icloud.com","yahoo.com","maver.com","nate.com","kakao.com","kakao.co.kr"}
                doms = enriched_df["Work email"].fillna("").astype(str).map(_dom)
                mask = (enriched_df["Website"] == "") & (doms != "") & (~doms.isin(list(free)))
                enriched_df.loc[mask, "Website"] = doms[mask].map(lambda d: f"https://{d}")
            
            # KSIC→SIC 매핑 적용
            mapping_csv = project_root / 'data' / 'ksic_to_sic_mapping.csv'
            mapper = KSICSICMapper(str(mapping_csv) if mapping_csv.exists() else None)
            
            sic_codes = []
            sic_descriptions = []
            
            for idx, row in enriched_df.iterrows():
                ksic_code = row.get('DART_KSIC_Code', '')
                sic_info = mapper.map_ksic_to_sic(ksic_code, ksic_description=None)
                
                if sic_info:
                    sic_codes.append(sic_info['SIC_Code'])
                    sic_descriptions.append(sic_info.get('SIC_Description', ''))
                else:
                    sic_codes.append('')
                    sic_descriptions.append('')
            
            enriched_df['SIC_Code'] = sic_codes
            enriched_df['SIC_Description'] = sic_descriptions
            
            # 결과 저장
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            enriched_df.to_csv(str(output_path), index=False, encoding='utf-8-sig')

            # 저장 후 안전장치: 일부 환경에서 NaN/빈값이 그대로 남는 경우가 있어 한 번 더 강제 채움 후 덮어씀
            try:
                _df = pd.read_csv(str(output_path), encoding="utf-8-sig")
                for col in ("Industry", "Website", "No of Employees", "Description"):
                    if col not in _df.columns:
                        _df[col] = ""
                    else:
                        _df[col] = _df[col].fillna("").astype(str).map(lambda x: x.strip())

                # Website 재보강
                if "DART_Website" in _df.columns:
                    dw = _df["DART_Website"].fillna("").astype(str).map(lambda x: x.strip())
                    _df.loc[_df["Website"] == "", "Website"] = dw
                if "Work email" in _df.columns:
                    def _dom(email: str) -> str:
                        s = (email or "").strip()
                        return s.split("@")[-1].lower() if "@" in s else ""
                    free = {"gmail.com","naver.com","daum.net","hanmail.net","outlook.com","hotmail.com","icloud.com","yahoo.com","maver.com","nate.com","kakao.com","kakao.co.kr"}
                    doms = _df["Work email"].fillna("").astype(str).map(_dom)
                    mask = (_df["Website"] == "") & (doms != "") & (~doms.isin(list(free)))
                    _df.loc[mask, "Website"] = doms[mask].map(lambda d: f"https://{d}")

                _df.to_csv(str(output_path), index=False, encoding="utf-8-sig")
            except Exception:
                pass
            
            # 통계 생성
            from .models import Statistics
            statistics = Statistics(
                total=len(enriched_df),
                high=len(enriched_df[enriched_df['Confidence_Score'] == 'High']),
                medium=len(enriched_df[enriched_df['Confidence_Score'] == 'Medium']),
                low=len(enriched_df[enriched_df['Confidence_Score'] == 'Low'])
            )
            
            # 작업 완료
            job_manager.complete_job(job_id, output_path, statistics)
            
            if progress_callback:
                await progress_callback(job_id, total, total, "처리 완료")
            
        except Exception as e:
            error_msg = str(e)
            job_manager.fail_job(job_id, error_msg)
            if progress_callback:
                await progress_callback(job_id, 0, 0, f"오류: {error_msg}")
            raise


processor_service = ProcessorService()
