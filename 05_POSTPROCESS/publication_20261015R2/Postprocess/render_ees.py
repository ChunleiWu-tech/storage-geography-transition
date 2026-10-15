from pathlib import Path
import os,sys,json,re,textwrap,ast
OUT=Path(__file__).resolve().parents[1]
BASE=OUT.parent
# Use the active Python environment; the recorded versions are in requirements.txt.
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
os.environ['MPLCONFIGDIR']=str(OUT/'Postprocess/.mplcache')
os.environ['V17_POSTPROCESS_SOURCE_ROOT']=str(OUT/'Postprocess')
os.environ['V17_POSTPROCESS_OUTPUT_ROOT']=str(OUT/'Postprocess')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.text as mt
import matplotlib.patheffects as pe
from matplotlib.ticker import MaxNLocator, FuncFormatter
import numpy as np
import pandas as pd
import ne_style
UPDATES=json.loads((OUT/'Postprocess/text_updates.json').read_text(encoding='utf-8'))
COMMON=json.loads((OUT/'Postprocess/common_updates.json').read_text(encoding='utf-8'))

def update_text(text,updates):
    # Keep reviewed figure vocabulary when regenerating from the archived tables.
    s=COMMON.get(text,updates.get(text,text))
    for old,new in [('Reconstructed standardized','Existing layout'),('Optimized reallocation','Reference layout'),
                    ('reconstructed/optimized','existing/reference'),('Reconstructed − optimized','Existing − reference'),
                    ('reconstructed minus optimized','existing-layout minus reference-layout'),
                    ('Optimized − observed','Reference − existing'),('Observed − optimized','Existing − reference'),
                    ('Observed standardized','Existing layout'),('Total discounted cost penalty','Total discounted cost difference'),
                    ('Half-sum of absolute regional power differences (GW)','Regional power difference\n(half absolute sum, GW)'),
                    ('Wind-and-solar curtailment','VRE curtailment'),('Long-duration storage power','LDES power'),('Long-duration storage energy','LDES energy'),
                    ('2033 + long-duration\nstorage, 4 h','2033\n+ LDES, 4 h'),('long-duration','LDES')]:
        s=s.replace(old,new)
    return s

