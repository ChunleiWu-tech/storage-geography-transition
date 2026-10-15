#!/usr/bin/env python3
"""Strict source-aware input validator for the publication storage study."""
from __future__ import annotations
from pathlib import Path
import hashlib, io, json, sys, zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
UP=ROOT
VERSION='NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2'
POWER=135930.0
ENERGY=351120.0
TOL_P=1e-5
TOL_E=1e-4
errors=[]
warnings=[]
checks=[]

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def add(name:str, ok:bool, detail=''):
    checks.append({'check':name,'passed':bool(ok),'detail':str(detail)})
    if not ok: errors.append(f'{name}: {detail}')

def warn(name:str, ok:bool, detail=''):
    if not ok: warnings.append(f'{name}: {detail}')

# Frozen raw snapshots and study-template lineage.
fp_path=ROOT/'audits/PUBLICATION_SOURCE_FINGERPRINT.json'
add('publication_source_fingerprint_exists',fp_path.is_file(),fp_path)
fp={}
if fp_path.is_file():
    fp=json.loads(fp_path.read_text(encoding='utf-8'))
    add('data_version',fp.get('data_version')==VERSION,fp.get('data_version'))
raw_switch=UP/'shared_source_snapshots/SWITCH_China_inputs_v2.0.9.zip'
raw_vre=UP/'shared_source_snapshots/hourly_vre_capacity_factor_2024_CHN_province_withSP.csv.gz'
template=ROOT/'base_model_v39/storage_base_template_v17.zip'
for name,p,expected in [
 ('switch_china_raw_snapshot',raw_switch,fp.get('switch_china',{}).get('raw_inputs_zip_sha256')),
 ('raw_vre_snapshot',raw_vre,fp.get('raw_vre_gzip_sha256')),
 ('study_template',template,fp.get('switch_china',{}).get('study_template_sha256')),
]:
    add(name+'_exists',p.is_file(),p)
    if p.is_file(): add(name+'_sha256',sha256(p)==expected,sha256(p))
lineage=UP/'SWITCH_CHINA_INPUT_LINEAGE_AUDIT.json'
add('switch_china_lineage_audit_exists',lineage.is_file(),lineage)
if lineage.is_file():
    lin=json.loads(lineage.read_text(encoding='utf-8'))
    add('switch_china_declared_version',lin.get('switch_china_snapshot',{}).get('declared_version')=='2.0.9',lin.get('switch_china_snapshot',{}).get('declared_version'))
    add('switch_china_no_false_byte_identity_claim','not a byte-identical copy' in lin.get('scientific_lineage_statement',''),lin.get('scientific_lineage_statement',''))

# Storage reconstruction.
province_path=ROOT/'data/processed/new_storage_existing_by_province_2025_nea_constrained_reconstruction.csv'
zone_path=ROOT/'data/processed/existing_new_storage_allocated_to_model_zones_2025.csv'
ledger_path=ROOT/'data/source_registry/provincial_storage_source_ledger_2025.csv'
regional_path=ROOT/'data/source_registry/nea_new_storage_national_regional_constraints_2025.csv'
prov_constraint_path=ROOT/'data/source_registry/nea_new_storage_provincial_constraints_2025.csv'
for name,p in [('province_reconstruction',province_path),('zone_storage_input',zone_path),('province_source_ledger',ledger_path),('regional_constraints',regional_path),('province_constraints',prov_constraint_path)]:
    add(name+'_exists',p.is_file(),p)
