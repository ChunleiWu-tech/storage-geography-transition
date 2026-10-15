"""Print-space label clearance and source-backed key comparisons."""
import re,json
import numpy as np
from matplotlib.collections import PathCollection
def apply(fig,panels,key,output):
 targets={'Fig2':[4],'Fig5':[0,1,2],'FigS11':[0,1]}.get(key,[])
 fig.canvas.draw();records=[]
 for i in targets:
  ax=panels[i];points=[]
  for c in ax.collections:
   if isinstance(c,PathCollection):points.extend(np.asarray(c.get_offsets(),float).tolist())
  if not points:continue
  for t in list(ax.texts):
   s=t.get_text().strip()
   if not re.fullmatch(r'[+−–-]?\d+[.]\d+(?:\n\(\d+[.]\d+%\))?',s):continue
   xp,yp=t.get_position();same=[p for p in points if abs(p[1]-yp)<.2]
   if not same:continue
   p=min(same,key=lambda p:abs(p[0]-xp));xmin,xmax=ax.get_xlim();right=(p[0]-xmin)/(xmax-xmin)<.72
   if key=='Fig2':right=True
   t.remove();a=ax.annotate(s,xy=p,xytext=(8 if right else -8,0),textcoords='offset points',ha='left' if right else 'right',va='center',fontsize=7.2,zorder=16,bbox=dict(facecolor='white',edgecolor='none',pad=.6),annotation_clip=False)
   records.append((a,p,i))
 if key=='Fig2':
  ax=panels[4];ax.text(.98,1.085,'USD 6.28 billion difference\n24.50% loss of storage value',transform=ax.transAxes,ha='right',va='bottom',fontsize=7.2,fontweight='bold',linespacing=1.3)
 if key=='Fig7':
  ax=panels[1];lo,hi=ax.get_ylim();ticks=[v for v in ax.get_yticks() if lo<=v<=hi];ax.set_ylim(lo,hi+35);ax.set_yticks(ticks)
  ax.text(.02,.98,'99.87 GW build-timing difference\n+7.01 GW cumulative net',transform=ax.transAxes,ha='left',va='top',fontsize=7.2,linespacing=1.3,bbox=dict(facecolor='white',edgecolor='none',pad=1.5))
 fig.canvas.draw();renderer=fig.canvas.get_renderer();qa=[]
 for a,p,i in records:
  box=a.get_window_extent(renderer);center=a.axes.transData.transform(p);gap=(box.x0-center[0]) if a.get_ha()=='left' else (center[0]-box.x1)
  assert gap>=6*fig.dpi/72,(key,a.get_text(),gap)
  qa.append({'panel':i,'label':a.get_text(),'clearance_from_marker_center_pt':gap*72/fig.dpi,'required_center_clearance_pt':6})
 if qa:
  dest=output/'核查记录';dest.mkdir(exist_ok=True);(dest/(key+'_label_clearance.json')).write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
