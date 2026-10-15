#!/usr/bin/env python3
"""Report strict progress across V20 Layer A/B/C without launching solvers."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def python_count(code: str, cwd: Path) -> tuple[int, list[str]]:
    p = subprocess.run([sys.executable, "-c", code], cwd=cwd, text=True, capture_output=True)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        return 0, []
    obj = json.loads(p.stdout.strip().splitlines()[-1])
    return int(obj["count"]), list(obj["scenarios"])


def main() -> None:
    module = ROOT / "modules" / "correction2033"
    a_code = r'''
import json, pandas as pd, sys
from pathlib import Path
root=Path.cwd(); sys.path.insert(0,str(root/'tools'))
import run_future_correction_batch as r
d=pd.read_csv(r.SCEN); ok=[]
for _,x in d.iterrows():
 rec=r.existing_official_record(x.to_dict())
 if rec is not None: ok.append(str(x.scenario))
print(json.dumps({'count':len(ok),'scenarios':ok}))
'''
    bc_code = r'''
import json, sys
from pathlib import Path
root=Path.cwd(); sys.path.insert(0,str(root/'tools'))
import run_v20_layer_b16 as b
names=b.official_scenarios()+['V20EH01_OBSERVED','V20EH02_OPTIMAL']; ok=[]
for s in names:
 if b.valid_row(s) is not None: ok.append(s)
print(json.dumps({'count':len(ok),'scenarios':ok}))
'''
    a, a_names = python_count(a_code, module)
    bc, bc_names = python_count(bc_code, ROOT)
    b_names = [s for s in bc_names if s.startswith("SL")]
    c_names = [s for s in bc_names if s.startswith("V20EH")]
    payload = {
        "version": "V20_HF4_REQUIRED_26_PROGRESS",
        "layer_a_strict": a,
        "layer_a_expected": 8,
        "layer_b_strict": len(b_names),
        "layer_b_expected": 16,
        "layer_c_strict": len(c_names),
        "layer_c_expected": 2,
        "strict_total": a + len(b_names) + len(c_names),
        "expected_total": 26,
        "remaining": 26 - a - len(b_names) - len(c_names),
        "status": "PASS" if a == 8 and len(b_names) == 16 and len(c_names) == 2 else "INCOMPLETE",
        "strict_scenarios": a_names + b_names + c_names,
    }
    out = ROOT / "audits" / "v20" / "V20_HF4_REQUIRED_26_PROGRESS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
