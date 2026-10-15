#!/usr/bin/env python3
"""Map the frozen publication VRE profile to representative model timepoints."""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ZONE_TO_PROVINCE_FILE=ROOT/'data/processed/model_zone_to_province_mapping_v2.csv'
RAW_CF_FILE=ROOT/'data/processed/vre_cf_hourly_by_province.csv'
CF_FILE=ROOT/'data/processed/vre_cf_hourly_by_province_publication_calibrated.csv'
BENCHMARK=ROOT/'data/processed/vre_cf_national_benchmark_2024.csv'
FINGERPRINT=ROOT/'audits/PUBLICATION_SOURCE_FINGERPRINT.json'
VRE_CF_NUMERICAL_ZERO_THRESHOLD=1.0e-6
DATA_VERSION='NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2'

def sha256(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def model_hours(series: pd.Series)->pd.Series:
    parts=series.astype(str).str.extract(r'^(\d{4})\.(\d{2})\.(\d{2})\.(\d{2})$')
    if parts.isna().any(axis=None):
        bad=series[parts.isna().any(axis=1)].head().tolist(); raise ValueError(f'Cannot parse timepoint(s): {bad}')
    dt=pd.to_datetime({'year':2001,'month':parts[1].astype(int),'day':parts[2].astype(int),'hour':parts[3].astype(int)})
    return ((dt-pd.Timestamp('2001-01-01')).dt.total_seconds()//3600+1).astype(int)

def apply(case_dir: str|Path, cf_file: str|Path=CF_FILE)->dict[str,object]:
    case_dir=Path(case_dir); inp=case_dir/'inputs'; cf_file=Path(cf_file)
    if not cf_file.exists(): raise FileNotFoundError(f'Publication VRE CF file missing: {cf_file}. Run tools/build_publication_vre_cf.py first.')
    if FINGERPRINT.exists():
        fp=json.loads(FINGERPRINT.read_text(encoding='utf-8'))
        expected=fp.get('wind_calibration',{}).get('calibrated_profile_sha256')
        if expected and expected!=sha256(cf_file): raise ValueError('Calibrated VRE profile hash differs from publication source fingerprint')
    gen=pd.read_csv(inp/'gen_info.csv'); vcf=pd.read_csv(inp/'variable_capacity_factors.csv'); mapping=pd.read_csv(ZONE_TO_PROVINCE_FILE)
    cf=pd.read_csv(cf_file,usecols=['province_en','model_hour','solar_cf','onshore_wind_cf'])
    if cf.duplicated(['province_en','model_hour']).any(): raise ValueError('VRE profile has duplicate province-hour rows')
    meta=gen[['GENERATION_PROJECT','gen_tech','gen_load_zone']].drop_duplicates('GENERATION_PROJECT')
    work=vcf.merge(meta,on='GENERATION_PROJECT',how='left',validate='many_to_one')
    z2p=dict(zip(mapping.model_zone.astype(str),mapping.province_en.astype(str)))
    work['province_en']=work.gen_load_zone.astype(str).map(lambda z:z2p.get(z,z)); work['model_hour']=model_hours(work.timepoint)
    before=pd.to_numeric(work.gen_max_capacity_factor,errors='coerce').copy()
    work=work.merge(cf,on=['province_en','model_hour'],how='left',validate='many_to_one')
    solar=work.gen_tech.isin(['Solar_Distributed','Solar_Utility']); wind=work.gen_tech.eq('Wind_Onshore'); offshore=work.gen_tech.eq('Wind_Offshore')
    if work.loc[solar,'solar_cf'].isna().any() or work.loc[wind,'onshore_wind_cf'].isna().any():
        miss=work.loc[(solar&work.solar_cf.isna())|(wind&work.onshore_wind_cf.isna()),['GENERATION_PROJECT','timepoint','province_en']].head(); raise ValueError('Missing mapped VRE values:\n'+miss.to_string(index=False))
    work.loc[solar,'gen_max_capacity_factor']=work.loc[solar,'solar_cf'].to_numpy(); work.loc[wind,'gen_max_capacity_factor']=work.loc[wind,'onshore_wind_cf'].to_numpy(); work.loc[offshore,'gen_max_capacity_factor']=0.0
    work['gen_max_capacity_factor']=pd.to_numeric(work.gen_max_capacity_factor,errors='raise')
    if not work.gen_max_capacity_factor.between(0,1).all(): raise ValueError('Mapped capacity factors fall outside [0,1]')
    tiny=work.gen_max_capacity_factor.between(0,VRE_CF_NUMERICAL_ZERO_THRESHOLD,inclusive='neither'); tiny_rows=int(tiny.sum()); tiny_sum=float(work.loc[tiny,'gen_max_capacity_factor'].sum()); work.loc[tiny,'gen_max_capacity_factor']=0.0
    out=work[['GENERATION_PROJECT','timepoint','gen_max_capacity_factor']]; out.to_csv(inp/'variable_capacity_factors.csv',index=False)
    benchmark=pd.read_csv(BENCHMARK).iloc[0].to_dict()
    audit={'case_dir':str(case_dir),'data_version':DATA_VERSION,'rows':len(out),'changed_rows':int((np.abs(before.to_numpy()-work.gen_max_capacity_factor.to_numpy())>1e-12).sum()),
           'offshore_cf_rows_zeroed':int(offshore.sum()),'numerical_cf_zero_threshold':VRE_CF_NUMERICAL_ZERO_THRESHOLD,'tiny_positive_cf_rows_zeroed':tiny_rows,'tiny_positive_cf_sum_before_zeroing':tiny_sum,
           'minimum_nonzero_cf_after_zeroing':float(out.loc[out.gen_max_capacity_factor>0,'gen_max_capacity_factor'].min()),'source_profile_hours_per_province':8760,
           'optimization_representative_timepoints':int(work.timepoint.nunique()),'scope':'NEA-calibrated national onshore-wind proxy plus supplied solar; offshore wind zeroed',
           'cf_file':str(cf_file),'cf_file_sha256':sha256(cf_file),'benchmark_file_sha256':sha256(BENCHMARK),'publication_source_fingerprint_sha256':sha256(FINGERPRINT) if FINGERPRINT.exists() else None,
           'wind_target_cf_8760':benchmark.get('derived_gross_availability_cf'),'raw_cf_file_retained_for_sensitivity':str(RAW_CF_FILE)}
    (case_dir/'audits').mkdir(exist_ok=True); (case_dir/'audits/vre_cf_application_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2)); return audit

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('case_dir'); ap.add_argument('--cf-file',default=str(CF_FILE)); args=ap.parse_args(); apply(args.case_dir,args.cf_file)
if __name__=='__main__': main()
