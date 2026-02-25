"""
WebSocket 라우트 - 실시간 진행 상황 전송
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json
from ..models import ProgressUpdate, JobStatus
from ..job_manager import job_manager

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """WebSocket 연결 관리자"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str):
        """연결 추가"""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, job_id: str):
        """연결 제거"""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
    
    async def send_progress(self, job_id: str, progress: ProgressUpdate):
        """진행 상황 전송"""
        if job_id in self.active_connections:
            message = progress.model_dump_json()
            disconnected = set()
            for websocket in self.active_connections[job_id]:
                try:
                    await websocket.send_text(message)
                except Exception:
                    disconnected.add(websocket)
            
            # 끊어진 연결 제거
            for ws in disconnected:
                self.disconnect(ws, job_id)


manager = ConnectionManager()


@router.websocket("/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """
    WebSocket 연결 - 실시간 진행 상황 수신
    
    Args:
        websocket: WebSocket 연결
        job_id: 작업 ID
    """
    await manager.connect(websocket, job_id)
    
    try:
        # 초기 상태 전송
        job = job_manager.get_job(job_id)
        if job:
            if job.get('progress'):
                await websocket.send_text(job['progress'].model_dump_json())
        
        # 연결 유지
        while True:
            data = await websocket.receive_text()
            # 클라이언트로부터 메시지 수신 (필요시 처리)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)


# 전역 매니저 인스턴스 (다른 모듈에서 사용)
websocket_manager = manager
