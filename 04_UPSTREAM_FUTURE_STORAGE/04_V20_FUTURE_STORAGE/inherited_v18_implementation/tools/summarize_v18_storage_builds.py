#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, re
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def first_existing(d:Path,names:list[str])->Path:
    for n in names:
        p=d/n
        if p.exists(): return p
    raise FileNotFoundError(f'None of {names} found in {d}')

def family(tech:str)->str:
    t=str(tech)
    if 'LFP' in t:return 'LFP'
    if 'VRFB' in t:return 'VRFB'
    if 'CAES' in t:return 'CAES'
    if re.search(r'(^|_)H2_',t):return 'H2'
    if 'PSH' in t:return 'PSH'
    return 'other'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('output_dir'); ap.add_argument('--out',default='')
    a=ap.parse_args(); d=Path(a.output_dir)
    pg=first_existing(d,['BuildGen.csv','build_gen.csv'])
    pe=first_existing(d,['BuildStorageEnergy.csv','build_storage_energy.csv'])
    g=pd.read_csv(pg); e=pd.read_csv(pe)
    def norm(df):
        ren={}
        for c in df.columns:
            cl=c.lower()
            if cl in {'generation_project','project'}:ren[c]='project'
            elif cl in {'build_year','period','investment_period'}:ren[c]='build_year'
            elif cl in {'buildgen','build_mw','value','buildgen_mw'}:ren[c]='mw'
            elif cl in {'buildstorageenergy','build_mwh','buildstorageenergy_mwh'}:ren[c]='mwh'
        return df.rename(columns=ren)
    g=norm(g); e=norm(e)
    if 'project' not in g or 'project' not in e: raise SystemExit('Project column not recognized.')
    gm=g[g.project.astype(str).str.contains('-V18_',regex=False)].copy()
    em=e[e.project.astype(str).str.contains('-V18_',regex=False)].copy()
    keys=['project']+(['build_year'] if 'build_year' in gm.columns and 'build_year' in em.columns else [])
    keepg=keys+['mw']; keepe=keys+['mwh']
    x=gm[keepg].merge(em[keepe],on=keys,how='outer').fillna({'mw':0,'mwh':0})
    x['tech']=x.project.astype(str).str.extract(r'-(V18_[^-]+)$',expand=False)
    x['family']=x.tech.map(family)
    x['model_zone']=x.project.astype(str).str.split('-').str[0]
    x['duration_h_realized']=x['mwh']/x['mw'].where(x['mw'].abs()>1e-9)
    out=Path(a.out) if a.out else d/'V18_STORAGE_BUILD_MIX.csv'
    x.to_csv(out,index=False)
    group_cols=[c for c in ['model_zone','build_year','family','tech'] if c in x.columns]
    agg=x.groupby(group_cols,dropna=False)[['mw','mwh']].sum().reset_index()
    agg['duration_h_realized']=agg.mwh/agg.mw.where(agg.mw.abs()>1e-9)
    agg.to_csv(out.with_name('V18_STORAGE_BUILD_MIX_GROUPED.csv'),index=False)
    print(out)

if __name__=='__main__': main()
