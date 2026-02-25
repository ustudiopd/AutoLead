"""
처리 라우트
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pathlib import Path
from ..models import ProcessRequest, JobResponse, JobStatusResponse
from ..job_manager import job_manager
from ..processor_service import processor_service

router = APIRouter(prefix="/api", tags=["process"])


async def progress_callback(job_id: str, current: int, total: int, message: str):
    """진행 상황 콜백 (WebSocket으로 전송)"""
    try:
        from ..routes.websocket import websocket_manager
        from ..models import ProgressUpdate, JobStatus
        
        status = JobStatus.COMPLETED if current >= total else JobStatus.PROCESSING
        
        progress = ProgressUpdate(
            job_id=job_id,
            current=current,
            total=total,
            percentage=(current / total * 100) if total > 0 else 0,
            current_item=message,
            status=status
        )
        await websocket_manager.send_progress(job_id, progress)
    except Exception as e:
        # WebSocket 오류는 무시 (폴링으로 대체)
        pass


@router.post("/process", response_model=JobResponse)
async def start_processing(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    파일 처리 시작
    
    Args:
        request: 처리 요청 (파일명 포함)
        background_tasks: 백그라운드 작업
        
    Returns:
        작업 ID 및 상태
    """
    # 작업 생성
    job_id = job_manager.create_job()
    
    # 파일 경로 확인
    upload_dir = Path("uploads")
    input_path = upload_dir / request.filename
    
    if not input_path.exists():
        job_manager.fail_job(job_id, f"파일을 찾을 수 없습니다: {request.filename}")
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    
    # 출력 경로 설정
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_filename = f"enriched_{job_id}.csv"
    output_path = output_dir / output_filename
    
    # 백그라운드 작업 시작
    background_tasks.add_task(
        processor_service.process_file_async,
        job_id,
        str(input_path),
        str(output_path),
        progress_callback
    )
    
    return JobResponse(
        job_id=job_id,
        status=job_manager.get_job(job_id)['status'],
        message="처리가 시작되었습니다."
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    작업 상태 조회
    
    Args:
        job_id: 작업 ID
        
    Returns:
        작업 상태 및 진행 상황
    """
    job = job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    
    from ..models import JobStatusResponse
    return JobStatusResponse(
        job_id=job_id,
        status=job['status'],
        progress=job.get('progress'),
        statistics=job.get('statistics'),
        error=job.get('error')
    )
