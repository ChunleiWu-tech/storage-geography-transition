#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'PACKAGE_MANIFEST_SHA256.json'
EXCLUDE_NAMES={'PACKAGE_MANIFEST_SHA256.json','STATIC_PACKAGE_AUDIT_V18R1.json','V18R1_FUTURE_CORRECTION_IDENTIFICATION_AUDIT.json','PUBLICATION_SOURCE_GATE_SOURCE.json','PUBLICATION_SOURCE_GATE_CASES.json','PUBLICATION_SOURCE_GATE_RESULTS.json','PUBLICATION_RESULT_LINEAGE_V18R1.json'}
EXCLUDE_PARTS={'__pycache__','future_correction_outputs','future_correction_batch_logs','failed_diagnostics','.git','.venv','venv'}
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def included(p):
 r=p.relative_to(ROOT)
 if p.name in EXCLUDE_NAMES or any(x in EXCLUDE_PARTS for x in r.parts): return False
 if 'outputs' in r.parts and r.parts[0]=='future_correction_cases': return False
 return True
rows={}
for p in sorted(x for x in ROOT.rglob('*') if x.is_file() and included(x)):
 r=p.relative_to(ROOT).as_posix(); rows[r]={'size':p.stat().st_size,'sha256':sha(p)}
payload={'version':'V18R1_FUTURE_CORRECTION','immutable_file_count':len(rows),'exclusions':{'names':sorted(EXCLUDE_NAMES),'parts':sorted(EXCLUDE_PARTS)},'files':rows}
OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','manifest':OUT.name,'immutable_file_count':len(rows)},indent=2))
