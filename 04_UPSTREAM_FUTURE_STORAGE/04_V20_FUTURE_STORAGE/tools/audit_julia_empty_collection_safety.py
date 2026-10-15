#!/usr/bin/env python3
"""Fail-fast static audit for empty-collection reductions in the V17 Julia model."""
from __future__ import annotations
from pathlib import Path
import json, re, sys
ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'base_model_v39'/'cheer_power_storage_v1.jl'
OUT=ROOT/'audits'; OUT.mkdir(exist_ok=True)

def extract_calls(text: str, name: str):
    calls=[]; token=name+'('; start=0
    while True:
        i=text.find(token,start)
        if i<0: break
        depth=0; j=i+len(name); in_str=False; esc=False
        while j<len(text):
            c=text[j]
            if in_str:
                if esc: esc=False
                elif c=='\\': esc=True
                elif c=='"': in_str=False
            else:
                if c=='"': in_str=True
                elif c=='(': depth+=1
                elif c==')':
                    depth-=1
                    if depth==0:
                        calls.append((i,j+1,text[i:j+1])); j+=1; break
            j+=1
        start=max(j,i+len(token))
    return calls

def line_no(text,pos): return text.count('\n',0,pos)+1

def main():
    text=MODEL.read_text(encoding='utf-8')
    checks=[]
    def add(name, ok, detail=''): checks.append({'check':name,'pass':bool(ok),'detail':detail})

    unsafe=[]
    for name in ('sum','maximum','minimum'):
        for i,j,call in extract_calls(text,name):
            # Generator reductions must supply an identity. A hard nonempty-set
            # check is allowed only for minimum(PERIODS), handled separately.
            if ' for ' in call and 'init=' not in call and 'maximum_or_default' not in text[max(0,i-30):i+5]:
                unsafe.append({'line':line_no(text,i),'reducer':name,'call':call[:300]})
    add('all_generator_reductions_define_identity',not unsafe,unsafe)
    add('no_direct_first_index_on_period_timepoints','TPS_IN_PERIOD[p][1]' not in text,'TPS_IN_PERIOD[p][1]')
    add('operational_period_partition_present','OPERATION_PERIODS = ' in text and 'STOCK_ANCHOR_PERIODS = ' in text,'period partition')
    add('stock_anchor_reserve_skipped','for p in OPERATION_PERIODS' in text and 'expected = isempty(TPS_IN_PERIOD[p]) ? 0' in text,'planning reserve logic')
    add('hours_reduction_is_empty_safe','sum(tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0)' in text,'hours_in_period')
    add('peak_load_reduction_is_empty_safe','sum(zone_demand_mw[(z, t)] for z in zones; init=0.0)' in text,'peak load')
    add('biomass_shadow_empty_guard','if nrow(df_biomass_shadow) == 0' in text,'empty biomass shadow table')
    add('empty_safety_token_exported','EMPTY_COLLECTION_SAFETY_VERSION' in text and ':empty_collection_safety_version' in text,'solve status metadata')

    summary={'version':'V17','checks':len(checks),'passed':sum(c['pass'] for c in checks),'all_pass':all(c['pass'] for c in checks)}
    payload={'summary':summary,'checks':checks}
    (OUT/'V17_EMPTY_COLLECTION_SAFETY_AUDIT.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if not summary['all_pass']:
        for c in checks:
            if not c['pass']: print(c,file=sys.stderr)
        raise SystemExit(1)
if __name__=='__main__': main()
