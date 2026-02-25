"""
DART 검색 라우트
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ..models import JobResponse
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dart_client import DartClient

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search/company")
async def search_company(
    company_name: str = Query(..., description="검색할 회사명"),
    email_domain: Optional[str] = Query(None, description="이메일 도메인 (선택)")
):
    """
    DART에서 회사 검색
    
    Args:
        company_name: 검색할 회사명
        email_domain: 이메일 도메인 (선택)
        
    Returns:
        검색된 회사 정보
    """
    try:
        client = DartClient(use_gemini=True)
        
        result = client.enrich_company_data(
            company_name=company_name,
            email_domain=email_domain
        )
        
        if result:
            return {
                "success": True,
                "data": {
                    "corp_name": result.get("corp_name", ""),
                    "corp_code": result.get("corp_code", ""),
                    "stock_code": result.get("stock_code", ""),
                    "address": result.get("adres", ""),
                    "website": result.get("hmurl", ""),
                    "ksic_code": result.get("induty_code", ""),
                    "ksic_name": result.get("induty_nm", ""),
                    "ceo_name": result.get("ceo_nm", ""),
                    "established_date": result.get("est_dt", ""),
                    "match_count": result.get("match_count", 0),
                    "search_method": result.get("search_method", "company_name"),
                    "all_matches": result.get("all_matches", [])
                }
            }
        else:
            return {
                "success": False,
                "message": "회사를 찾을 수 없습니다.",
                "data": None
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {str(e)}")
