#!/usr/bin/env python3
"""Ingest the supplied 2024 province-hour VRE profile with fail-closed quality checks."""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
DATA_VERSION="NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2"
EXPECTED_PROFILE_QUALITY="era5_2024_china_province_ispo_potential_weighted_withSP"
CN_FULL_TO_SHORT={'北京市':'北京','天津市':'天津','河北省':'河北','山西省':'山西','内蒙古自治区':'内蒙古','辽宁省':'辽宁','吉林省':'吉林','黑龙江省':'黑龙江','上海市':'上海','江苏省':'江苏','浙江省':'浙江','安徽省':'安徽','福建省':'福建','江西省':'江西','山东省':'山东','河南省':'河南','湖北省':'湖北','湖南省':'湖南','广东省':'广东','广西壮族自治区':'广西','海南省':'海南','重庆市':'重庆','四川省':'四川','贵州省':'贵州','云南省':'云南','西藏自治区':'西藏','陕西省':'陕西','甘肃省':'甘肃','青海省':'青海','宁夏回族自治区':'宁夏','新疆维吾尔自治区':'新疆'}
def sha256(path:Path)->str:
 h=hashlib.sha256();
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('input_csv_gz_or_csv'); ap.add_argument('--weather-year',type=int,default=2024); args=ap.parse_args()
 src=Path(args.input_csv_gz_or_csv).resolve(); df=pd.read_csv(src)
 mapping=pd.read_csv(ROOT/'data/processed/new_storage_existing_by_province_2025_nea_scope.csv')
 cn_to_en=dict(zip(mapping.province_cn,mapping.province_en))
 required={'province','technology','hour','capacity_factor','profile_quality'}
 if not required.issubset(df.columns): raise SystemExit('Expected long schema columns: '+', '.join(sorted(required)))
 if len(df)!=31*2*8760: raise SystemExit(f'Expected 543120 rows, got {len(df)}')
 if df['province'].nunique()!=31 or df['hour'].nunique()!=8760 or set(df['technology'])!={'onshore_wind','solar'}: raise SystemExit('Unexpected province/hour/technology coverage')
 q=sorted(df['profile_quality'].dropna().astype(str).unique())
 if q!=[EXPECTED_PROFILE_QUALITY]: raise SystemExit(f'Unexpected profile_quality values: {q}')
 if df[['province','technology','hour']].duplicated().any(): raise SystemExit('Duplicate province-technology-hour rows')
 if not pd.to_numeric(df.capacity_factor,errors='raise').between(0,1).all(): raise SystemExit('capacity_factor outside [0,1]')
 df['province_cn_full']=df['province']; df['province_cn']=df.province.map(CN_FULL_TO_SHORT); df['province_en']=df.province_cn.map(cn_to_en)
 if df.province_en.isna().any(): raise SystemExit('Unmapped provinces')
 df['model_hour']=pd.to_numeric(df.hour,errors='raise').astype(int)
 wide=df.pivot(index=['province_en','province_cn','model_hour'],columns='technology',values='capacity_factor').reset_index().rename(columns={'solar':'solar_cf','onshore_wind':'onshore_wind_cf'})
 wide.columns.name=None; wide['weather_year']=args.weather_year
 base=pd.Timestamp('2001-01-01'); wide['datetime']=wide.model_hour.map(lambda h:(base+pd.Timedelta(hours=int(h)-1)).strftime('%Y-%m-%d %H:%M:%S'))
 wide['offshore_wind_cf']=0.0; wide['temporal_scope']='8760_model_year_after_leap_day_filter'; wide['source_profile_quality']=EXPECTED_PROFILE_QUALITY; wide['data_version']=DATA_VERSION
 wide=wide[['province_en','province_cn','weather_year','model_hour','datetime','solar_cf','onshore_wind_cf','offshore_wind_cf','temporal_scope','source_profile_quality','data_version']].sort_values(['province_en','model_hour'])
 out=ROOT/'data/processed/vre_cf_hourly_by_province.csv'; wide.to_csv(out,index=False)
 summ=wide.groupby(['province_en','province_cn'],as_index=False).agg(solar_cf_mean=('solar_cf','mean'),solar_cf_min=('solar_cf','min'),solar_cf_max=('solar_cf','max'),onshore_wind_cf_mean=('onshore_wind_cf','mean'),onshore_wind_cf_min=('onshore_wind_cf','min'),onshore_wind_cf_max=('onshore_wind_cf','max'),hours=('model_hour','count'))
 summ['solar_full_load_hours']=summ.solar_cf_mean*8760; summ['onshore_wind_full_load_hours']=summ.onshore_wind_cf_mean*8760; summ['cf_scope']='supplied solar and onshore-wind hourly shape; offshore wind excluded'; summ['data_version']=DATA_VERSION; summ.to_csv(ROOT/'data/processed/vre_cf_validation_summary_2024.csv',index=False)
 audit={'status':'PASS','data_version':DATA_VERSION,'source_file':src.name,'source_file_sha256':sha256(src),'source_profile_quality':EXPECTED_PROFILE_QUALITY,'source_rows':int(len(df)),'processed_rows':int(len(wide)),'provinces':31,'hours':8760,'technologies':['solar','onshore_wind'],'exact_duplicate_keys':0,'null_capacity_factors':0,'offshore_wind_enabled':False,'cf_min':float(wide[['solar_cf','onshore_wind_cf']].min().min()),'cf_max':float(wide[['solar_cf','onshore_wind_cf']].max().max())}
 (ROOT/'audits').mkdir(exist_ok=True); (ROOT/'audits/vre_cf_ingest_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
