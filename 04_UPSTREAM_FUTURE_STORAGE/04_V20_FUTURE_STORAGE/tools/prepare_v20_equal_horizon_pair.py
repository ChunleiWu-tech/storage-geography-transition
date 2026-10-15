#!/usr/bin/env python3
"""Prepare the mandatory V20 equal-evidence-horizon core pair.

Purpose
-------
V19's evidence-direct primary pathway gives the 4 h LFP candidate the source-direct
NLR/NREL 2025 trajectory through 2060, while the multi-technology PNNL v2024
benchmark only supports BAU cost projections through 2030 for the non-LFP
headline technologies.  V20 does *not* invent post-2030 learning curves for
VRFB or PSH. Instead it adds a matched two-case sensitivity in which the LFP
candidate is also frozen at its source-direct 2030 benchmark after 2030.

Only V18_LFP_4h build-cost rows at build_year >= 2033 are changed relative to
the corresponding evidence-direct source cases. All other scientific inputs
are byte-identical. This sensitivity is mandatory for long-horizon technology-
competition claims but does not replace the evidence-direct primary pathway.
"""
from __future__ import annotations
from pathlib import Path
import hashlib, json, shutil, sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCEN = ROOT / "storage_runner" / "scenarios_storage_master.csv"
OUT_INDEX = ROOT / "storage_runner" / "v20_equal_horizon_cases_index.csv"
NLR = ROOT / "data" / "processed" / "nlr_2025_battery_4h_costs.csv"

CPI_U_2010 = 218.056
CPI_U_2024 = 313.689
DEFLATOR_2024_TO_2010 = CPI_U_2010 / CPI_U_2024
DURATION_H = 4.0
FOM_SHARE = 0.04
ANCHOR_YEAR = 2030
PAIR = [
    ("V20EH01_OBSERVED", "SL01_OBSERVED_STANDARDIZED"),
    ("V20EH02_OPTIMAL", "SL02_OPTIMAL_REALLOCATION"),
]


def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def input_hashes(case: Path) -> dict[str,str]:
    return {p.relative_to(case/'inputs').as_posix():sha256(p) for p in sorted((case/'inputs').rglob('*')) if p.is_file()}


