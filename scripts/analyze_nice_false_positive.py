import os
import glob
import re
import sys
from difflib import SequenceMatcher

import pandas as pd


def _newest_enriched_csv() -> str:
    paths = glob.glob(os.path.join("output", "enriched_test_run_*.csv"))
    if not paths:
        raise SystemExit("No enriched_test_run_*.csv found under output/")
    paths.sort(key=os.path.getmtime, reverse=True)
    return paths[0]


def _norm(s: object) -> str:
    s = "" if s is None else str(s)
    s = s.lower().strip()
    s = " ".join(s.split())
    s = re.sub(r"[^a-z0-9가-힣 ]", " ", s)
    s = " ".join(s.split()).strip()
    return s


def _token_set(s: object) -> set[str]:
    stop = {"co", "ltd", "inc", "corp", "company", "the", "and", "of"}
    return {t for t in _norm(s).split(" ") if t and t not in stop}


def _parse_fuzzy_pair(evidence: str) -> tuple[str, str] | None:
    """
    Evidence 예:
      "NICE DB fuzzy match (Tech2worldwide... -> cheil worldwide...)"
    """
    ev = str(evidence or "")
    key = "fuzzy match ("
    i = ev.lower().find(key)
    if i < 0:
        return None
    j = ev.find(")", i)
    if j < 0:
        return None
    inside = ev[i + len(key) : j]
    if "->" not in inside:
        return None
    left, right = inside.split("->", 1)
    return left.strip(), right.strip()


def _analyze_one(path: str) -> dict:
    df = pd.read_csv(path, encoding="utf-8-sig")
    total_rows = len(df)

    if "Employee_Count_Source" not in df.columns:
        return {
            "path": path,
            "total_rows": total_rows,
            "has_employee_source": False,
        }

    nice = df[df["Employee_Count_Source"].fillna("") == "NICE_DB"].copy()
    nice_rows = len(nice)

    method_counts: dict[str, int] = {}
    if "Employee_Count_Match_Method" in nice.columns:
        vc = nice["Employee_Count_Match_Method"].fillna("EMPTY").value_counts()
        method_counts = {str(k): int(v) for k, v in vc.items()}

    fuzzy = nice[nice.get("Employee_Count_Match_Method", "").fillna("") == "NICE_FUZZY"].copy()
    fuzzy_total = len(fuzzy)

    pairs = []
    for _, r in fuzzy.iterrows():
        parsed = _parse_fuzzy_pair(r.get("Employee_Count_Evidence", ""))
        if not parsed:
            continue
        inp, mat = parsed
        a, b = _norm(inp), _norm(mat)
        sim = SequenceMatcher(None, a, b).ratio() if a and b else 0.0
        ta, tb = _token_set(inp), _token_set(mat)
        uni = ta.union(tb)
        jac = (len(ta.intersection(tb)) / len(uni)) if uni else 0.0
        pairs.append(
            {
                "company": r.get("Company name", ""),
                "input_part": inp,
                "matched_part": mat,
                "sim": sim,
                "token_jaccard": jac,
            }
        )

    pairs_df = pd.DataFrame(pairs)
    if len(pairs_df):
        susp = pairs_df[(pairs_df["token_jaccard"] < 0.15) & (pairs_df["sim"] < 0.78)].copy()
    else:
        susp = pairs_df
    suspicious = len(susp)

    top = []
    if suspicious:
        show = susp.sort_values(["token_jaccard", "sim"], ascending=[True, True]).head(12)
        top = show.to_dict(orient="records")

    return {
        "path": path,
        "total_rows": total_rows,
        "has_employee_source": True,
        "nice_rows": nice_rows,
        "method_counts": method_counts,
        "fuzzy_total": fuzzy_total,
        "parsed_fuzzy_pairs": int(len(pairs_df)),
        "suspicious_fuzzy_pairs": int(suspicious),
        "suspicious_rate_of_fuzzy": (round(suspicious / fuzzy_total, 3) if fuzzy_total else 0.0),
        "suspicious_rate_of_all_nice": (round(suspicious / nice_rows, 3) if nice_rows else 0.0),
        "top_suspicious": top,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if a.strip()]
    paths = args if args else [_newest_enriched_csv()]

    for idx, p in enumerate(paths):
        print("=" * 80)
        print(f"file: {p}")
        try:
            r = _analyze_one(p)
        except Exception as e:
            print(f"error: {e}")
            continue

        print(f"total_rows: {r.get('total_rows')}")
        if not r.get("has_employee_source"):
            print("No Employee_Count_Source column.")
            continue

        print(f"nice_rows: {r.get('nice_rows')}")
        print("NICE method breakdown:")
        mc = r.get("method_counts") or {}
        if mc:
            for k, v in sorted(mc.items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"  {k}: {v}")
        else:
            print("  (none)")

        print(f"fuzzy_total: {r.get('fuzzy_total')}")
        print(f"parsed_fuzzy_pairs: {r.get('parsed_fuzzy_pairs')}")
        print(f"suspicious_fuzzy_pairs: {r.get('suspicious_fuzzy_pairs')}")
        print(f"suspicious_rate_of_fuzzy: {r.get('suspicious_rate_of_fuzzy')}")
        print(f"suspicious_rate_of_all_nice: {r.get('suspicious_rate_of_all_nice')}")

        top = r.get("top_suspicious") or []
        if top:
            print("Top suspicious:")
            for rr in top:
                print(
                    f"- {rr.get('company','')} :: {rr.get('input_part','')} -> {rr.get('matched_part','')} "
                    f"(sim={float(rr.get('sim') or 0):.2f}, tokJ={float(rr.get('token_jaccard') or 0):.2f})"
                )

        if idx < len(paths) - 1:
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

