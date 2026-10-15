#!/usr/bin/env python3
from pathlib import Path
import json
from publication_source_common import write_source_fingerprint
ROOT=Path(__file__).resolve().parents[1]
fp=write_source_fingerprint(ROOT)
print(json.dumps(fp,ensure_ascii=False,indent=2))
