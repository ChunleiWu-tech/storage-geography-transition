from pathlib import Path
import json, hashlib
R=Path(__file__).resolve().parents[1]
data=json.loads((R/'metadata/SOURCE_FILES_SHA256.json').read_text(encoding='utf-8'))
errors=[]
for row in data['files']:
 p=R/row['path']
 if not p.is_file() or p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']: errors.append(row['path'])
frozen=json.loads((R/'05_POSTPROCESS/publication_20261015R2/Postprocess/SOURCE_TABLES_SHA256.json').read_text(encoding='utf-8'))
assert len(frozen)==74
for name,digest in frozen.items():
 p=R/'05_POSTPROCESS/publication_20261015R2/Postprocess'/name.replace(chr(92),'/')
 if hashlib.sha256(p.read_bytes()).hexdigest()!=digest: errors.append(name)
if errors: raise SystemExit('FAIL: '+str(errors))
print('PASS:',len(data['files']),'copied source files; 74 current frozen source tables')
