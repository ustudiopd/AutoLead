"""
파일 업로드 라우트
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import aiofiles
import uuid

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    CSV 파일 업로드
    
    Returns:
        업로드된 파일명
    """
    # 파일 확장자 검증
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드 가능합니다.")
    
    # 업로드 디렉토리 생성
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    # 고유 파일명 생성
    file_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix
    saved_filename = f"{file_id}{file_extension}"
    file_path = upload_dir / saved_filename
    
    # 파일 저장
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    return {
        "filename": saved_filename,
        "original_filename": file.filename,
        "size": len(content)
    }
