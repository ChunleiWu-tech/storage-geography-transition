#!/usr/bin/env python3
"""Prepare Storage V19 dynamic-pathway scenario input folders from the sanitized storage base case.

V19 preserves the 16 spatial-legacy scenarios while adding the evidence-tiered future multi-technology, multi-duration storage pathway extension.
"""
from pathlib import Path
import shutil, pandas as pd, json, argparse, sys
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'base_model_v39'/'storage_base_noNBCCS_noDACCS_onshorePV'
OUTROOT=ROOT/'storage_cases'
SCEN=ROOT/'storage_runner'/'scenarios_storage_master.csv'

def ensure_base(reuse_base=False):
    sys.path.insert(0, str(ROOT/'tools'))
    if BASE.exists() and reuse_base:
        from publication_source_common import validate_base_fingerprint
        ok, reasons = validate_base_fingerprint(ROOT, BASE)
        if ok:
            return
        print("Existing base rejected by current source gate: " + "; ".join(reasons))
        shutil.rmtree(BASE)
    elif BASE.exists():
        shutil.rmtree(BASE)
    import build_storage_base_case
    build_storage_base_case.main()

def copy_case(name):
    dst=OUTROOT/name
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(BASE, dst)
    return dst

def _official_mask(df, scenario_set):
    official = df.get('v17_official_unique', False).astype(str).str.lower().isin(['true','1','yes'])
    if scenario_set == 'spatial_legacy_full':
        return official
    story = {'spatial_legacy_core':'spatial_legacy_core',
             'spatial_legacy_robustness':'spatial_legacy_robustness'}[scenario_set]
    return official & df.get('legacy_story_set','').astype(str).eq(story)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--official', action='store_true', help='Prepare the 16 frozen V17 spatial-legacy contexts with V18 future-storage extensions')
    ap.add_argument('--scenario-set', default='spatial_legacy_full', choices=['spatial_legacy_full','spatial_legacy_core','spatial_legacy_robustness'])
    ap.add_argument('--scenario')
    ap.add_argument('--reuse-base', action='store_true', help='Explicitly reuse an already source-gated expanded base')
    args=ap.parse_args()
    if not args.all and not args.official and not args.scenario:
        raise SystemExit('Use --official, --all, or --scenario SCENARIO')
    ensure_base(args.reuse_base); OUTROOT.mkdir(exist_ok=True)
    df=pd.read_csv(SCEN)
    if args.official:
        df=df[_official_mask(df, args.scenario_set)].copy()
    if args.scenario:
        df=df[df.scenario==args.scenario]
    rows=[]
    sys.path.insert(0, str(ROOT/'tools'))
    import apply_scenario_mutations
    from publication_source_contract import DATA_VERSION, load_fingerprint, source_fingerprint_sha256
    source_contract=load_fingerprint()
    source_contract_sha=source_fingerprint_sha256()
    for _,r in df.iterrows():
        dst=copy_case(str(r.scenario))
        mutations = apply_scenario_mutations.apply_mutations(dst, r.to_dict())
        from validate_prepared_storage_case import validate_case
        validation = validate_case(dst, r.to_dict(), raise_on_error=True)
        meta={k:(None if pd.isna(v) else v) for k,v in r.items()}
        meta['base_case_copied_from']=str(BASE)
        meta['publication_source_data_version']=DATA_VERSION
        meta['publication_source_fingerprint_sha256']=source_contract_sha
        meta['publication_source_contract']=source_contract
        meta['scope_lock']='V19 dynamic-pathway layer: NBCCS/DACCS disabled; offshore wind excluded; onshore wind + solar CF applied; generator CCS follows scenario flags; future storage uses discrete technology-duration candidates; linked-month SOC enabled by runner; CAES/H2 remain pressure-test-only without province resource ledgers; no multi-weather claim.'
        meta['v19_mutations_applied']=mutations
        meta['v19_prepared_case_validation']=validation
        (dst/'STORAGE_SCENARIO_META.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        from publication_source_common import write_case_fingerprint
        cfp=write_case_fingerprint(ROOT,dst,str(r.scenario),'main','STORAGE_SCENARIO_META.json')
        rows.append({'scenario':r.scenario,'case_dir':str(dst.relative_to(ROOT)).replace('\\','/'),'legacy_story_set':meta.get('legacy_story_set'),'v17_official_unique':meta.get('v17_official_unique'),'source_fingerprint_sha256':cfp['source_fingerprint_sha256'],'input_manifest_sha256':cfp['input_manifest_sha256']})
    pd.DataFrame(rows).to_csv(ROOT/'storage_runner'/'prepared_storage_cases_index.csv',index=False)
    print(f'Prepared {len(rows)} storage case directories under {OUTROOT}')
if __name__=='__main__': main()
