#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, csv, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[1]
MAN=ROOT/'V20_PACKAGE_MANIFEST_SHA256.csv'
EXCLUDE={'V20_PACKAGE_MANIFEST_SHA256.csv','V20_PACKAGE_MANIFEST_SHA256.json'}

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--strict-set',action='store_true',help='Also fail on files not recorded in the clean release manifest.')
    a=ap.parse_args()
    if not MAN.is_file():
        raise SystemExit('V20 manifest missing: '+str(MAN))
    rows=list(csv.DictReader(MAN.open(encoding='utf-8-sig',newline='')))
    expected={r['relative_path']:r for r in rows}
    missing=[]; size_bad=[]; hash_bad=[]
    for rel,r in expected.items():
        p=ROOT/rel
        if not p.is_file(): missing.append(rel); continue
        if p.stat().st_size!=int(r['size_bytes']): size_bad.append(rel); continue
        if sha256(p)!=r['sha256']: hash_bad.append(rel)
    extras=[]
    if a.strict_set:
        actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p.relative_to(ROOT).as_posix() not in EXCLUDE}
        extras=sorted(actual-set(expected))
    ok=not missing and not size_bad and not hash_bad and not extras
    out={'version':'V20_MANIFEST_VERIFY_R1','status':'PASS' if ok else 'FAIL','checked_files':len(rows),'missing':missing,'size_mismatch':size_bad,'sha256_mismatch':hash_bad,'unexpected_files':extras}
    print(json.dumps(out,ensure_ascii=False,indent=2))
    raise SystemExit(0 if ok else 1)
if __name__=='__main__': main()
