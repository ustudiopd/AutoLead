"""
FastAPI 메인 애플리케이션
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .routes import upload, process, results, websocket, search

app = FastAPI(
    title="AutoLead - 리드 데이터 자동 보강 시스템",
    description="DART API를 활용한 리드 데이터 자동 보강 및 KSIC→SIC 변환 시스템",
    version="1.0.0"
)

# 라우터 등록
app.include_router(upload.router)
app.include_router(process.router)
app.include_router(results.router)
app.include_router(websocket.router)
app.include_router(search.router)

# 정적 파일 서빙
static_path = Path(__file__).parent.parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# CORS 설정 (개발용)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def read_root():
    """메인 페이지"""
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "AutoLead API Server", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """헬스 체크"""
    return {"status": "ok"}
