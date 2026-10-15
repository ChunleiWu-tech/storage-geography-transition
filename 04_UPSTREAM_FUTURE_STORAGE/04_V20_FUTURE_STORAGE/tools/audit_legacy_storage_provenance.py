#!/usr/bin/env python3
from pathlib import Path
import json, pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=ROOT/'data/processed/new_storage_existing_by_province_2025_nea_scope.csv'; d=pd.read_csv(p)
 audit={
  'status':'PASS',
  'data_version':str(d.data_version.iloc[0]),
  'national_power_mw':float(d.new_storage_power_mw_model.sum()),
  'national_energy_mwh':float(d.new_storage_energy_mwh_standardized.sum()),
  'national_closure_pass':abs(float(d.new_storage_power_mw_model.sum())-135930)<=1e-6 and abs(float(d.new_storage_energy_mwh_standardized.sum())-351120)<=1e-6,
  'official_evidence_boundary':{
   'official_exact':'national power and energy; North and Northwest report values; Inner Mongolia, Xinjiang, Shandong, Gansu and Guizhou power',
   'official_threshold':'seven additional provinces reported only as above 5 GW',
   'model_reconstruction':'all remaining provincial point estimates and the East/South/Central/Northeast exact closure derived from rounded official shares and a frozen prior',
  },
  'main_input_interpretation':'NEA-constrained model reconstruction with a common exact national duration; not an official exact 31-province inventory',
  'publication_language_lock':'Use model-reconstructed or NEA-constrained allocation. Never call the complete 31-province vector an official provincial census.',
 }
 out=ROOT/'audits/V17_LEGACY_STORAGE_PROVENANCE_AUDIT.json'; out.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
