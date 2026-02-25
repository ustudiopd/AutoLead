"""
결과 조회 라우트
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import pandas as pd
from ..models import ResultsResponse, ResultRow, Statistics
from ..job_manager import job_manager

router = APIRouter(prefix="/api", tags=["results"])


@router.get("/results/{job_id}", response_model=ResultsResponse)
async def get_results(job_id: str, skip: int = 0, limit: int = 100):
    """
    처리 결과 조회
    
    Args:
        job_id: 작업 ID
        skip: 건너뛸 행 수
        limit: 반환할 행 수
        
    Returns:
        처리 결과
    """
    job = job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    
    if job['status'].value != 'completed':
        raise HTTPException(status_code=400, detail="작업이 아직 완료되지 않았습니다.")
    
    result_path = job.get('result_path')
    if not result_path or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")
    
    # CSV 파일 읽기
    try:
        df = pd.read_csv(result_path, encoding='utf-8-sig')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV 파일 읽기 오류: {str(e)}")
    
    # 통계 생성
    statistics = Statistics(
        total=len(df),
        high=len(df[df.get('Confidence_Score', '') == 'High']),
        medium=len(df[df.get('Confidence_Score', '') == 'Medium']),
        low=len(df[df.get('Confidence_Score', '') == 'Low'])
    )
    
    # 페이지네이션
    total_rows = len(df)
    paginated_df = df.iloc[skip:skip + limit]
    
    # 행 데이터 변환
    rows = [
        ResultRow(data=row.to_dict())
        for _, row in paginated_df.iterrows()
    ]
    
    return ResultsResponse(
        job_id=job_id,
        total=total_rows,
        rows=rows,
        statistics=statistics
    )


@router.get("/results/{job_id}/download")
async def download_results(job_id: str):
    """
    결과 파일 다운로드
    
    Args:
        job_id: 작업 ID
        
    Returns:
        CSV 파일
    """
    job = job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    
    result_path = job.get('result_path')
    if not result_path or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")
    
    return FileResponse(
        result_path,
        media_type='text/csv',
        filename=f"enriched_leads_{job_id}.csv"
    )
