"""Resolve province callouts at the final publication size without moving data.

Map labels deliberately use 3.8--4.2 pt Arial rather than the 7.2 pt lower
bound applied to quantitative axis text. All distances are in print points.
"""
import json
from pathlib import Path
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.text import Annotation, Text
from matplotlib.transforms import Bbox


def _circle_hit(box, xy, radius):
    near = np.maximum([box.x0, box.y0], np.minimum(xy, [box.x1, box.y1]))
    return np.linalg.norm(xy - near) < radius


def _segment_hits(a, b, xy, radius):
    v = b-a
    t = np.clip(np.dot(xy-a, v) / max(np.dot(v, v), 1e-12), 0., 1.)
    return np.linalg.norm(xy-(a+t*v)) < radius


def apply(fig, key, out):
    maps = [ax for ax in fig.axes if np.allclose(ax.get_xlim(), [73, 135])
            and np.allclose(ax.get_ylim(), [18, 54])]
    if not maps:
        return
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    unit = fig.dpi / 72.
    report = []
    for mi, ax in enumerate(maps):
        frame = ax.get_window_extent(renderer)
        size = 3.8 if frame.width / fig.dpi < 1.85 else 4.2
        labels = [t for t in ax.texts if isinstance(t, Annotation) and t.get_text().strip()]
        points = []
        for coll in ax.collections:
            if not isinstance(coll, PathCollection):
                continue
            offsets = np.asarray(coll.get_offsets(), dtype=float)
            sizes = np.resize(coll.get_sizes(), len(offsets))
            widths = np.resize(coll.get_linewidths(), len(offsets))
            for xy, s, lw in zip(coll.get_offset_transform().transform(offsets), sizes, widths):
                # Circular scatter markers are sqrt(s) points in diameter.
                points.append((xy, (np.sqrt(s)/2 + lw/2 + 1.0)*unit))
        obstacles = [child.get_window_extent(renderer).padded(1.0*unit) for child in ax.child_axes]
        for other in ax.texts:
            if other not in labels and other.get_visible() and other.get_text().strip():
                obstacles.append(other.get_window_extent(renderer).padded(1.0*unit))
        inner = Bbox.from_extents(frame.x0+2*unit, frame.y0+2*unit,
                                 frame.x1-2*unit, frame.y1-2*unit)
        originals = {}
        for ann in labels:
            ann.update_positions(renderer)
            old_box = Text.get_window_extent(ann, renderer)
            originals[ann] = dict(fontsize=ann.get_fontsize(),
                                  center=np.array([(old_box.x0+old_box.x1)/2, (old_box.y0+old_box.y1)/2]),
                                  anchor=list(ann.xy))
            ann.set_fontfamily('Arial')
            ann.set_fontsize(size)
            ann.set_fontweight('normal')
            ann.set_ha('center'); ann.set_va('center')
            ann.set_bbox(dict(boxstyle='square,pad=0.10', facecolor='white',
                              edgecolor='none', alpha=0.92))
            ann.set_path_effects([])
            ann.set_anncoords(ax.transAxes)
            ann.set_annotation_clip(False)
            ann.set_clip_on(False)
            ann.set_zorder(7)
            if ann.arrow_patch is not None:
                ann.arrow_patch.set_connectionstyle('arc3,rad=0')
                ann.arrow_patch.set_linewidth(.45)
                ann.arrow_patch.set_color('#536169')
                ann.arrow_patch.shrinkA=1.0
                anchor=ax.transData.transform(ann.xy)
                radius=max([r for xy,r in points if np.linalg.norm(xy-anchor)<.1]+[2*unit])
                ann.arrow_patch.shrinkB=radius/unit
        occupied=list(obstacles)
        placed=[]
        # Long names are placed first so short names can occupy the remaining gaps.
        for ann in sorted(labels, key=lambda t: -len(t.get_text())):
            anchor = ax.transData.transform(ann.xy)
            ann.set_position((.5,.5));ann.update_positions(renderer)
            box = Text.get_window_extent(ann, renderer)
            pad = (size*.10 + .7)*unit
            w,h = box.width+2*pad, box.height+2*pad
            candidates=[originals[ann]['center']]
            for rad in [10,14,18,23,29,36,45,55,70]:
                for theta in np.linspace(0,2*np.pi,24,endpoint=False):
                    candidates.append(anchor+rad*unit*np.array([np.cos(theta),np.sin(theta)]))
            # A deterministic whole-frame fallback handles dense eastern provinces.
            for x in np.linspace(inner.x0+w/2,inner.x1-w/2,24):
                for y in np.linspace(inner.y0+h/2,inner.y1-h/2,16):candidates.append(np.array([x,y]))
            best=None
            for center in candidates:
                center=np.maximum([inner.x0+w/2,inner.y0+h/2],np.minimum(center,[inner.x1-w/2,inner.y1-h/2]))
                rect=Bbox.from_bounds(center[0]-w/2,center[1]-h/2,w,h)
                if any(rect.overlaps(b) for b in occupied):continue
                crossings=sum(_segment_hits(center,anchor,xy,r) for xy,r in points if np.linalg.norm(xy-anchor)>.1)
                if any(_circle_hit(rect,xy,r) for xy,r in points):continue
                length=np.linalg.norm(center-anchor)/unit
                drift=np.linalg.norm(center-originals[ann]['center'])/unit
                score=length+.10*drift+crossings*20
                if best is None or score<best[0]:best=(score,center,rect,crossings)
            if best is None:
                raise RuntimeError(f'{key} map {mi+1}: no collision-free position for {ann.get_text()}')
            _,center,rect,crossings=best
            ann.set_position(ax.transAxes.inverted().transform(center))
            occupied.append(rect)
            placed.append((ann,rect,crossings))
        fig.canvas.draw()
        entries=[]
        for ann,rect,crossings in placed:
            ann.update_positions(renderer)
            actual=ann.get_bbox_patch().get_window_extent(renderer)
            assert inner.contains(actual.x0,actual.y0) and inner.contains(actual.x1,actual.y1),(key,ann.get_text(),'out of frame')
            assert not any(_circle_hit(actual,xy,r) for xy,r in points),(key,ann.get_text(),'marker overlap')
            assert not any(actual.overlaps(b) for b in obstacles),(key,ann.get_text(),'inset/text overlap')
            assert list(ann.xy)==originals[ann]['anchor']
            entries.append(dict(text=ann.get_text(),font_pt=size,old_font_pt=originals[ann]['fontsize'],
                                anchor_data=list(map(float,ann.xy)),label_axes=list(map(float,ann.get_position())),
                                box_figure=list(map(float,actual.transformed(fig.transFigure.inverted()).extents)),
                                leader_other_marker_crossings=int(crossings)))
        for i,(a,_,_) in enumerate(placed):
            for b,_,_ in placed[i+1:]:
                assert not a.get_bbox_patch().get_window_extent(renderer).overlaps(b.get_bbox_patch().get_window_extent(renderer))
        report.append(dict(map_index=mi+1,width_inches=frame.width/fig.dpi,
                           map_box_figure=list(map(float,frame.transformed(fig.transFigure.inverted()).extents)),
                           label_count=len(labels),labels=entries,text_overlap_count=0,marker_overlap_count=0,outside_frame_count=0))
    dest=Path(out)/'核查记录/map_labels_20260915'
    dest.mkdir(parents=True,exist_ok=True)
    (dest/(key+'.json')).write_text(json.dumps(dict(figure=key,maps=report),indent=2),encoding='utf-8')

