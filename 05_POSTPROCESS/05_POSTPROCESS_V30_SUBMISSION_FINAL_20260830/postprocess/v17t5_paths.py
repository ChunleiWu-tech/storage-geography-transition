"""Shared paths for the integrated V30 publication postprocessor.

The legacy names are intentionally retained because the frozen Fig. 1--5 and
Fig. S1--S12 builders import them.  The two additional roots are read-only
evidence sources for V20 and FULL8760.
"""
from __future__ import annotations

import os
from pathlib import Path

SOURCE_ROOT = Path(os.environ.get("V17_POSTPROCESS_SOURCE_ROOT", Path(__file__).resolve().parents[1])).resolve()
PROJECT_ROOT = Path(os.environ.get("V17_PROJECT_ROOT", SOURCE_ROOT)).resolve()
TARGETYEAR_ROOT = Path(os.environ.get("V17_TARGETYEAR_SENSITIVITY_ROOT", SOURCE_ROOT)).resolve()
FULL8760_ROOT = Path(os.environ.get("V30_FULL8760_ROOT", SOURCE_ROOT)).resolve()
V20_ROOT = Path(os.environ.get("V30_FUTURE_STORAGE_ROOT", SOURCE_ROOT)).resolve()
OUTPUT_ROOT = Path(os.environ.get("V17_POSTPROCESS_OUTPUT_ROOT", SOURCE_ROOT / "postprocess_outputs")).resolve()

MASTER = PROJECT_ROOT / "storage_runner" / "scenarios_storage_master.csv"
TEMPLATE = PROJECT_ROOT / "base_model_v39" / "storage_base_template_v17.zip"
TARGETYEAR_REGISTRY = TARGETYEAR_ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
TARGETYEAR_OUTPUTS = TARGETYEAR_ROOT / "sensitivity_outputs"

TABLE_MAIN = OUTPUT_ROOT / "tables" / "main"
TABLE_SUPP = OUTPUT_ROOT / "tables" / "supplementary"
TABLE_TARGETYEAR = OUTPUT_ROOT / "tables" / "targetyear_sensitivity"
TABLE_FULL8760 = OUTPUT_ROOT / "tables" / "full8760_validation"
TABLE_V20 = OUTPUT_ROOT / "tables" / "future_storage"
FIG_MAIN = OUTPUT_ROOT / "figures" / "main"
FIG_SUPP = OUTPUT_ROOT / "figures" / "supplementary"
AUDIT_DIR = OUTPUT_ROOT / "audits"
TEXT_DIR = OUTPUT_ROOT / "manuscript_ready_text"

MAP_ASSET_CANDIDATES = [
    SOURCE_ROOT / "postprocess_assets" / "map_assets",
    PROJECT_ROOT / "postprocess_assets" / "map_assets",
    PROJECT_ROOT / "map_assets",
]