def main() -> None:
    if not NLR.is_file(): raise SystemExit(f"Missing authoritative NLR table: {NLR}")
    src_table=pd.read_csv(NLR)
    q=src_table.loc[pd.to_numeric(src_table.year,errors='raise').astype(int).eq(ANCHOR_YEAR)]
    if len(q)!=1: raise SystemExit('Expected exactly one NLR 2030 anchor row')
    source_2030=float(q.iloc[0]['mid_2024usd_per_kwh'])
    if abs(source_2030-279.0)>1e-12:
        raise SystemExit(f"Unexpected NLR 2030 mid anchor {source_2030}; expected official Appendix Table 2 transcription 279")
    hold_cost=source_2030*DEFLATOR_2024_TO_2010*DURATION_H*1000.0
    hold_fom=hold_cost*FOM_SHARE

    master=pd.read_csv(SCEN)
    master=master.loc[~master.scenario.astype(str).isin([x[0] for x in PAIR])].copy()
    new_rows=[]; index=[]
    for new_name, source_name in PAIR:
        src_rows=master.loc[master.scenario.astype(str).eq(source_name)]
        if len(src_rows)!=1: raise SystemExit(f"Expected one source scenario row for {source_name}")
        r=src_rows.iloc[0].copy()
        r['scenario']=new_name
        if 'v17_official_unique' in r.index: r['v17_official_unique']=False
        if 'legacy_story_set' in r.index: r['legacy_story_set']='v20_equal_evidence_horizon'
        if 'notes' in r.index:
            r['notes']=f"V20 mandatory equal-evidence-horizon sensitivity cloned from {source_name}; only future V18_LFP_4h CAPEX/FOM held at NLR 2030 benchmark after 2030."
        new_rows.append(r)

        src=ROOT/'storage_cases'/source_name; dst=ROOT/'storage_cases'/new_name
        if not src.is_dir(): raise SystemExit(f"Missing prepared source case {src}; run V20 preparation first")
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(src,dst)
        before=input_hashes(src)
        costp=dst/'inputs/gen_build_costs.csv'
        costs=pd.read_csv(costp)
        years=pd.to_numeric(costs['build_year'],errors='raise').astype(int)
        lfp=costs['GENERATION_PROJECT'].astype(str).str.endswith('-V18_LFP_4h')
        changed=lfp & years.ge(2033)
        if int(lfp.sum())!=32*7 or int(changed.sum())!=32*6:
            raise SystemExit(f"Unexpected LFP cost row geometry in {new_name}: total={int(lfp.sum())}, changed={int(changed.sum())}")
        costs.loc[changed,'gen_overnight_cost']=hold_cost
        costs.loc[changed,'gen_storage_energy_overnight_cost']=0.0
        costs.loc[changed,'gen_fixed_om']=hold_fom
        costs.to_csv(costp,index=False)
        after=input_hashes(dst)
        non_cost_drift=[k for k,v in before.items() if k!='gen_build_costs.csv' and after.get(k)!=v]
        if non_cost_drift: raise SystemExit(f"Non-cost scientific input drift in {new_name}: {non_cost_drift[:10]}")

        # Update case metadata to avoid machine-path / source-scenario ambiguity.
        meta_p=dst/'STORAGE_SCENARIO_META.json'
        meta=json.loads(meta_p.read_text(encoding='utf-8')) if meta_p.exists() else {}
        meta['scenario']=new_name
        meta['v17_official_unique']=False
        meta['legacy_story_set']='v20_equal_evidence_horizon'
        meta['base_case_copied_from']='base_model_v39/storage_base_noNBCCS_noDACCS_onshorePV'
        meta['v20_equal_horizon_source_scenario']=source_name
        meta['v20_cost_regime']='equal_evidence_horizon_2030_hold'
        meta['v20_intervention_scope']='Only V18_LFP_4h future build CAPEX/FOM rows at build_year>=2033 are held at the source-direct NLR 2030 mid benchmark; non-LFP headline technologies were already held at their PNNL 2030 benchmark.'
        meta_p.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

        aud={
          'status':'PASS','version':'V20_EQUAL_EVIDENCE_HORIZON_2030_HOLD_R1',
          'scenario':new_name,'source_scenario':source_name,
          'purpose':'Mandatory robustness test for asymmetric evidence horizon in long-run technology competition.',
          'authoritative_lfp_source':'Cole, Ramasamy and Turan (2025), NREL/TP-6A40-93281, Appendix Table 2',
          'doi':'10.2172/2583471','source_anchor_year':2030,
          'source_anchor_mid_2024usd_per_kwh':source_2030,
          'cpi_u_2010':CPI_U_2010,'cpi_u_2024':CPI_U_2024,'deflator_2024_to_2010':DEFLATOR_2024_TO_2010,
          'model_hold_cost_2010usd_per_mw':hold_cost,'model_hold_fom_2010usd_per_mw_year':hold_fom,
          'changed_rows':int(changed.sum()),'changed_build_years':sorted(years.loc[changed].unique().tolist()),
          'non_cost_input_drift':non_cost_drift,'post2030_lfp_extrapolation_used':False,
          'invented_vrfb_or_psh_learning_curve_used':False,
          'doe_si2030_lcos_used_as_capex_scalar':False,
          'claim_scope':'Sensitivity only. Technology-winner claims after 2030 are headline-eligible only if qualitatively robust to this equal-horizon pair.'
        }
        (dst/'audits/V20_EQUAL_HORIZON_COST_AUDIT.json').write_text(json.dumps(aud,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        pd.DataFrame([{
          'scenario':new_name,'source_scenario':source_name,'technology':'V18_LFP_4h',
          'anchor_year':2030,'anchor_2024usd_per_kwh':source_2030,
          'hold_model_2010usd_per_mw':hold_cost,'hold_fom_2010usd_per_mw_year':hold_fom,
          'changed_rows':int(changed.sum()),'changed_years':';'.join(map(str,sorted(years.loc[changed].unique())))
        }]).to_csv(dst/'audits/V20_EQUAL_HORIZON_COST_AUDIT.csv',index=False)
        index.append({'scenario':new_name,'source_scenario':source_name,'case_dir':f'storage_cases/{new_name}','cost_regime':'equal_evidence_horizon_2030_hold','status':'PASS'})

    master=pd.concat([master,pd.DataFrame(new_rows)],ignore_index=True)
    master.to_csv(SCEN,index=False)

    # Regenerate case fingerprints now that the registry contains the V20 rows.
    sys.path.insert(0,str(ROOT/'tools'))
    try:
        from publication_source_common import write_case_fingerprint
        # The case fingerprint records the SHA256 of the *entire* scenario registry.
        # Rewriting the master registry to append the two V20 rows therefore changes
        # that SHA for every main-model case, not just the new pair. Regenerate the
        # 16 official fingerprints plus the two V20 equal-horizon fingerprints so
        # PREP_V20 remains resume-safe and the source gate cannot become stale.
        active = master.loc[master.get('v17_official_unique', False).astype(str).str.lower().isin(['true','1']) if 'v17_official_unique' in master.columns else pd.Series(False,index=master.index), 'scenario'].astype(str).tolist()
        active += [x[0] for x in PAIR]
        for scenario in active:
            case_dir=ROOT/'storage_cases'/scenario
            if not case_dir.is_dir():
                raise FileNotFoundError(f'Missing prepared case while restamping registry fingerprint: {case_dir}')
            write_case_fingerprint(ROOT,case_dir,scenario,'main','STORAGE_SCENARIO_META.json')
    except Exception as exc:
        raise SystemExit(f"Failed to regenerate V20 equal-horizon case fingerprints: {exc}")
    pd.DataFrame(index).to_csv(OUT_INDEX,index=False)
    print(json.dumps({'status':'PASS','cases':[x[0] for x in PAIR],'lfp_2030_mid_2024usd_per_kwh':source_2030,'model_hold_cost_2010usd_per_mw':hold_cost},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
