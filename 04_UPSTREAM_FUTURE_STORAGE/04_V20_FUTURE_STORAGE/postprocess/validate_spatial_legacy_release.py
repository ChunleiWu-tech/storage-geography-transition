#!/usr/bin/env python3
from pathlib import Path
import argparse,json,pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'postprocess_outputs'
MAIN=[f'Fig{i}' for i in range(1,7)]; SUPP=[f'FigS{i:02d}' for i in range(1,17)]
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--scenario-set',default='spatial_legacy_full'); args=ap.parse_args(); rows=[]
 for kind,ids,folder in [('main',MAIN,OUT/'figures/main'),('supplementary',SUPP,OUT/'figures/supplementary')]:
  for fid in ids:
   matches=list(folder.glob(fid+'*.pdf')); row={'figure_id':fid,'kind':kind,'pdf_count':len(matches),'pdf_exists':len(matches)==1}
   if matches:
    base=matches[0].with_suffix(''); row.update({'svg_exists':base.with_suffix('.svg').is_file(),'png_exists':base.with_suffix('.png').is_file(),'pdf_bytes':matches[0].stat().st_size})
   else: row.update({'svg_exists':False,'png_exists':False,'pdf_bytes':0})
   row['pass']=row['pdf_exists'] and row['svg_exists'] and row['png_exists'] and row['pdf_bytes']>1000; rows.append(row)
 a=pd.DataFrame(rows); (OUT/'audits').mkdir(parents=True,exist_ok=True); a.to_csv(OUT/'audits/figure_file_release_audit.csv',index=False); summary={'scenario_set':args.scenario_set,'main_figures':6,'supplementary_figures':16,'all_pass':bool(a['pass'].all()),'failed':a.loc[~a['pass'],'figure_id'].tolist()}; (OUT/'audits/postprocess_release_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2));
 if not summary['all_pass']: raise SystemExit(1)
if __name__=='__main__': main()
