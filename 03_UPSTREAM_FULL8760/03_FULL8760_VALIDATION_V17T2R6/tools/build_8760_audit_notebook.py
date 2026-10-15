#!/usr/bin/env python3
"""Create and execute the compact V17T2R6 data-quality audit notebook."""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks" / "V17T2R6_FULL8760_DATA_QUALITY_AUDIT.ipynb"


def main() -> None:
    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3 (ipykernel)",
        "language": "python",
        "name": "python3",
    }
    nb["metadata"]["language_info"] = {"name": "python", "version": "3.11"}
    nb["cells"] = [
        nbf.v4.new_markdown_cell(
            "# V17T2R6 full-8760 data-quality audit\n\n"
            "This notebook independently checks the frozen raw-data hashes, the 31-province non-leap load table, "
            "the four prepared cases, annual-energy closure, VRE bounds/time-zone declaration, and within-pair identity. "
            "It audits inputs only; no solver result is inferred."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import hashlib, json\n"
            "import pandas as pd\n"
            "ROOT = Path.cwd().parent.resolve()\n"
            "assert (ROOT / 'VERSION_V17T2R6_FULL8760.txt').is_file(), ROOT\n"
            "def sha256(path):\n"
            "    h = hashlib.sha256()\n"
            "    with Path(path).open('rb') as fh:\n"
            "        for block in iter(lambda: fh.read(1024*1024), b''):\n"
            "            h.update(block)\n"
            "    return h.hexdigest()\n"
            "ROOT"
        ),
        nbf.v4.new_code_cell(
            "raw = ROOT / 'data/raw/load/figshare_29832701_Data_output.xlsx'\n"
            "processed = ROOT / 'data/processed/figshare_load_2024_31province_8760_nonleap.csv'\n"
            "load = pd.read_csv(processed)\n"
            "load_cols = [c for c in load if c.endswith('_load_gw')]\n"
            "basic = {\n"
            " 'raw_figshare_sha256': sha256(raw) == 'a93ff6d4a2f4f8c36538fdc4704e2e88bef16347d217c456a99a7a97d56a19e0',\n"
            " 'processed_load_sha256': sha256(processed) == '74944cc8d707561ac1b6e3210cfa7035eaa5d0e84a391d42c012de17304291ab',\n"
            " 'hours_8760': len(load) == 8760 and load.model_hour.tolist() == list(range(1,8761)),\n"
            " 'province_columns_31': len(load_cols) == 31,\n"
            " 'all_load_values_positive': load[load_cols].stack().gt(0).all(),\n"
            "}\n"
            "pd.DataFrame({'check': basic.keys(), 'pass': basic.values()})"
        ),
        nbf.v4.new_code_cell(
            "scenarios = pd.read_csv(ROOT / 'storage_runner/scenarios_targetyear_linked.csv')\n"
            "rows = []\n"
            "for scenario in scenarios.scenario:\n"
            "    case = ROOT / 'sensitivity_cases' / scenario\n"
            "    prepared = json.loads((case / 'audits/FULL8760_PREPARED_INPUT_VALIDATION.json').read_text(encoding='utf-8'))\n"
            "    temporal = json.loads((case / 'audits/FULL8760_TEMPORAL_INPUT_AUDIT.json').read_text(encoding='utf-8'))\n"
            "    residual = max(abs(float(x['annual_energy_residual_mwh'])) for x in temporal['loads'])\n"
            "    rows.append({\n"
            "      'scenario': scenario, 'prepared_status': prepared['status'],\n"
            "      'timepoints': pd.read_csv(case / 'inputs/timepoints.csv').shape[0],\n"
            "      'max_zone_annual_energy_residual_mwh': residual,\n"
            "      'vre_shift_hours': temporal['vre']['utc_to_cst_circular_shift_hours'],\n"
            "      'vcf_min': temporal['vre']['minimum_cf'], 'vcf_max': temporal['vre']['maximum_cf'],\n"
            "    })\n"
            "case_audit = pd.DataFrame(rows)\n"
            "case_audit"
        ),
        nbf.v4.new_code_cell(
            "pair = json.loads((ROOT / 'audits/V17T2R6_FULL8760_PAIR_IDENTITY_AUDIT.json').read_text(encoding='utf-8'))\n"
            "gate = json.loads((ROOT / 'audits/PUBLICATION_SOURCE_GATE_CASES.json').read_text(encoding='utf-8'))\n"
            "final_checks = {\n"
            "  **basic,\n"
            "  'four_scenarios': len(scenarios) == 4,\n"
            "  'all_prepared_pass': case_audit.prepared_status.eq('PASS').all(),\n"
            "  'all_cases_8760': case_audit.timepoints.eq(8760).all(),\n"
            "  'annual_energy_closure_0p05_mwh': case_audit.max_zone_annual_energy_residual_mwh.le(0.05).all(),\n"
            "  'vre_cst_shift_plus_8': case_audit.vre_shift_hours.eq(8).all(),\n"
            "  'vre_bounded_0_1': case_audit.vcf_min.ge(0).all() and case_audit.vcf_max.le(1).all(),\n"
            "  'pair_identity_pass': pair['status'] == 'PASS',\n"
            "  'source_case_gate_pass': gate['status'] == 'PASS' and gate['checks_passed'] == gate['checks_total'],\n"
            "}\n"
            "summary = pd.DataFrame({'check': final_checks.keys(), 'pass': final_checks.values()})\n"
            "assert summary['pass'].all(), summary.loc[~summary['pass']]\n"
            "summary"
        ),
        nbf.v4.new_markdown_cell(
            "## Interpretation\n\n"
            "All input-level gates pass. The notebook does not assert that the four LPs have been solved. "
            "Publication claims must wait for solver-native OPTIMAL status, physical audits, result fingerprints, "
            "and the paired full-8760 summary."
        ),
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(OUT.parent)}})
    executed = client.execute()
    nbf.write(executed, OUT)
    print(f"PASS: executed notebook written to {OUT}")


if __name__ == "__main__":
    main()
