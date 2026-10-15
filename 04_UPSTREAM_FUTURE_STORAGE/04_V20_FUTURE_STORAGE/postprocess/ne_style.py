"""Nature-family figure style helpers for Storage V17."""
from __future__ import annotations
from pathlib import Path
import gc
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager

# Colour-blind-aware, restrained palette; white background; no gradients or 3-D.
PALETTE = {
    "navy": "#2B5A73", "blue": "#4C78A8", "teal": "#4F8F8B",
    "orange": "#E28E4B", "vermillion": "#C85C47", "purple": "#7A6FA8",
    "grey": "#8B8B8B", "light_grey": "#D9D9D9", "dark": "#222222",
    "green": "#6D9F71", "sand": "#C7A86B",
}
SCENARIO_COLORS = {
    "SL00_OBSERVED_ACTUAL": PALETTE["grey"],
    "SL01_OBSERVED_STANDARDIZED": PALETTE["blue"],
    "SL02_OPTIMAL_REALLOCATION": PALETTE["orange"],
    "SL03_NO_LEGACY": PALETTE["dark"],
    "SL04_RULE_LOAD": PALETTE["teal"],
    "SL05_RULE_VRE": PALETTE["purple"],
}
SCENARIO_LABELS = {
    "SL00_OBSERVED_ACTUAL": "Reconstructed duration",
    "SL01_OBSERVED_STANDARDIZED": "Reconstructed standardized",
    "SL02_OPTIMAL_REALLOCATION": "Optimal reallocation",
    "SL03_NO_LEGACY": "No legacy",
    "SL04_RULE_LOAD": "Load rule",
    "SL05_RULE_VRE": "VRE rule",
}


def configure():
    candidates=["Arial","Helvetica","Liberation Sans","DejaVu Sans"]
    available={f.name for f in font_manager.fontManager.ttflist}
    family=next((f for f in candidates if f in available),"DejaVu Sans")
    mpl.rcParams.update({
        "font.family": family, "font.size": 7.0, "axes.labelsize": 7.0,
        "axes.titlesize": 7.0, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
        "legend.fontsize": 6.5, "axes.linewidth": 0.65, "xtick.major.width": 0.6,
        "ytick.major.width": 0.6, "xtick.major.size": 2.8, "ytick.major.size": 2.8,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    })
    return family


def clean_axis(ax, grid_axis: str | None = None):
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    if grid_axis:
        ax.grid(axis=grid_axis, color="#E6E6E6", linewidth=0.45, zorder=0)
    ax.tick_params(direction="out")


def panel_label(ax, label: str, x: float=-0.12, y: float=1.05):
    ax.text(x,y,label,transform=ax.transAxes,fontweight="bold",fontsize=8.5,va="top",ha="left")


def save_figure(fig, outbase: Path, dpi: int=300):
    outbase.parent.mkdir(parents=True,exist_ok=True)
    for ext in ["pdf","svg","png"]:
        fig.savefig(outbase.with_suffix("."+ext),bbox_inches="tight",dpi=dpi if ext=="png" else None)
    plt.close(fig)
    del fig
    gc.collect()
