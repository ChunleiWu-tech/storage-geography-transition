#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]; P=ROOT/'PACKAGE_MANIFEST_SHA256.json'
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
obj=json.loads(P.read_text(encoding='utf-8')); errors=[]
for rel,rec in obj['files'].items():
 p=ROOT/rel
 if not p.is_file(): errors.append('MISSING: '+rel); continue
 if p.stat().st_size!=int(rec['size']): errors.append('SIZE: '+rel); continue
 if sha(p)!=rec['sha256']: errors.append('SHA256: '+rel)
# Detect unexpected immutable files using the exact same exclusion policy.
exclude_names=set(obj.get('exclusions',{}).get('names',[])); exclude_parts=set(obj.get('exclusions',{}).get('parts',[]))
def included(p):
 r=p.relative_to(ROOT)
 if p.name in exclude_names or any(x in exclude_parts for x in r.parts): return False
 if 'outputs' in r.parts and r.parts[0]=='future_correction_cases': return False
 return True
actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and included(p)}
expected=set(obj['files'])
for rel in sorted(actual-expected): errors.append('UNMANIFESTED: '+rel)
for rel in sorted(expected-actual):
 if not any(e==('MISSING: '+rel) for e in errors): errors.append('MISSING_SET: '+rel)
print(json.dumps({'version':obj.get('version'),'checked_files':len(expected),'status':'PASS' if not errors else 'FAIL','errors':errors},ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