def save(fig,base,dpi=600):
    name=base.stem
    selected = os.environ.get('EES_FIGURE_KEYS', '')
    if selected and name.split('_')[0] not in selected.split(','):
        plt.close(fig)
        return
    updates=UPDATES.get(name,{})
    heights={'Fig1':6.6,'Fig2':6.2,'Fig3':6.5,'Fig4':7.4,'Fig5':6.1,'Fig6':7.5,'Fig7':8.5,
             'FigS01':3.0,'FigS02':3.7,'FigS03':6.0,'FigS04':6.0,'FigS05':6.3,'FigS06':6.8,
             'FigS07':4.0,'FigS08':5.1,'FigS09':4.7,'FigS10':4.5,'FigS11':6.6,'FigS12':7.8,'FigS13':7.7}
    key=name.split('_')[0]
    panels=[ax for ax in fig.axes if not hasattr(ax,'_colorbar') and ax.get_position().height>.09]
    if key!='FigS14': fig.set_size_inches(171/25.4,heights[key],forward=True)
    for ax in panels:
        xlim,ylim=ax.get_xlim(),ax.get_ylim()
        for axis in ['x','y']:
            ts=getattr(ax,'get_'+axis+'ticks')(); labs=getattr(ax,'get_'+axis+'ticklabels')()
            strings=[update_text(t.get_text(),updates) for t in labs]
            if len(ts)==len(strings) and any(s for s in strings):getattr(ax,'set_'+axis+'ticks')(ts,strings)
        ax.set_xlim(xlim);ax.set_ylim(ylim)
    for t in fig.findobj(match=mt.Text):
        if not t.get_text():continue
        t.set_text(update_text(t.get_text(),updates))
        t.set_fontfamily('Arial')
        t.set_fontsize(max(t.get_fontsize(),7.2))
        # Make panel letters stay inside the figure, independent of axes height.
        if t.get_text() in list('abcde') and t.axes and t.get_transform()==t.axes.transAxes:
            t.set_position((-0.10,1.045));t.set_fontsize(9)
    # Numerical callouts keep fixed print-space separation from the zero line.
    if key in ['Fig5','FigS11']:
        for ax in fig.axes:
            for t in ax.texts:
                if re.fullmatch(r'[+−–-]?\d+(?:\.\d+)?',t.get_text().strip()):
                    t.set_bbox(dict(facecolor='white',edgecolor='none',pad=1.2))
                    t.set_zorder(15)
    if key=='FigS08':
        for ax in panels:
            b=ax.get_position();ax.set_position([b.x0,b.y0*.92,b.width,b.height*.88])
    if key in ['Fig5','FigS11']:
        short={'Pumped-storage constraint':'PSH limit','Pumped-storage cap':'PSH limit','Tighter carbon cap':'Tighter carbon','Transmission fixed':'Fixed network','Fixed transmission':'Fixed network','Low battery cost':'Low cost','High battery cost':'High cost'}
        for ax in panels:
            ts=ax.get_yticks();labs=[short.get(t.get_text(),t.get_text()) for t in ax.get_yticklabels()]
            if len(ts)==len(labs):ax.set_yticks(ts,labs)
            for t in ax.texts:
                t.set_text(short.get(t.get_text(),t.get_text()))
    if key=='FigS11':
        for ax,pos in zip(panels,[[.23,.61,.29,.30],[.66,.61,.29,.30],[.23,.15,.72,.29]]):ax.set_position(pos)
        panels[2].set_title('Transmission and curtailment',loc='left')
        panels[2].set_xlim(-5,8)
        for t in list(fig.findobj(match=mt.Text)):
            if 'Marker area' in t.get_text():t.set_text('')
    if key=='FigS04':
        ax=panels[0];b=ax.get_position();ax.set_position([.30,.16,.68,.76])
        labels=[update_text(t.get_text(),updates).replace('Conservative pumped storage','PSH limit').replace('Fixed transmission','Fixed network').replace('Tighter carbon cap','Tighter carbon').replace('Low battery cost','Low cost').replace('High battery cost','High cost').replace('reconstructed','existing').replace('optimized','reference').replace('Reconstructed duration','Variable duration') for t in ax.get_yticklabels()]
        ax.set_yticks(ax.get_yticks(),labels)
        # Geography and duration are separate dimensions. Wrap cell labels at
        # unchanged type size so that every glyph remains inside its cell.
        for t in ax.texts:
            x,y=t.get_position()
            if x==.5 and y==.5:t.set_text('Existing\nlayout')
            elif x==.5:
                t.set_text({'Existing layout':'Existing\nlayout','Renewables rule':'VRE rule'}.get(t.get_text(),t.get_text()))
    if key=='FigS06':
        for ax,pos in zip(panels,[[.16,.13,.34,.77],[.64,.13,.34,.77]]):ax.set_position(pos)
    if key=='FigS09':
        panels[0].set_position([.255,.15,.31,.72]);panels[1].set_position([.70,.15,.28,.72])
        labs=[t.get_text().replace('W. Inner Mong.','WIM').replace('E. Inner Mong.','EIM').replace('Inner Mong.','IM').replace('West Inner Mong.','WIM') for t in panels[0].get_yticklabels()]
        panels[0].set_yticks(panels[0].get_yticks(),labs)
        panels[1].set_xticks([2023,2033,2043,2053],['2023','2033','2043','2053'])
        panels[0].set_xlim(-3.6,3.1)
    if key=='Fig4':
        a,b,m1,m2,d=panels
        a.set_position([.11,.66,.31,.25]);b.set_position([.59,.66,.37,.25])
        # Dedicated map/colorbar bands separate geography from the classification diagram.
        m1.set_position([.07,.345,.34,.205]);m2.set_position([.07,.065,.34,.205])
        bars=[ax for ax in fig.axes if hasattr(ax,'_colorbar')]
        for old,mp,y,label in zip(bars,[m1,m2],[.318,.038],['Initial power difference (GW)','2058 power difference (GW)']):
            artist=old._colorbar.mappable;old.remove()
            cx=fig.add_axes([.095,y,.285,.009]);cb=fig.colorbar(artist,cax=cx,orientation='horizontal')
            cb.set_label(label,fontsize=7.2,labelpad=2);cb.ax.tick_params(labelsize=7.2,pad=1)
        for t in list(fig.texts):
            if 'Δ (GW)' in t.get_text():t.remove()
        d.set_position([.50,.085,.48,.47]);d.clear();d.set_axis_off()
        from matplotlib.path import Path as PlotPath
        from matplotlib.patches import PathPatch,Rectangle
        q=pd.read_csv(OUT/'Postprocess/tables/main/fig4c_zone_correction.csv')
        q['positive']=q.optimized_minus_observed_power_mw>0
        classes=['persistent or amplified','partly corrected','substantially corrected','reversal']
        cols=[ne_style.PALETTE[x] for x in ['red','orange','teal','purple']]
        grouped=q.groupby(['positive','correction_class']).initial_absolute_power_mw.sum()
        den=grouped.sum();gap=.035
        sp={};tp={};cur=.08
        for sg in [True,False]:
            h=grouped.loc[sg].sum()/den*.73;sp[sg]=[cur,cur+h];cur+=h+gap
        cur=.08
        for cl in classes:
            h=grouped.xs(cl,level=1).sum()/den*.73;tp[cl]=[cur,cur+h];cur+=h+gap
        sc={x:y[0] for x,y in sp.items()};tc={x:y[0] for x,y in tp.items()}
        for sg in [True,False]:
            for cl,col in zip(classes,cols):
                h=grouped.get((sg,cl),0)/den*.73
                if not h:continue
                u,v=sc[sg],tc[cl];sc[sg]+=h;tc[cl]+=h
                vs=[(.27,u),(.40,u),(.65,v),(.83,v),(.83,v+h),(.65,v+h),(.40,u+h),(.27,u+h),(.27,u)]
                cs=[1,4,4,4,2,4,4,4,79]
                d.add_patch(PathPatch(PlotPath(vs,cs),facecolor=col,edgecolor='none',alpha=.48))
        for sg,(lo,hi) in sp.items():
            d.add_patch(Rectangle((.23,lo),.04,hi-lo,facecolor=ne_style.PALETTE['blue']))
            d.text(.20,(lo+hi)/2,'Positive' if sg else 'Negative',ha='right',va='center',fontsize=7.2)
        labs=['Persistent /\namplified (1)','Partly\ncorrected (8)','Substantially\ncorrected (11)','Sign reversal (12)']
        for cl,col,lab in zip(classes,cols,labs):
            lo,hi=tp[cl];d.add_patch(Rectangle((.83,lo),.04,hi-lo,facecolor=col))
            d.text(.91,(lo+hi)/2,lab,ha='left',va='center',fontsize=7.2,linespacing=1.3)
        d.set_xlim(0,1.55);d.set_ylim(0,1.05)
        d.text(.02,1.045,'d',transform=d.transAxes,fontweight='bold',fontsize=9)
        d.text(.13,1.02,'Initial sign',ha='center',fontsize=7.2,fontweight='bold')
        d.text(1.04,1.02,'2058 class',ha='center',fontsize=7.2,fontweight='bold')
        fig.text(.51,.029,'Width: absolute initial regional difference.\nRemaining magnitude ≤10% of the initial difference\n(≥90% reduction) is classified before sign reversal.\nSee Methods for the ordered tests.',fontsize=7.2,linespacing=1.25)
        for t in m2.texts:
            if isinstance(t,mt.Annotation) and t.get_text()=='Anhui':t.set_position((.98,.45))
        for t in b.texts:
            if isinstance(t,mt.Annotation) and t.get_text()=='Guangdong':t.set_position((-45,15));t.set_ha('left')
            if isinstance(t,mt.Annotation) and t.get_text()=='Shandong':t.set_position((-45,-13));t.set_ha('left')
        a.set_xticks(a.get_xticks(),[t.get_text().replace('Stock\nanchor','Initial\nstock') for t in a.get_xticklabels()],rotation=35,ha='right')
    if key=='Fig3':
        for ax in panels[1:3]:
            for t in ax.texts:
                if t.get_text()=='+4.08':t.set_ha('right')
        for t in list(panels[2].texts):
            if isinstance(t,mt.Annotation) and t.get_text()=='+11.81':
                # The point is 2028; use a print-space offset into clear space.
                assert int(t.xy[0])==2028
                point=t.xy;t.remove()
                panels[2].annotate('+11.81',xy=point,xytext=(12,-14),textcoords='offset points',
                    ha='left',va='top',fontsize=7.2,zorder=15,
                    bbox=dict(facecolor='white',edgecolor='none',pad=1.2),
                    arrowprops=dict(arrowstyle='-',color='#555',lw=.55,shrinkA=2,shrinkB=4))
    if key=='FigS02':
        for ax in list(fig.axes):
            if hasattr(ax,'_colorbar'):ax.remove()
        for coll in panels[0].collections:coll.set_array(None);coll.set_facecolor(ne_style.PALETTE['teal'])
    if key=='FigS03':
        ax=panels[0];b=ax.get_position();ax.set_position([b.x0,b.y0+.04,b.width,b.height-.04])
        cx=fig.add_axes([b.x0,b.y0-.045,b.width,.011])
        cb=fig.colorbar(ax.collections[0],cax=cx,orientation='horizontal')
        cb.set_label('Storage power / coincident peak',fontsize=7.2)
    if key=='FigS10':
        panels[1].set_xlim(.3,32.7)
    if key=='Fig1':
        for t in list(panels[0].texts):
            if 'National stock:' in t.get_text():t.remove()
        fig.text(.055,.535,'National stock: 135.93 GW / 351.12 GWh',fontsize=7.2,fontweight='bold')
        ax=panels[3];ax.clear();ax.set_axis_off()
        ax.text(0,1.045,'d',transform=ax.transAxes,fontweight='bold',fontsize=9)
        ax.text(.02,.94,'Matched inherited stock',fontweight='bold',fontsize=8)
        ax.text(.02,.85,'135.93 GW / 351.12 GWh',fontsize=7.2)
        for y,label,detail,col in [(.65,'Duration sensitivity','Existing sites; variable duration','#73787C'),(.42,'Existing layout','Existing sites; common duration','#3F7AA6'),(.19,'Reference layout','Optimized sites; common duration','#D98A3A')]:
            ax.text(.02,y,label,color=col,fontweight='bold',fontsize=8)
            ax.text(.02,y-.10,detail,fontsize=7.2)
        ax.text(.02,.01,'Other benchmarks: no stock; load / VRE rules',fontsize=7.2)
        for t in panels[2].texts:
            if t.get_text()=='0.06':t.set_text('0.0631')
        for t in list(fig.texts):
            if t.get_text()=='d':t.remove()
    if key=='Fig2':
        # Leave an explicit gutter for panel e's categorical axis.
        axs=panels
        axs[3].set_position([.14,.14,.44,.36]);axs[4].set_position([.80,.14,.18,.36])
        axs[4].set_xlim(-1,41)
        for t in axs[4].get_yticklabels():
            t.set_text({'Optimized':'Reference','Standardized':'Existing'}.get(t.get_text(),t.get_text()))
        axs[4].set_yticks(axs[4].get_yticks(),[{'Optimized':'Reference','Renewables rule':'VRE rule','Standardized':'Existing','No legacy':'No stock'}.get(t.get_text(),t.get_text()) for t in axs[4].get_yticklabels()])
        axs[4].set_xlabel('System value\n(billion USD, PV)',fontsize=7.2)
        for ax in axs[:3]:
            for t in ax.texts:
                if len(t.get_text())>9 and 'Inner' in t.get_text():t.set_text('W. Inner M.')
        for t in axs[1].texts:
            if isinstance(t,mt.Annotation) and t.get_text()=='Zhejiang':
                # Keep the full label and its leader above the maritime inset.
                t.set_position((.98,.41))
    if key=='Fig6':
        for ax in panels[:2]:
            for t in ax.texts:
                if 'Symbol area shows' in t.get_text():t.set_text('Area = absolute change')
        panels[2].set_title('Matched 2033 portfolios',loc='left',pad=25)
        leg=panels[2].get_legend()
        if leg:leg.set_bbox_to_anchor((.5,1.04))
        panels[3].set_xlabel('Regional power difference\n(half absolute sum, GW)',fontsize=7.2)
        for t in list(panels[3].texts):
            if 'Expanded*' in t.get_text():t.remove()
        fig.text(.15,.012,'Expanded*: resource-unconstrained technology sensitivity.',fontsize=7.2)
    if key=='Fig7':
        for t in panels[2].texts:
            if isinstance(t,mt.Annotation) and t.get_text()=='Shanghai':t.set_position((.98,.43))
        ax=panels[3]
        ax.set_position([.70,.345,.27,.215])
        ax.set_xlim(-12,23)
        ax.set_title('Net additions and cost',loc='left',fontsize=8,y=1.10,pad=6)
        for t in ax.texts:
            s=t.get_text()
            if 'billion' in s:
                t.set_text(s.split(' billion')[0]);t.set_position((27,t.get_position()[1]));t.set_ha('right');t.set_color('#555')
        ax.set_xlim(-12,47)
        ax.set_xticks([-10,0,10])
        for t in ax.texts:
            st=t.get_text().strip()
            if re.fullmatch(r'[+−–-]\d+(?:\.\d+)?',st):
                t.set_position((21,t.get_position()[1]));t.set_ha('left')
                t.set_bbox(dict(facecolor='white',edgecolor='none',pad=.4))
            elif re.fullmatch(r'\d+\.\d+',st):
                t.set_position((46,t.get_position()[1]));t.set_ha('right')
        ax.text(21,-.75,'GW',ha='left',fontsize=7.2)
        ax.text(46,-.75,'USD bn',ha='right',fontsize=7.2)
        for t in ax.texts:
            if t.get_text()=='d':t.set_position((-.10,1.12))
        panels[4].set_position([.15,.13,.81,.15])
        for t in list(panels[4].texts):
            if t.get_position()[1]<0:t.remove()
        fig.text(.15,.034,'Ideal additions for fixed 2033 portfolios under common hourly conditions.\nTheir implementation costs are outside the planning-cost comparison.',fontsize=7.2,linespacing=1.4)

        ax.set_xlabel('Build difference (GW)',fontsize=7.2)
        labels=[{'Reference':'Baseline','Pumped-storage cap':'PSH limit','Tighter carbon cap':'Tighter carbon','Transmission fixed':'Fixed network','Low battery cost':'Low cost','High battery cost':'High cost'}.get(t.get_text(),t.get_text()) for t in ax.get_yticklabels()]
        ax.set_yticks(ax.get_yticks(),labels)
        for t in list(panels[4].texts):
            if 'All four have' in t.get_text() or 'Zero would' in t.get_text():t.remove()
        panels[4].set_xticks(panels[4].get_xticks(),['Existing','Reference','Existing\n+ LDES','Reference\n+ LDES'])
        for leg in fig.legends:
            leg.set_ncols(3);leg.set_bbox_to_anchor((.5,.99))
    # Captions, rather than microtext, carry methodological notes.
    if key in ['FigS12','FigS13']:
        for t in list(fig.texts):t.remove()
        if key=='FigS12':
            fig.subplots_adjust(left=.18,right=.97,bottom=.16,top=.89,hspace=.60,wspace=.68)
            for ax,pos in zip(panels,[[.16,.62,.32,.28],[.66,.62,.30,.28],[.16,.24,.32,.25],[.66,.24,.30,.25]]):ax.set_position(pos)
            for ax in fig.axes[:2]:
                ax.set_yticks(range(4),['2028\nlinked SOC','2033\nlinked SOC','2033 linked SOC\n+ LDES','2033 linked SOC\n1 h'])
            fig.axes[0].set_xlabel('Annual cost difference\n(million USD yr$^{-1}$)')
            for ax in fig.axes[2:4]:
                ax.set_xticks(range(4),['2028\n4 h','2033\n4 h','2033\nLDES, 4 h','2033\n1 h'])
            ax=fig.axes[1];ax.set_xlim(-4200,8800)
            ax.set_xlabel('Cost components\n(million USD yr$^{-1}$)')
            for t in ax.texts:
                if t.get_text().startswith('Net '):
                    t.set_text(t.get_text().replace('Net ',''));t.set_position((8600,t.get_position()[1]));t.set_ha('right')
            for leg in fig.legends:
                leg.set_ncols(3);leg.set_bbox_to_anchor((.5,.995))
            leg=ax.get_legend()
            if leg:
                handles,labels=ax.get_legend_handles_labels();leg.remove()
                fig.legend(handles,labels,ncol=3,loc='upper center',bbox_to_anchor=(.52,.995),fontsize=7.2)
            for t in list(fig.axes[0].texts):
                if 'response ratio:' in t.get_text():t.remove()
            fig.text(.05,.04,'Color is scaled within each row.\nAbsolute emission differences below 0.005 Mt CO$_2$ yr$^{-1}$ are shown in neutral color.',fontsize=7.2)
        else:
            for ax,pos in zip(panels,[[.16,.60,.32,.28],[.68,.60,.29,.28],[.16,.20,.32,.28],[.68,.20,.29,.28]]):ax.set_position(pos)
            short=['Existing','Reference','Existing + LDES','Reference + LDES']
            for ax in [panels[0],panels[1],panels[3]]:ax.set_yticks(range(4),short)
            panels[0].set_xlim(0,133)
            panels[0].set_title('Ideal balancing capacity',loc='left')
            panels[1].set_title('Supply and absorption',loc='left')
            panels[2].set_title('Regional balancing (GW)',loc='left')
            for cb in fig.axes:
                if hasattr(cb,'_colorbar'):
                    cb.set_axes_locator(None);cb.set_position([.505,.225,.012,.22])
            panels[2].set_xticks(range(4),short,rotation=35,ha='right')
            panels[3].set_title('Numerical evidence',loc='left')
            panels[3].set_xticks(range(5),['Optimal','Primal / dual','Inputs','Physical checks','Overall'],rotation=35,ha='right')
            for t in panels[3].texts:t.set_text({'Satisfied':'Pass','Unavailable':'N/A','Not satisfied':'Fail'}.get(t.get_text(),t.get_text()))
            fig.text(.14,.025,'Fixed portfolios; added ideal capacity is a diagnostic, not an actual investment.\nGray cells: optional numerical checks not available.',fontsize=7.2)
    if key == 'Fig1':
        from layout_fig1_20260914 import apply as apply_fig1
        apply_fig1(fig, panels, OUT)
    if key == 'Fig4':
        from layout_fig4_20260914 import apply as apply_fig4
        apply_fig4(fig, panels, OUT)
    from layout_caption_cleanup_20260914 import apply as apply_caption_layout
    apply_caption_layout(fig, panels, key)
    from layout_quantitative_si import apply as apply_quantitative_si
    apply_quantitative_si(fig, panels, key, OUT)
    for ax in fig.axes:
        if hasattr(ax,'_colorbar') and key!='FigS14':
            bar=ax._colorbar
            bar.locator=MaxNLocator(nbins=3)
            bar.formatter=FuncFormatter(lambda x,pos:f'{x:g}')
            bar.update_ticks()
            ax.tick_params(labelsize=7.2)
    folder=OUT/'Figures'/('supplementary' if key.startswith('FigS') else 'main')
    folder.mkdir(parents=True,exist_ok=True)
    # Recompute map-only text sizes/positions after all final layout changes.
    from layout_map_labels import apply as apply_map_labels
    apply_map_labels(fig, key, OUT)
    from terminology_display import apply as apply_terms
    apply_terms(fig, panels, key)
    from layout_final_science import apply as apply_final_science
    apply_final_science(fig, panels, key, OUT)
    fig.canvas.draw()
    # Preview at readable size; save full-resolution PNG and embedded-font PDF.
    for ext in ['png','pdf','svg']:
        fig.savefig(folder/(name+'.'+ext),dpi=600 if ext=='png' else 150,facecolor='white')
    # Final deliverables are saved above; no preview cache is published.
    plt.close(fig)
    print('SAVED',key,flush=True)

