#!/usr/bin/env python3
"""Apply the transmission arm of the V19 Layer-A correction experiment."""
from __future__ import annotations
from pathlib import Path
import argparse, json
import pandas as pd


def apply(case_dir: str | Path, transmission_case: str) -> dict:
    case_dir = Path(case_dir)
    inp = case_dir / "inputs"
    if transmission_case == "TX_policy":
        report={"status":"PASS","transmission_case":transmission_case,"action":"frozen policy build envelope retained"}
        audits=case_dir/"audits"; audits.mkdir(exist_ok=True)
        (audits/"future_correction_transmission_application.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return report
    if transmission_case != "TX_fixed":
        raise ValueError("V19 Layer-A supports only TX_policy and TX_fixed")
    limits_f = inp / "build_tx_limits.csv"
    lines_f = inp / "transmission_lines.csv"
    limits = pd.read_csv(limits_f)
    lines = pd.read_csv(lines_f)
    limits["build_trans_limit_mw"] = 0.0
    lines["trans_new_build_allowed"] = False
    lines["trans_new_build_cap"] = 0.0
    limits.to_csv(limits_f, index=False)
    lines.to_csv(lines_f, index=False)
    report = {
        "status": "PASS",
        "transmission_case": transmission_case,
        "action": "no new interprovincial transmission; existing capacity remains dispatchable",
        "all_new_build_flags_disabled": bool(lines["trans_new_build_allowed"].astype(str).str.strip().str.lower().isin({"false","0","no","n","f"}).all()),
        "line_new_build_cap_max_mw": float(pd.to_numeric(lines["trans_new_build_cap"], errors="coerce").fillna(0).max()),
        "period_build_limit_max_mw": float(pd.to_numeric(limits["build_trans_limit_mw"], errors="coerce").fillna(0).max()),
    }
    audits = case_dir / "audits"
    audits.mkdir(exist_ok=True)
    (audits / "future_correction_transmission_application.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("case_dir"); ap.add_argument("--transmission-case",required=True,choices=["TX_policy","TX_fixed"]); a=ap.parse_args()
    print(json.dumps(apply(a.case_dir,a.transmission_case),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
