"""
Pydantic 모델 정의
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum


class JobStatus(str, Enum):
    """작업 상태"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ConfidenceScore(str, Enum):
    """신뢰도 점수"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ReviewStatus(str, Enum):
    """검토 상태"""
    APPROVED = "Approved"
    NEEDS_REVIEW = "Needs Review"


class ProcessRequest(BaseModel):
    """처리 요청 모델"""
    filename: str


class JobResponse(BaseModel):
    """작업 응답 모델"""
    job_id: str
    status: JobStatus
    message: str


class ProgressUpdate(BaseModel):
    """진행 상황 업데이트 모델"""
    job_id: str
    current: int
    total: int
    percentage: float
    current_item: str
    status: JobStatus
    message: Optional[str] = None


class Statistics(BaseModel):
    """통계 모델"""
    total: int
    high: int
    medium: int
    low: int


class JobStatusResponse(BaseModel):
    """작업 상태 응답 모델"""
    job_id: str
    status: JobStatus
    progress: Optional[ProgressUpdate] = None
    statistics: Optional[Statistics] = None
    error: Optional[str] = None


class ResultRow(BaseModel):
    """결과 행 모델"""
    data: Dict[str, Any]


class ResultsResponse(BaseModel):
    """결과 응답 모델"""
    job_id: str
    total: int
    rows: List[ResultRow]
    statistics: Statistics