ne_style.save_figure=save
origconfigure=ne_style.configure
def configure():
    origconfigure()
    matplotlib.rcParams.update({'font.family':'Arial','font.size':7.2,'axes.labelsize':7.2,'axes.titlesize':8,
      'xtick.labelsize':7.2,'ytick.labelsize':7.2,'legend.fontsize':7.2,'pdf.fonttype':42,'svg.fonttype':'none'})
ne_style.configure=configure

import runpy
runpy.run_path(str(OUT/'Postprocess/verify_tables.py'),run_name='source_check')
group=sys.argv[1] if len(sys.argv)>1 else 'all'
sys.argv=sys.argv[:1]
if group in ['spatial','all']:
    import plot_spatial_legacy_figures as p
    p.main()
if group in ['target','all']:
    import plot_targetyear_sensitivity_figure as p
    # Display tolerance is tied to the published 0.01-unit precision, not a claim of exact zero.
    original=p.row_normalized_matrix
    def matrix(ax,frame,metric_order,title_units=True):
        image=original(ax,frame,metric_order,title_units)
        values=frame.pivot(index='metric',columns='pair_id',values='observed_minus_optimized').reindex(index=metric_order,columns=p.PAIR_ORDER).to_numpy(float)
        scaled=np.asarray(image.get_array()).copy()
        for i,metric in enumerate(metric_order):
            if metric=='Net emissions':
                scaled[i,np.abs(values[i])<.005]=0
                for j in range(values.shape[1]):
                    t=ax.texts[i*values.shape[1]+j]
                    if abs(values[i,j])<.005:t.set_color(ne_style.PALETTE['dark'])
        image.set_data(scaled)
        return image
    p.row_normalized_matrix=matrix
    p.main()
