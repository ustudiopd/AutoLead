"""
엔리치 파이프라인 테스트 (Industry / No of Employees / Description 반영 확인)
사용: PROCESS_ROW_LIMIT=5 python scripts/run_enrich_test.py
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# 0이면 전체, 미설정/양수면 해당 행 수만 처리 (기본 10)
if "PROCESS_ROW_LIMIT" not in os.environ or os.environ.get("PROCESS_ROW_LIMIT") == "":
    os.environ["PROCESS_ROW_LIMIT"] = "10"

from src.api.processor_service import processor_service

def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(str(msg).encode(enc, errors="replace").decode(enc))

def main():
    # 사용자 제공 파일만 사용 (실제 파일 내용으로 테스트)
    # 기본은 TEST1. 필요 시 TEST_INPUT_PATH 환경변수로 다른 파일 지정(예: TEST2) 가능.
    input_path = project_root / "output" / "docs" / "TEST1. FY26 UPDATED_List Upload ROE Template (SMC) - Service Decoded 2 260303.xlsx"
    override = (os.getenv("TEST_INPUT_PATH", "") or "").strip()
    if override:
        try:
            input_path = Path(override)
            if not input_path.is_absolute():
                input_path = (project_root / override).resolve()
        except Exception:
            pass

    # 경로를 직접 지정하기 어려운 경우(윈도우 콘솔 인코딩 등) 힌트로 파일 자동 선택
    hint = (os.getenv("TEST_INPUT_HINT", "") or "").strip()
    if hint:
        try:
            docs_dir = project_root / "output" / "docs"
            cand = []
            for p in docs_dir.glob("*.xlsx"):
                if hint.lower() in p.name.lower():
                    cand.append(p)
            if cand:
                cand.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                input_path = cand[0]
        except Exception:
            pass
    if not input_path.exists():
        _safe_print(f"입력 파일이 없습니다: {input_path}")
        return 1
    # 실제 파일에서 시트·행 수 확인
    import pandas as pd
    xl = pd.ExcelFile(input_path)
    data_sheet = None
    for name in xl.sheet_names:
        if (name or "").strip().startswith("ListUploadROE_Template"):
            data_sheet = name
            break
    data_sheet = data_sheet or xl.sheet_names[0]
    df_preview = pd.read_excel(input_path, sheet_name=data_sheet, header=1)
    company_col = df_preview.get("Company name") if "Company name" in df_preview.columns else df_preview.get("Company")
    total_rows = len(df_preview)
    try:
        limit = int(os.getenv("PROCESS_ROW_LIMIT", "10") or "10")
    except Exception:
        limit = 10
    # 0 = 전체 행 처리
    apply_limit = total_rows if limit <= 0 else min(limit, total_rows)
    _safe_print(f"입력 파일(실제 데이터): {input_path.name}")
    _safe_print(f"데이터 시트: {data_sheet} | 전체 행: {total_rows} | 테스트 행 수: {apply_limit}")
    if company_col is not None:
        sample = company_col.dropna().astype(str).head(5).tolist()
        _safe_print(f"샘플 회사명: {sample}")
    os.environ["PROCESS_ROW_LIMIT"] = str(apply_limit)
    # 실행 시마다 새 파일로 저장 (수정 시각으로 방금 만든 결과 확인 가능)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = project_root / "output" / f"enriched_test_run_{stamp}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    job_id = "test-run"
    output_abs = output_path.resolve()
    _safe_print(f"출력(절대경로): {output_abs}")
    asyncio.run(processor_service.process_file_async(job_id, str(input_path), str(output_abs)))
    if not output_abs.exists():
        _safe_print(f"오류: 결과 파일이 생성되지 않았습니다. {output_abs}")
        return 1
    _safe_print(f"저장 완료: {output_abs}")
    _safe_print(f"결과 샘플 (Industry / No of Employees / Description) - 상위 {apply_limit}행:")
    df = pd.read_csv(output_abs, encoding="utf-8-sig", nrows=20)
    n_show = min(apply_limit, len(df))
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    for col in ("Industry", "No of Employees", "Description"):
        if col in df.columns:
            out = f"  {col}: {df[col].head(n_show).tolist()}"
            try:
                _safe_print(out)
            except UnicodeEncodeError:
                _safe_print(out.encode(enc, errors="replace").decode(enc))
    return 0

if __name__ == "__main__":
    sys.exit(main())
