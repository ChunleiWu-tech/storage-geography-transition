#!/usr/bin/env python3
"""Audit the evidence boundary of the end-2025 inherited-storage reconstruction."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
AUD=ROOT/'audits'; AUD.mkdir(exist_ok=True)
VERSION='NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2'
p=ROOT/'data/processed/new_storage_existing_by_province_2025_nea_constrained_reconstruction.csv'
ledger=ROOT/'data/source_registry/provincial_storage_source_ledger_2025.csv'
constraints=ROOT/'data/source_registry/nea_new_storage_provincial_constraints_2025.csv'
d=pd.read_csv(p); l=pd.read_csv(ledger); c=pd.read_csv(constraints)
exact=c.loc[c.constraint_type.eq('official_exact_power_mw'),'province_en'].astype(str).tolist()
threshold=c.loc[c.constraint_type.eq('official_reported_above_threshold_power_mw'),'province_en'].astype(str).tolist()
out={
 'status':'PASS',
 'data_version':VERSION,
 'scientific_object':'end-2025 commissioned new-type-storage power geography used as a model input',
 'national_power_mw':float(d.new_storage_power_mw_model.sum()),
 'national_energy_mwh':float(d.new_storage_energy_mwh_standardized.sum()),
 'national_totals_evidence':'official exact values from China New Energy Storage Development Report 2026',
 'official_exact_province_power_values':exact,
 'official_reported_above_5gw_set':threshold,
 'remaining_province_values':'official-constrained model reconstruction using a frozen, explicitly unverified within-region shape prior',
 'primary_energy_assignment':'common national duration 351120/135930 h, so the primary comparison isolates power geography',
 'separate_duration_sensitivity':'prior duration pattern rescaled to exact national energy; not represented as official province energy',
 'forbidden_claim':'The 31 reconstructed province values are an official province-by-province inventory.',
 'language_gate_pass':bool(l.submission_language_lock.astype(str).str.contains('not an official exact 31-province inventory',case=False,regex=False).all()),
 'province_count':int(d.province_en.nunique()),
 'model_reconstruction_count':int((~d.evidence_class.eq('official_exact_power')).sum()),
 'results_status':'RERUN_REQUIRED_16_PLUS_8'
}
if not out['language_gate_pass'] or out['province_count']!=31: out['status']='FAIL'
(AUD/'V17_LEGACY_STORAGE_PROVENANCE_AUDIT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
l[['province_en','province_cn','region','new_storage_power_mw_model','official_exact_power_mw','official_reported_threshold_power_mw','evidence_class','official_source_status','submission_language_lock']].to_csv(AUD/'V17_LEGACY_STORAGE_PROVENANCE_LEDGER.csv',index=False)
print(json.dumps(out,ensure_ascii=False,indent=2))
if out['status']!='PASS': raise SystemExit(2)
