"""Print-scale layout for Fig. 4; all coordinates derive from locked tables."""
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.text import Annotation
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Rectangle

import ne_style


def apply(fig, panels, out):
    """Widen the alluvial plot and reconnect four scatter labels to source data.

    Call after the base Fig. 4 layout. This changes only presentation, retaining
    all scatter values, class assignments and initial-absolute-difference weights.
    """
    out = Path(out)
    _, b, _, _, d = panels
    q = pd.read_csv(out / 'Postprocess/tables/main/fig4c_zone_correction.csv')
    assert q.model_zone.is_unique
    classes = ['persistent or amplified', 'partly corrected',
               'substantially corrected', 'reversal']
    counts = q.correction_class.value_counts().to_dict()
    assert [counts[c] for c in classes] == [1, 8, 11, 12]
    assert np.allclose(q.initial_absolute_power_mw,
                       np.abs(q.optimized_minus_observed_power_mw),
                       rtol=0, atol=1e-8)

    # The actual axes frames share both horizontal boundaries. The right column
    # has extra width, and the Sankey curves use most of that width directly.
    left, right = .535, .985
    b.set_position([left, .66, right-left, .25])
    d.set_position([left, .074, right-left, .476])

    # Place each label in a separate empty quadrant; no label crosses another
    # label's leader. xy is the exact table point, never the label's position.
    labels = {
        'Xinjiang': ('Xinjiang', (-22.0, -10.5)),
        'West_Inner_Mongolia': ('W. Inner Mong.', (-17.5, 11.0)),
        'Shandong': ('Shandong', (17.0, 11.0)),
        'Guangdong': ('Guangdong', (17.0, -10.5)),
    }
    for text in list(b.texts):
        if isinstance(text, Annotation):
            text.remove()
    anchors = {}
    for zone, (label, position) in labels.items():
        row = q.loc[q.model_zone.eq(zone)].iloc[0]
        xy = (float(row.optimized_minus_observed_power_mw) / 1000.0,
              float(row.final_power_delta_mw) / 1000.0)
        ann = b.annotate(
            label, xy=xy, xycoords='data', xytext=position, textcoords='data',
            ha='center', va='center', fontsize=7.2, fontfamily='Arial',
            color=ne_style.PALETTE['dark'], zorder=20,
            bbox=dict(facecolor='white', edgecolor='none', pad=1.0, alpha=.97),
            arrowprops=dict(arrowstyle='-', color='#56656D', linewidth=.65,
                            shrinkA=3.0, shrinkB=0.0,
                            connectionstyle='arc3,rad=0'),
            annotation_clip=False)
        assert tuple(ann.xy) == xy
        # A leader must end at an actual scatter marker, in addition to matching
        # the locked source-table coordinates.
        plotted = [np.asarray(c.get_offsets(), dtype=float) for c in b.collections
                   if hasattr(c, 'get_offsets')]
        assert any(np.any(np.all(np.isclose(points, xy, rtol=0, atol=1e-10), axis=1))
                   for points in plotted if len(points))
        anchors[zone] = dict(x_gw=xy[0], y_gw=xy[1], label_xy=position)

    d.clear()
    d.set_axis_off()
    d.set_xlim(0, 1)
    d.set_ylim(0, 1.04)
    q = q.assign(positive=q.optimized_minus_observed_power_mw.gt(0))
    grouped = q.groupby(['positive', 'correction_class']).initial_absolute_power_mw.sum()
    total = float(grouped.sum())
    assert np.isclose(total, q.initial_absolute_power_mw.sum(), rtol=0, atol=1e-7)
    colors = [ne_style.PALETTE[k] for k in ['red', 'orange', 'teal', 'purple']]
    scale, gap = .77, .044
    source, target = {}, {}
    cursor = .08
    for sign in [True, False]:
        height = float(grouped.loc[sign].sum()) / total * scale
        source[sign] = [cursor, cursor + height]
        cursor += height + gap
    cursor = .08
    for cls in classes:
        height = float(grouped.xs(cls, level=1).sum()) / total * scale
        target[cls] = [cursor, cursor + height]
        cursor += height + gap
    source_cursor = {k: v[0] for k, v in source.items()}
    target_cursor = {k: v[0] for k, v in target.items()}

    # Physical curve width: .45 * (.735-.065) * 171 mm = 51.56 mm.
    # The previous .48 * (.83-.27) / 1.55 * 171 mm = 29.65 mm.
    x0, x1 = .065, .735
    for sign in [True, False]:
        for cls, color in zip(classes, colors):
            height = float(grouped.get((sign, cls), 0)) / total * scale
            if height == 0:
                continue
            sy, ty = source_cursor[sign], target_cursor[cls]
            source_cursor[sign] += height
            target_cursor[cls] += height
            vertices = [(x0, sy), (.30, sy), (.50, ty), (x1, ty),
                        (x1, ty+height), (.50, ty+height), (.30, sy+height),
                        (x0, sy+height), (x0, sy)]
            codes = [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
                     MplPath.LINETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
                     MplPath.CLOSEPOLY]
            d.add_patch(PathPatch(MplPath(vertices, codes), facecolor=color,
                                  edgecolor='none', alpha=.49, zorder=1))
    for sign, (low, high) in source.items():
        d.add_patch(Rectangle((.030, low), .035, high-low,
                              facecolor=ne_style.PALETTE['blue'], edgecolor='none'))
        d.text(.012, (low+high)/2, 'Positive' if sign else 'Negative',
               ha='right', va='center', fontsize=7.2, fontfamily='Arial')
    class_labels = ['Persistent /\namplified (1)', 'Partly\ncorrected (8)',
                    'Substantially\ncorrected (11)', 'Sign reversal\n(12)']
    for cls, color, label in zip(classes, colors, class_labels):
        low, high = target[cls]
        d.add_patch(Rectangle((x1, low), .035, high-low,
                              facecolor=color, edgecolor='none'))
        d.text(.795, (low+high)/2, label, ha='left', va='center',
               fontsize=7.2, fontfamily='Arial', linespacing=1.2)
    d.text(-.10, 1.045, 'd', transform=d.transAxes,
           fontweight='bold', fontsize=9, fontfamily='Arial')
    d.text(.030, 1.020, 'Initial sign', ha='center', va='bottom',
           fontsize=7.2, fontweight='bold', fontfamily='Arial')
    d.text(.795, 1.020, '2058 class', ha='left', va='bottom',
           fontsize=7.2, fontweight='bold', fontfamily='Arial')

    # The final caption supplies weighting and ordered classification rules.
    for text in list(fig.texts):
        if ('Width: absolute initial regional difference.' in text.get_text()
                or 'Remaining magnitude ≤10%' in text.get_text()):
            text.remove()

    fig.canvas.draw()
    assert np.allclose([b.get_position().x0, b.get_position().x1],
                       [d.get_position().x0, d.get_position().x1],
                       rtol=0, atol=1e-12)
    fig._fig4_layout_audit = dict(
        labels=anchors, category_counts=counts, initial_absolute_weight_mw=total,
        curve_width_mm=(right-left)*(x1-x0)*171,
        former_curve_width_mm=.48*(.83-.27)/1.55*171,
        aligned_axes_x=[left, right])
