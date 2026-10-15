"""Nature-family visual system for Storage V17T5R6R8R5 publication figures."""
from __future__ import annotations

import gc
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager

PALETTE = {
    "navy": "#17324D",
    "blue": "#3F7AA6",
    "cyan": "#58A6A6",
    "teal": "#2E8B8B",
    "orange": "#D98A3A",
    "vermillion": "#C75A4A",
    "red": "#B64045",
    "purple": "#7B6AAE",
    "green": "#4E8F62",
    "yellow": "#D6B24A",
    "sand": "#C6A66B",
    "grey": "#73787C",
    "mid_grey": "#AEB3B7",
    "light_grey": "#E4E7E9",
    "pale": "#F4F6F7",
    "dark": "#1C2023",
    "white": "#FFFFFF",
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
    "SL02_OPTIMAL_REALLOCATION": "Optimized reallocation",
    "SL03_NO_LEGACY": "No legacy",
    "SL04_RULE_LOAD": "Load rule",
    "SL05_RULE_VRE": "Renewables rule",
}
CONTEXT_LABELS = {
    "base": "Base",
    "tx_fixed": "Fixed transmission",
    "ph_conservative": "Conservative pumped hydro",
    "carbon_tight": "Tighter carbon cap",
    "battery_cost_low": "Low battery cost",
    "battery_cost_high": "High battery cost",
}

FIGURE_WIDTH_IN = 180.0 / 25.4


def configure() -> str:
    candidates = ["Arial", "Helvetica Neue", "Helvetica", "Liberation Sans", "DejaVu Sans"]
    available = {font.name for font in font_manager.fontManager.ttflist}
    family = next((font for font in candidates if font in available), "DejaVu Sans")
    mpl.rcParams.update(
        {
            "font.family": family,
            "mathtext.fontset": "custom",
            "mathtext.rm": family,
            "mathtext.it": f"{family}:italic",
            "mathtext.bf": f"{family}:bold",
            "mathtext.fallback": None,
            "font.size": 6.9,
            "axes.labelsize": 6.9,
            "axes.titlesize": 7.1,
            "xtick.labelsize": 6.3,
            "ytick.labelsize": 6.3,
            "legend.fontsize": 6.0,
            "axes.linewidth": 0.60,
            "xtick.major.width": 0.55,
            "ytick.major.width": 0.55,
            "xtick.major.size": 2.6,
            "ytick.major.size": 2.6,
            "xtick.minor.width": 0.40,
            "ytick.minor.width": 0.40,
            "xtick.minor.size": 1.5,
            "ytick.minor.size": 1.5,
            "axes.titlepad": 6.0,
            "axes.labelpad": 3.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.pad_inches": 0.00,
            "legend.frameon": False,
            "axes.unicode_minus": True,
        }
    )
    return family


def clean_axis(axis, grid_axis: str | None = None, *, zero_line: bool = False) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    if grid_axis:
        axis.grid(axis=grid_axis, color=PALETTE["light_grey"], linewidth=0.45, zorder=0)
    if zero_line:
        axis.axvline(0, color=PALETTE["dark"], linewidth=0.60, zorder=1)
    axis.tick_params(direction="out")
    axis.set_axisbelow(True)


def panel_label(axis, label: str, x: float = -0.12, y: float = 1.075) -> None:
    """Place a lowercase panel tag at one locked upper-left anchor.

    The optional x/y arguments remain accepted for backward compatibility but
    are intentionally ignored so every panel is aligned in the release.
    """
    axis.text(
        -0.12, 1.075, str(label).lower(), transform=axis.transAxes,
        fontweight="bold", fontsize=8.2, va="bottom", ha="left",
        color=PALETTE["dark"], clip_on=False,
    )


def direct_value(axis, x: float, y: float, text: str, *, ha: str = "left", va: str = "center", color: str | None = None, size: float = 6.0) -> None:
    axis.text(x, y, text, ha=ha, va=va, fontsize=size, color=color or PALETTE["dark"])


def save_figure(figure, output_base: Path, dpi: int = 600) -> None:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    figure.canvas.draw()
    for extension in ["pdf", "svg", "png"]:
        figure.savefig(output_base.with_suffix(f'.{extension}'), bbox_inches=None, dpi=dpi if extension == 'png' else None, metadata={"Creator": "Storage-system publication figure renderer"})
    plt.close(figure)
    del figure
    gc.collect()