if province_path.is_file():
    d=pd.read_csv(province_path)
    req={'province_en','region','new_storage_power_mw_model','new_storage_energy_mwh_standardized','new_storage_energy_mwh_compiled_duration_sensitivity','evidence_class','inventory_interpretation','data_version'}
    add('province_required_columns',req.issubset(d.columns),sorted(req-set(d.columns)))
    add('province_count_31',len(d)==31 and d.province_en.nunique()==31,(len(d),d.province_en.nunique()))
    add('province_version_lock',set(d.data_version.astype(str))=={VERSION},set(d.data_version.astype(str)))
    add('province_power_closure',abs(float(d.new_storage_power_mw_model.sum())-POWER)<=TOL_P,float(d.new_storage_power_mw_model.sum()))
    add('province_standardized_energy_closure',abs(float(d.new_storage_energy_mwh_standardized.sum())-ENERGY)<=TOL_E,float(d.new_storage_energy_mwh_standardized.sum()))
    add('province_compiled_duration_sensitivity_energy_closure',abs(float(d.new_storage_energy_mwh_compiled_duration_sensitivity.sum())-ENERGY)<=TOL_E,float(d.new_storage_energy_mwh_compiled_duration_sensitivity.sum()))
    add('province_nonnegative',(d[['new_storage_power_mw_model','new_storage_energy_mwh_standardized','new_storage_energy_mwh_compiled_duration_sensitivity']]>=0).all().all(),'')
    add('province_interpretation_lock',d.inventory_interpretation.astype(str).str.contains('not an official exact 31-province inventory',case=False,regex=False).all(),'')
    if regional_path.is_file():
        rc=pd.read_csv(regional_path)
        targets=rc.loc[rc.metric.eq('power_mw') & ~rc.geography.eq('China')].set_index('geography').value.astype(float)
        got=d.groupby('region').new_storage_power_mw_model.sum()
        add('six_region_coverage',set(got.index)==set(targets.index),(sorted(got.index),sorted(targets.index)))
        for r,v in targets.items(): add(f'region_{r}_power_closure',abs(float(got.get(r,float('nan')))-v)<=TOL_P,float(got.get(r,float('nan'))))
    if prov_constraint_path.is_file():
        pc=pd.read_csv(prov_constraint_path)
        dm=d.set_index('province_en').new_storage_power_mw_model.astype(float)
        exact=pc.loc[pc.constraint_type.eq('official_exact_power_mw')]
        floors=pc.loc[pc.constraint_type.eq('official_reported_above_threshold_power_mw')]
        for r in exact.itertuples(): add(f'official_exact_{r.province_en}',abs(float(dm[r.province_en])-float(r.constraint_value_mw))<=TOL_P,float(dm[r.province_en]))
        for r in floors.itertuples(): add(f'official_threshold_{r.province_en}',float(dm[r.province_en])>=float(r.constraint_value_mw)-TOL_P,float(dm[r.province_en]))
if zone_path.is_file():
    z=pd.read_csv(zone_path)
    add('model_zone_count_32',len(z)==32 and z.model_zone.nunique()==32,(len(z),z.model_zone.nunique()))
    add('zone_version_lock',set(z.data_version.astype(str))=={VERSION},set(z.data_version.astype(str)))
    add('zone_power_closure',abs(float(z.existing_new_storage_power_mw.sum())-POWER)<=TOL_P,float(z.existing_new_storage_power_mw.sum()))
    add('zone_energy_closure',abs(float(z.existing_new_storage_energy_mwh.sum())-ENERGY)<=TOL_E,float(z.existing_new_storage_energy_mwh.sum()))
    expected=fp.get('storage_stock',{}).get('zone_input_sha256')
    add('zone_storage_hash_lock',sha256(zone_path)==expected,sha256(zone_path))
if ledger_path.is_file():
    led=pd.read_csv(ledger_path)
    add('source_ledger_31_rows',len(led)==31 and led.province_en.nunique()==31,(len(led),led.province_en.nunique()))
    add('source_ledger_language_lock',led.submission_language_lock.astype(str).str.contains('not an official exact 31-province inventory',case=False,regex=False).all(),'')
    add('source_ledger_hash_lock',sha256(ledger_path)==fp.get('storage_stock',{}).get('province_ledger_sha256'),sha256(ledger_path))

# VRE source and official calibration.
raw_cf=ROOT/'data/processed/vre_cf_hourly_by_province.csv'
cal=ROOT/'data/processed/vre_cf_hourly_by_province_publication_calibrated.csv'
bench=ROOT/'data/processed/vre_cf_national_benchmark_2024.csv'
vaudit=ROOT/'audits/vre_cf_publication_calibration_audit.json'
for name,p in [('raw_vre_processed',raw_cf),('calibrated_vre',cal),('wind_benchmark',bench),('wind_calibration_audit',vaudit)]: add(name+'_exists',p.is_file(),p)
if raw_cf.is_file():
    c=pd.read_csv(raw_cf)
    add('raw_vre_31x8760',len(c)==31*8760 and c.province_en.nunique()==31 and c.model_hour.nunique()==8760,(len(c),c.province_en.nunique(),c.model_hour.nunique()))
    for col in ['solar_cf','onshore_wind_cf','offshore_wind_cf']:
        add(f'raw_{col}_bounded',col in c.columns and c[col].between(0,1).all(),col)
    add('raw_offshore_scope_zero',c.offshore_wind_cf.eq(0).all(),'')
