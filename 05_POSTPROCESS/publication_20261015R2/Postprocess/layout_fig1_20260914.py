"""Vector layout revision for Fig. 1, 14 September 2026.

Applied after the established data plotting and text updates.  No source table,
geographic artist, or plotted numerical value is changed by this module.
"""

from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.transforms import Bbox


def apply(fig, panels, out):
    """Tighten the map scale and show the primary comparison as a flow diagram."""
    map_ax, scatter_ax, _, flow_ax = panels
    fig.canvas.draw()

    # Resolve scale position from the *drawn* map frame, after its fixed
    # geographic aspect ratio and final publication dimensions have taken effect.
    # The 12 pt band contains the unchanged 7.2 pt tick labels with clear space
    # between their baseline and the geographic frame.
    bars = [ax for ax in fig.axes if hasattr(ax, "_colorbar")]
    point_y = 1.0 / (72.0 * fig.get_figheight())
    for scale, anchor in zip(bars[:2], (map_ax, scatter_ax)):
        def locate(_axis, _renderer, anchor=anchor):
            box = anchor.get_position()
            width = 0.53 * box.width
            return Bbox.from_bounds(
                box.x0 + 0.5 * (box.width - width),
                box.y1 + 12.0 * point_y,
                width,
                3.7 * point_y,
            )
        scale.set_axes_locator(locate)
        scale.tick_params(labelsize=7.2, length=1.8, pad=1.5)
        scale.xaxis.set_label_position("top")
        scale.xaxis.label.set_fontsize(7.2)
        scale.xaxis.labelpad = 2.0
        scale._colorbar.outline.set_linewidth(0.45)

    # A self-contained primary comparison.  Additional tests are specified in
    # the caption so that the zero-stock benchmark cannot appear to share the
    # matched inherited-stock constraint.
    flow_ax.clear()
    flow_ax.set_position([0.555, 0.075, 0.430, 0.383])
    flow_ax.set_axis_off()
    flow_ax.set_xlim(0.0, 1.0)
    flow_ax.set_ylim(0.0, 1.0)
    flow_ax.text(-0.047, 1.105, "d", transform=flow_ax.transAxes,
                 fontfamily="Arial", fontsize=9, fontweight="bold",
                 ha="left", va="top", color="#202B33")

    ink = "#263844"
    slate = "#647783"
    blue = "#3F7AA6"
    orange = "#C47A33"

    def box(x, y, width, height, edge, fill):
        flow_ax.add_patch(FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.010,rounding_size=0.016",
            linewidth=0.85, edgecolor=edge, facecolor=fill,
            zorder=2, clip_on=False,
        ))

    def label(x, y, text, *, bold=False, color=ink, size=7.2):
        flow_ax.text(x, y, text, ha="center", va="center",
                     fontfamily="Arial", fontsize=size,
                     fontweight="bold" if bold else "normal",
                     color=color, linespacing=1.25, zorder=5)

    def line(xs, ys):
        flow_ax.plot(xs, ys, color=slate, linewidth=0.85,
                     solid_capstyle="round", clip_on=False, zorder=1)

    def arrow(start, end):
        flow_ax.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=8.2,
            linewidth=0.85, color=slate, shrinkA=0, shrinkB=1.0,
            zorder=3, clip_on=False,
        ))

    box(0.03, 0.820, 0.94, 0.150, slate, "#F2F5F7")
    label(0.50, 0.925, "Inherited storage held fixed", bold=True, size=8.0)
    label(0.50, 0.867, "135.93 GW / 351.12 GWh")

    left, right = 0.2475, 0.7525
    line([0.50, 0.50], [0.810, 0.775])
    line([left, right], [0.775, 0.775])
    arrow((left, 0.775), (left, 0.733))
    arrow((right, 0.775), (right, 0.733))

    box(0.03, 0.520, 0.435, 0.200, blue, "#EFF5F9")
    box(0.535, 0.520, 0.435, 0.200, orange, "#FCF3E9")
    label(left, 0.674, "Existing layout", bold=True, color=blue, size=8.0)
    label(left, 0.614, "Existing initial sites")
    label(left, 0.563, "Common duration")
    label(right, 0.674, "Reference layout", bold=True, color=orange, size=8.0)
    label(right, 0.614, "Optimized initial sites")
    label(right, 0.563, "Common duration")

    line([left, left], [0.510, 0.473])
    line([right, right], [0.510, 0.473])
    line([left, right], [0.473, 0.473])
    arrow((0.50, 0.473), (0.50, 0.440))

    box(0.03, 0.255, 0.94, 0.175, slate, "#F7F9FA")
    label(0.50, 0.392, "System-cost optimization", bold=True, size=8.0)
    label(0.50, 0.331, "Investment and operation adjust")
    label(0.50, 0.280, "in each pathway, 2028–2058")

    arrow((0.50, 0.245), (0.50, 0.180))
    box(0.03, 0.035, 0.94, 0.135, slate, "#FFFFFF")
    label(0.50, 0.125, "Compare paired pathways", bold=True, size=8.0)
    label(0.50, 0.069, "Cost · regional differences · timing")

