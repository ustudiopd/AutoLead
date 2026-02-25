"""
작업 관리자 - 배치 처리 작업 추적
"""
import uuid
import asyncio
from typing import Dict, Optional
from datetime import datetime
from .models import JobStatus, ProgressUpdate, Statistics
import pandas as pd


class JobManager:
    """작업 관리자 싱글톤"""
    _instance = None
    _jobs: Dict[str, Dict] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def create_job(self) -> str:
        """새 작업 생성"""
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            'status': JobStatus.PENDING,
            'created_at': datetime.now(),
            'progress': None,
            'statistics': None,
            'error': None,
            'result_path': None
        }
        return job_id
    
    def update_progress(
        self,
        job_id: str,
        current: int,
        total: int,
        current_item: str,
        status: JobStatus = JobStatus.PROCESSING
    ):
        """진행 상황 업데이트"""
        if job_id in self._jobs:
            percentage = (current / total * 100) if total > 0 else 0
            self._jobs[job_id]['progress'] = ProgressUpdate(
                job_id=job_id,
                current=current,
                total=total,
                percentage=percentage,
                current_item=current_item,
                status=status
            )
            self._jobs[job_id]['status'] = status
    
    def complete_job(self, job_id: str, result_path: str, statistics: Statistics):
        """작업 완료"""
        if job_id in self._jobs:
            self._jobs[job_id]['status'] = JobStatus.COMPLETED
            self._jobs[job_id]['result_path'] = result_path
            self._jobs[job_id]['statistics'] = statistics
            if self._jobs[job_id]['progress']:
                self._jobs[job_id]['progress'].status = JobStatus.COMPLETED
    
    def fail_job(self, job_id: str, error: str):
        """작업 실패"""
        if job_id in self._jobs:
            self._jobs[job_id]['status'] = JobStatus.FAILED
            self._jobs[job_id]['error'] = error
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """작업 정보 조회"""
        return self._jobs.get(job_id)
    
    def get_statistics_from_csv(self, csv_path: str) -> Statistics:
        """CSV 파일에서 통계 생성"""
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            total = len(df)
            high = len(df[df.get('Confidence_Score', '') == 'High'])
            medium = len(df[df.get('Confidence_Score', '') == 'Medium'])
            low = len(df[df.get('Confidence_Score', '') == 'Low'])
            return Statistics(total=total, high=high, medium=medium, low=low)
        except Exception:
            return Statistics(total=0, high=0, medium=0, low=0)


# 전역 작업 관리자 인스턴스
job_manager = JobManager()
