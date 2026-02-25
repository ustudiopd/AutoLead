"""
처리 서비스 - 실제 데이터 처리 로직
"""
import asyncio
import sys
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


class ProcessorService:
    """데이터 처리 서비스"""
    
    def __init__(self):
        self.data_processor = DataProcessor()
    
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
            
            # CSV 파일 로드
            df = pd.read_csv(input_path, encoding='utf-8-sig')
            total = len(df)
            
            job_manager.update_progress(
                job_id, 0, total, "파일 로드 완료"
            )
            if progress_callback:
                await progress_callback(job_id, 0, total, "파일 로드 완료")
            
            # 각 행 처리
            enriched_rows = []
            for idx, row in df.iterrows():
                company_name = row.get('Company name', 'N/A')
                
                try:
                    enriched_row = self.data_processor.process_lead(row)
                    enriched_rows.append(enriched_row)
                    
                    # DART 검색 결과 확인
                    dart_corp_name = enriched_row.get('DART_Corp_Name', '')
                    if not dart_corp_name:
                        print(f"경고: {company_name} - DART 회사명을 찾지 못했습니다.")
                    
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    print(f"오류 발생 ({company_name}): {str(e)}")
                    print(f"상세 오류:\n{error_detail}")
                    # 오류 발생 시 원본 데이터 유지
                    enriched_row = row.to_dict()
                    enriched_row['DART_Corp_Name'] = ''
                    enriched_row['DART_Address'] = ''
                    enriched_row['DART_Website'] = ''
                    enriched_row['DART_KSIC_Code'] = ''
                    enriched_row['Match_Count'] = 0
                    enriched_row['Search_Method'] = 'error'
                    enriched_rows.append(enriched_row)
                
                # 진행 상황 업데이트 (각 행 처리 후)
                current = idx + 1
                job_manager.update_progress(
                    job_id, current, total, company_name
                )
                
                if progress_callback:
                    await progress_callback(job_id, current, total, company_name)
                    
                    # 비동기 처리 중 다른 작업 허용
                    await asyncio.sleep(0.01)
            
            # 결과 데이터프레임 생성
            enriched_df = pd.DataFrame(enriched_rows)
            
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


processor_service = ProcessorService()
