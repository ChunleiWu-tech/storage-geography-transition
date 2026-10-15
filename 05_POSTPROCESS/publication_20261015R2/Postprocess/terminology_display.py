"""Consistent publication scenario names; numerical artists are unchanged."""
import re
from matplotlib import text as mt
def rename(s,key):
    s=s.replace('US$','USD').replace(r'US\$','USD')
    s=s.replace('half absolute sum','half-sum')
    s=s.replace('Pumped hydro','PSH').replace('pumped hydro','PSH')
    s=s.replace('Peak demand (GW)','Coincident peak (GW)').replace('Storage / peak','Storage / coincident peak')
    s=s.replace('0.40 × peak','0.40 × coincident peak')
    s=s.replace('storage-to-peak','storage-to-coincident-peak-demand')
    short={
      'Baseline':'Core options','Adaptive':'VRFB +\nlong PSH',
      'Adaptive\nfixed transmission':'VRFB + long PSH\nfixed transmission',
      'Expanded*':'Broader options*'}
    if key=='Fig6':
      s=short.get(s,s)
    if key=='FigS14':
      s=s.replace('2033 adaptive','2033 VRFB/PSH').replace('2033 base','2033 core').replace('2033 expanded*','2033 broader*')
      s=s.replace('Baseline,','Base planning,')
    s=re.sub(r'\bExisting\b','Retained',s);s=re.sub(r'\bexisting\b','retained',s)
    s=re.sub(r'\bReference\b','Optimized',s);s=re.sub(r'\breference\b','optimized',s)
    if key in ['Fig5','FigS11'] and s=='Base':s='Base planning'
    if key=='Fig7' and s=='Baseline':s='Base planning'
    return s
def apply(fig,panels,key):
    for ax in fig.axes:
      for axis in ['x','y']:
        ticks=getattr(ax,'get_'+axis+'ticks')();labels=getattr(ax,'get_'+axis+'ticklabels')()
        old=[t.get_text() for t in labels];new=[rename(s,key) for s in old]
        if len(ticks)==len(new) and new!=old:
          lim=getattr(ax,'get_'+axis+'lim')();getattr(ax,'set_'+axis+'ticks')(ticks,new);getattr(ax,'set_'+axis+'lim')(lim)
    for t in fig.findobj(match=mt.Text):t.set_text(rename(t.get_text(),key))
