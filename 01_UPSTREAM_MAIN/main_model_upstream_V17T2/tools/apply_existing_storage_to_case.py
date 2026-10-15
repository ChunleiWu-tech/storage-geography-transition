#!/usr/bin/env python3
"""Apply the end-2025 NEA-constrained new-type-storage legacy to a model case.

The core input uses the reconstructed province/model-zone power allocation and the
exact national mean duration (351,120 MWh / 135,930 MW). Province-level magnitudes
that are not published by NEA are explicitly model-reconstructed and are never
labelled as an official 31-province inventory.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ALLOC=ROOT/'data/processed/existing_new_storage_allocated_to_model_zones_2025.csv'
FINGERPRINT=ROOT/'audits/PUBLICATION_SOURCE_FINGERPRINT.json'
EXPECTED_POWER_MW=135930.0
EXPECTED_ENERGY_MWH=351120.0
DATA_VERSION='NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2'

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def apply(case_dir, remove_existing=False, power_scale=1.0, energy_scale=1.0):
    case_dir=Path(case_dir); inp=case_dir/'inputs'
    gen=pd.read_csv(inp/'gen_info.csv')
    gb=pd.read_csv(inp/'gen_build_predetermined.csv')
    alloc=pd.read_csv(ALLOC)
    required={'model_zone','existing_new_storage_power_mw','existing_new_storage_energy_mwh','data_version'}
    missing=required-set(alloc.columns)
    if missing: raise ValueError(f'Storage allocation missing columns: {sorted(missing)}')
    if alloc.model_zone.nunique()!=32 or len(alloc)!=32: raise ValueError('Storage allocation must contain exactly 32 unique model zones')
    if set(alloc.data_version.astype(str))!={DATA_VERSION}: raise ValueError('Storage allocation data_version mismatch')
    p=float(alloc.existing_new_storage_power_mw.sum()); e=float(alloc.existing_new_storage_energy_mwh.sum())
    if abs(p-EXPECTED_POWER_MW)>1e-5 or abs(e-EXPECTED_ENERGY_MWH)>1e-4:
        raise ValueError(f'Storage national closure mismatch: {p} MW / {e} MWh')
    if FINGERPRINT.exists():
        fp=json.loads(FINGERPRINT.read_text(encoding='utf-8'))
        expected=fp.get('storage_stock',{}).get('zone_input_sha256')
        if expected and expected!=sha256(ALLOC): raise ValueError('Storage allocation hash differs from publication source fingerprint')
    battery_projects=set(gen.loc[gen.gen_tech.eq('Battery'),'GENERATION_PROJECT'])
    gb=gb[~(gb.GENERATION_PROJECT.isin(battery_projects) & pd.to_numeric(gb.build_year,errors='raise').eq(2023))].copy()
    added=[]
    if not remove_existing:
        zone_to_batt=dict(zip(gen.loc[gen.gen_tech.eq('Battery'),'gen_load_zone'], gen.loc[gen.gen_tech.eq('Battery'),'GENERATION_PROJECT']))
        for _,r in alloc.iterrows():
            proj=zone_to_batt.get(r.model_zone)
            if proj is None: raise RuntimeError(f'No Battery project for zone {r.model_zone}')
            added.append({'GENERATION_PROJECT':proj,'build_year':2023,
                          'build_gen_predetermined':float(r.existing_new_storage_power_mw)*float(power_scale),
                          'build_gen_energy_predetermined':float(r.existing_new_storage_energy_mwh)*float(energy_scale)})
        gb=pd.concat([gb,pd.DataFrame(added)],ignore_index=True)
    gb.to_csv(inp/'gen_build_predetermined.csv',index=False)
    audit={'case_dir':str(case_dir),'data_version':DATA_VERSION,'allocation_file':ALLOC.relative_to(ROOT).as_posix(),
           'allocation_sha256':sha256(ALLOC),'publication_source_fingerprint_sha256':sha256(FINGERPRINT) if FINGERPRINT.exists() else None,
           'existing_storage_removed':bool(remove_existing),'power_scale':float(power_scale),'energy_scale':float(energy_scale),
           'battery_power_added_mw':float(sum(a['build_gen_predetermined'] for a in added)),
           'battery_energy_added_mwh':float(sum(a['build_gen_energy_predetermined'] for a in added)),
           'rows_added':len(added),'input_scope':'NEA-constrained provincial power reconstruction; common national duration; pumped hydro excluded',
           'province_values_official_31_row_inventory':False}
    (case_dir/'audits').mkdir(exist_ok=True)
    (case_dir/'audits/existing_storage_application_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    return audit

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('case_dir'); ap.add_argument('--remove-existing',action='store_true'); ap.add_argument('--power-scale',type=float,default=1.0); ap.add_argument('--energy-scale',type=float,default=1.0)
    args=ap.parse_args(); apply(args.case_dir,args.remove_existing,args.power_scale,args.energy_scale)
if __name__=='__main__': main()
