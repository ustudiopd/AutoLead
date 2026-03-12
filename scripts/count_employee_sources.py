"""
엔리치 결과 CSV에서 'No of Employees'가 나이스 DB vs 크롤링 중 어디서 채워졌는지 건수 집계.
사용: python scripts/count_employee_sources.py [csv_path]
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from src.data_processor import _load_nice_employees, _normalize_for_lookup, DataProcessor


def _norm_emp_val(v) -> str:
    """CSV의 직원수 값을 나이스 DB와 비교 가능한 문자열로 (예: 681.0 -> 681)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if not s:
        return ""
    try:
        n = int(float(s))
        return str(n) if n > 0 else ""
    except Exception:
        return s


def main():
    csv_path = project_root / "output" / "enriched_TEST1_full_20260312_102349.csv"
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"파일 없음: {csv_path}")
        return 1

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    company_col = "Company name" if "Company name" in df.columns else "Company"
    emp_col = "No of Employees"
    if emp_col not in df.columns:
        print(f"컬럼 없음: {emp_col}")
        return 1

    nice = _load_nice_employees()
    dp = DataProcessor()
    count_nice = 0
    count_crawl = 0
    count_empty = 0

    for _, row in df.iterrows():
        emp_val = row.get(emp_col)
        emp_str = _norm_emp_val(emp_val)
        if not emp_str:
            count_empty += 1
            continue

        company = str(row.get(company_col) or "").strip()
        if not company:
            count_crawl += 1
            continue

        # 나이스에 해당 회사+직원수 조합이 있는지 확인 (동일 로직: raw, cleaned, normalized)
        key_raw = company
        key_cleaned = dp.clean_company_name(company)
        key_norm = _normalize_for_lookup(company)
        from_nice = (
            (key_raw and key_raw in nice and nice[key_raw] == emp_str)
            or (key_cleaned and key_cleaned in nice and nice[key_cleaned] == emp_str)
            or (key_norm and key_norm in nice and nice[key_norm] == emp_str)
        )
        if from_nice:
            count_nice += 1
        else:
            count_crawl += 1

    total_with_emp = count_nice + count_crawl
    print(f"파일: {csv_path.name}")
    print(f"전체 행: {len(df)}")
    print(f"직원수 있음: {total_with_emp}  (비어 있음: {count_empty})")
    print(f"  - 나이스 DB에서 채워진 건수: {count_nice}")
    print(f"  - 크롤링(또는 기타)에서 채워진 건수: {count_crawl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