if group in ['full','all']:
    import plot_full8760_validation as p
    p.main()
if group in ['future','all']:
    import plot_v20_publication_figures as p
    configure()
    p.plot_fig6(p.read(p.TABLE_V31,'fig6_layer_a_pair_metrics.csv'),p.read(p.TABLE_V31,'fig6_adaptive_zone_portfolios.csv'))
    p.plot_fig7(p.read(p.TABLE_V31,'fig7_core_timing_by_technology.csv'),p.read(p.TABLE_V31,'fig7_core_zone_difference.csv'),p.read(p.TABLE_V31,'fig7_context_pair_metrics.csv'),p.read(p.TABLE_FULL8760,'full8760_certificate_summary.csv'))
    metrics=p.read(p.TABLE_V31,'figS14_all26_case_metrics.csv').sort_values('scenario_order')
    tech=p.read(p.TABLE_V31,'figS14_all26_technology_shares.csv')
    timing=p.read(p.TABLE_V31,'figS14_timing_display.csv')
    order=metrics.scenario.tolist(); yy=np.arange(26)
    fig=plt.figure(figsize=(171/25.4,8.0))
    # One shared 26-row alignment avoids duplicating a dense row axis.
    axes=[fig.add_axes(b) for b in [[.30,.22,.115,.64],[.445,.22,.08,.64],[.565,.22,.18,.64],[.78,.22,.205,.64]]]
    colors=metrics.layer.map(p.LAYER_COLORS).tolist()
    axes[0].barh(yy,metrics.power_gw,color=colors,height=.7)
    axes[0].set_xscale('log');axes[0].set_xticks([100,1000],['100','1,000'])
    labels=[f'{i+1:02d} '+s.replace('observed','existing').replace('optimized','reference').replace('transmission fixed','fixed network').replace('Pumped-storage constraint','PSH limit').replace('pumped-storage constraint','PSH limit').replace('Actual inherited stock','Reconstructed duration').replace('Reference,','Baseline,') for i,s in enumerate(metrics.scenario_label)]
    axes[0].set_yticks(yy,labels)
    axes[0].set_xlabel('Power (GW)\nlog scale');axes[0].set_title('a  New power',loc='left',pad=12)
    axes[1].scatter(metrics.duration_h,yy,c=colors,s=15)
    axes[1].set_xlim(3.5,10.5);axes[1].set_xticks([4,7,10]);axes[1].set_yticks([])
    axes[1].set_xlabel('Duration\n(h)');axes[1].set_title('b  Duration',loc='left',pad=12)
    for ax in axes[:2]:p.clean_axis(ax,'x');ax.set_ylim(25.7,-.7)
    for ax,frame,col,cols,title in [(axes[2],tech,'technology_group',[t for t in p.TECH_ORDER if t in tech.technology_group.unique()],'c  Technology'),(axes[3],timing,'build_year',sorted(timing.build_year.dropna().astype(int).unique()),'d  Build year')]:
        tab=frame.pivot_table(index='scenario',columns=col,values='power_share_pct',aggfunc='sum').reindex(index=order,columns=cols).fillna(0)
        vals=tab.to_numpy(float).copy()
        if col=='build_year':vals[metrics.layer.to_numpy()=='A',:]=np.nan
        cmap=plt.get_cmap('Blues').copy();cmap.set_bad('#e8e8e8')
        im=ax.imshow(vals,aspect='auto',cmap=cmap,vmin=0,vmax=100)
        ax.set_ylim(25.7,-.7);ax.set_yticks([]);ax.set_xticks(range(len(cols)),[str(x).replace('Li-ion/LFP','LFP') for x in cols],rotation=90)
        ax.tick_params(length=0);ax.set_title(title,loc='left',pad=12)
        for sp in ax.spines.values():sp.set_visible(False)
        if col=='build_year':
            for i in range(8):ax.text((len(cols)-1)/2,i,'N/A',ha='center',va='center',fontsize=7.2,color='#555')
    for ax in axes:
        for row in [7.5,23.5]:ax.axhline(row,color='#999',lw=.65)
    cbax=fig.add_axes([.565,.95,.42,.012]);bar=fig.colorbar(im,cax=cbax,orientation='horizontal',ticks=[0,50,100]);bar.set_label('Share of reported new power (%)',fontsize=7.2)
    bar.ax.xaxis.set_label_position('top');bar.ax.tick_params(labelsize=7.2)
    fig.text(.03,.10,'Rows 01–08: static 2033 configurations; no construction-year trajectory (N/A).\nRows 09–24: multiyear pathways. Rows 25–26: equal-horizon comparison.\nAll panels retain the same 26-row order. Expanded* is a boundary-condition scenario.',fontsize=7.2,va='top',linespacing=1.45)
    save(fig,p.FIG_SUPP/'FigS14_future_storage_extended_robustness')