if cal.is_file():
    c=pd.read_csv(cal)
    add('calibrated_vre_31x8760',len(c)==31*8760 and c.province_en.nunique()==31 and c.model_hour.nunique()==8760,(len(c),c.province_en.nunique(),c.model_hour.nunique()))
    add('calibrated_vre_bounded',c[['solar_cf','onshore_wind_cf','offshore_wind_cf']].apply(lambda x:x.between(0,1).all()).all(),'')
    add('calibrated_profile_hash_lock',sha256(cal)==fp.get('wind_calibration',{}).get('calibrated_profile_sha256'),sha256(cal))
if bench.is_file():
    b=pd.read_csv(bench)
    add('wind_benchmark_one_row',len(b)==1,len(b))
    if len(b)==1:
        target=float(b.derived_gross_availability_cf.iloc[0]); actual=float(b.calibrated_model_capacity_weighted_cf.iloc[0])
        add('wind_target_closure',abs(target-actual)<=1e-10,(target,actual))
        add('wind_target_fingerprint',abs(target-float(fp.get('wind_calibration',{}).get('target_cf_8760',-1)))<=1e-12,target)
    add('wind_benchmark_hash_lock',sha256(bench)==fp.get('wind_calibration',{}).get('benchmark_sha256'),sha256(bench))
if vaudit.is_file():
    a=json.loads(vaudit.read_text(encoding='utf-8'))
    add('wind_audit_version',a.get('data_version')==VERSION,a.get('data_version'))
    add('wind_official_source_lock',a.get('official_source')=='National Energy Administration',a.get('official_source'))
    add('commercial_annual_report_excluded',a.get('commercial_annual_report_source_used') is False,a.get('commercial_annual_report_source_used'))
    add('wind_audit_hash_lock',sha256(vaudit)==fp.get('wind_calibration',{}).get('audit_sha256'),sha256(vaudit))

# Clean model scope and base/template integrity.
if template.is_file():
    try:
        with zipfile.ZipFile(template) as z:
            names=[x.replace('\\','/').lower() for x in z.namelist()]
            bf=pd.read_csv(io.BytesIO(z.read('inputs/beccs_lifecycle_factors.csv')))
        add('template_no_nbccs',not any(x.startswith('inputs/nbccs_') for x in names),'')
        add('template_no_daccs','inputs/dac_params.csv' not in names,'')
        factor=float(bf.beccs_net_removal_per_captured_tco2.iloc[0])
        add('template_beccs_physical_factor_one',abs(factor-1.0)<=1e-12,factor)
    except Exception as exc: add('template_scope_readable',False,exc)
base=ROOT/'base_model_v39/storage_base_noNBCCS_noDACCS_onshorePV/inputs'
if base.is_dir():
    gen=pd.read_csv(base/'gen_info.csv'); gb=pd.read_csv(base/'gen_build_predetermined.csv')
    batt=set(gen.loc[gen.gen_tech.eq('Battery'),'GENERATION_PROJECT'])
    b=gb.loc[gb.GENERATION_PROJECT.isin(batt)&pd.to_numeric(gb.build_year).eq(2023)]
    add('expanded_base_power',abs(float(b.build_gen_predetermined.sum())-POWER)<=TOL_P,float(b.build_gen_predetermined.sum()))
    add('expanded_base_energy',abs(float(b.build_gen_energy_predetermined.sum())-ENERGY)<=TOL_E,float(b.build_gen_energy_predetermined.sum()))
else:
    warnings.append('Expanded base is intentionally absent in the clean package and will be rebuilt before scenario preparation.')

# Scenario matrices.
master=ROOT/'storage_runner/scenarios_storage_master.csv'
if master.is_file():
    s=pd.read_csv(master)
    official=s.loc[s.v17_official_unique.astype(str).str.lower().isin(['true','1','yes'])]
    add('official_main_scenario_count_16',len(official)==16 and official.scenario.nunique()==16,(len(official),official.scenario.nunique()))
    add('cdr_disabled_all_official',official.nbccs_dac_genccs.astype(str).str.contains('nbccs_daccs_beccs_disabled',case=False,regex=False).all(),'')
report={'status':'PASS' if not errors else 'FAIL','data_version':VERSION,'checks':checks,'errors':errors,'warnings':warnings}
(ROOT/'audits').mkdir(exist_ok=True)
(ROOT/'audits/storage_input_validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
pd.DataFrame(checks).to_csv(ROOT/'audits/storage_input_validation_report.csv',index=False)
print(json.dumps({'status':report['status'],'checks':len(checks),'passed':sum(x['passed'] for x in checks),'errors':errors,'warnings':warnings},ensure_ascii=False,indent=2))
if errors: sys.exit(2)
