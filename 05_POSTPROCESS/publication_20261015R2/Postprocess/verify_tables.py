from pathlib import Path
from manifest_paths import source_path
import hashlib,json,sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'SOURCE_TABLES_SHA256.json').read_text(encoding='utf-8'))
bad=[p for p,h in manifest.items() if not source_path(root,p).is_file() or hashlib.sha256(source_path(root,p).read_bytes()).hexdigest()!=h]
print(json.dumps({'table_count':len(manifest),'status':'FAIL' if bad else 'PASS','mismatches':bad},indent=2))
if bad: raise RuntimeError("Bundled source table hash mismatch")
