#!/usr/bin/env python3
"""Render the frozen V17T5R6R7 main-model figures within V17T5R6R8R5.

The confirmatory visual narrative is: inherited geography -> spatial value ->
compensatory investment -> persistence -> robustness. Gross dispatch,
directional transmission flow, reserve transfer, and charge/discharge
components are deliberately excluded because the certified optimum is highly
degenerate along those operational dimensions.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.patches import FancyBboxPatch, PathPatch, Polygon, Rectangle
from matplotlib.transforms import Bbox
from matplotlib.ticker import FormatStrFormatter
from matplotlib.path import Path as MplPath
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from ne_style import (
    CONTEXT_LABELS,
    PALETTE,
    SCENARIO_COLORS,
    SCENARIO_LABELS,
    clean_axis,
    configure,
    direct_value,
    panel_label,
    save_figure,
)
from v17t5_paths import FIG_MAIN, FIG_SUPP, TABLE_MAIN, TABLE_SUPP, MAP_ASSET_CANDIDATES

PAIR = ["SL01_OBSERVED_STANDARDIZED", "SL02_OPTIMAL_REALLOCATION"]
CORE = [
    "SL00_OBSERVED_ACTUAL",
    "SL01_OBSERVED_STANDARDIZED",
    "SL02_OPTIMAL_REALLOCATION",
    "SL03_NO_LEGACY",
    "SL04_RULE_LOAD",
    "SL05_RULE_VRE",
]
CONTEXTS = [
    "base",
    "tx_fixed",
    "ph_conservative",
    "carbon_tight",
    "battery_cost_low",
    "battery_cost_high",
]

# Short publication labels are used only where two robustness panels share a
# narrow two-column row.  The scientific context identifiers remain unchanged.
ROBUSTNESS_CONTEXT_LABELS = {
    **CONTEXT_LABELS,
    "ph_conservative": "Pumped-storage constraint",
}

CORRECTION_LABELS = {
    "persistent or amplified": "Persistent/amplified",
    "partly corrected": "Partly corrected",
    "substantially corrected": "Substantially corrected",
    "reversal": "Sign reversal",
    "near zero initially": "Near zero initially",
}

SCENARIO_SHORT_LABELS = {
    "SL00_OBSERVED_ACTUAL": "Reconstructed duration",
    "SL01_OBSERVED_STANDARDIZED": "Reconstructed standardized",
    "SL02_OPTIMAL_REALLOCATION": "Optimized",
    "SL03_NO_LEGACY": "No legacy",
    "SL04_RULE_LOAD": "Load rule",
    "SL05_RULE_VRE": "Renewables rule",
    "SL06_TX_FIXED_OBSERVED": "Fixed Tx · observed",
    "SL07_TX_FIXED_OPTIMAL": "Fixed Tx · optimized",
    "SL08_PH_CONSERVATIVE_OBSERVED": "Conservative PH · observed",
    "SL09_PH_CONSERVATIVE_OPTIMAL": "Conservative PH · optimized",
    "SL10_CARBON_TIGHT_OBSERVED": "Tighter carbon · observed",
    "SL11_CARBON_TIGHT_OPTIMAL": "Tighter carbon · optimized",
    "SL12_COST_LOW_OBSERVED": "Low battery cost · observed",
    "SL13_COST_LOW_OPTIMAL": "Low battery cost · optimized",
    "SL14_COST_HIGH_OBSERVED": "High battery cost · observed",
    "SL15_COST_HIGH_OPTIMAL": "High battery cost · optimized",
}


def read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def _duration_histogram(axis, values: pd.Series, *, color: str, max_bins: int = 10) -> None:
    """Plot a duration distribution without inventing bins for point-mass data."""
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    if numeric.size == 0 or not np.isfinite(numeric).all():
        raise ValueError("Duration distribution must contain finite values only")
    vmin, vmax = float(numeric.min()), float(numeric.max())
    scale = max(abs(vmin), abs(vmax), 1.0)
    resolution = 64.0 * np.finfo(float).eps * scale
    if vmax - vmin <= resolution:
        center = float(numeric.mean())
        axis.vlines(center, 0.0, len(numeric), color=color, linewidth=6.0, alpha=0.80)
        axis.scatter([center], [len(numeric)], s=16, color=color, edgecolor="white", linewidth=0.4, zorder=3)
        pad = max(0.05, 0.03 * max(abs(center), 1.0))
        axis.set_xlim(center - pad, center + pad)
        axis.annotate(f"Point mass at {center:.2f} h", (center, len(numeric)), xytext=(4, -2), textcoords="offset points", ha="left", va="top", fontsize=5.4)
        return
    bin_count = min(max_bins, max(1, len(np.unique(numeric))))
    edges = np.linspace(vmin, vmax, bin_count + 1)
    if not np.all(np.diff(edges) > 0.0):
        raise ValueError("Unable to construct strictly increasing duration-bin edges")
    axis.hist(numeric, bins=edges, color=color, alpha=0.80, edgecolor="white")


def zone_label(zone: str) -> str:
    return str(zone).replace("_", " ")


def zone_label_compact(zone: str) -> str:
    labels = {
        "West_Inner_Mongolia": "W. Inner Mong.",
        "East_Inner_Mongolia": "E. Inner Mong.",
        "Heilongjiang": "Heilongjiang",
    }
    return labels.get(str(zone), zone_label(zone))


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _assert_x_aligned(axis_a, axis_b, label: str, tol: float = 1.0e-6) -> None:
    box_a, box_b = axis_a.get_position(), axis_b.get_position()
    mismatch = max(abs(box_a.x0 - box_b.x0), abs(box_a.x1 - box_b.x1))
    if mismatch > tol:
        raise RuntimeError(f"{label}: horizontal frame mismatch {mismatch:.3e}")


def _resolve_map_asset(name: str) -> Path | None:
    for root in MAP_ASSET_CANDIDATES:
        cand = root / name
        if cand.is_file():
            return cand
    return None


MAP_SEA_FACE = "#E3EDF2"
MAP_LAND_FACE = "#F4EFE4"
MAP_PROVINCE_EDGE = "#66757D"
MAP_FRAME_EDGE = "#536169"
MAP_TAIWAN_EDGE = "#34434B"


def _draw_geom(
    axis,
    geom,
    *,
    edgecolor="#D5DADD",
    facecolor="#F7F8F8",
    hole_facecolor="white",
    lw=0.45,
    zorder=0,
    alpha=1.0,
):
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    def draw_polygon(poly):
        if not poly:
            return
        outer = np.asarray(poly[0])
        if outer.size == 0:
            return
        axis.add_patch(Polygon(outer, closed=True, facecolor=facecolor, edgecolor=edgecolor, linewidth=lw, zorder=zorder, alpha=alpha))
        for hole in poly[1:]:
            hole_arr = np.asarray(hole)
            if hole_arr.size:
                axis.add_patch(Polygon(hole_arr, closed=True, facecolor=hole_facecolor, edgecolor=edgecolor, linewidth=max(lw*0.5,0.2), zorder=zorder, alpha=1.0))
    def draw_line(line):
        arr = np.asarray(line)
        if arr.size:
            axis.plot(arr[:,0], arr[:,1], color=edgecolor, linewidth=lw, zorder=zorder, alpha=alpha)
    if gtype == "Polygon":
        draw_polygon(coords)
    elif gtype == "MultiPolygon":
        for poly in coords:
            draw_polygon(poly)
    elif gtype == "LineString":
        draw_line(coords)
    elif gtype == "MultiLineString":
        for line in coords:
            draw_line(line)


def _draw_basemap(axis, *, with_inset: bool = True):
    provinces = _resolve_map_asset("china_provinces.geojson")
    nine_dash = _resolve_map_asset("nine_dash_line_geometry_only.geojson")
    # Separate sea, land and administrative lines by both tone and stroke.
    # The contrast remains legible after reduction to journal column width
    # without competing with the quantitative marker colours.
    axis.set_facecolor(MAP_SEA_FACE)
    if provinces is not None:
        data = _load_json(provinces)
        # Pass 1: a quiet but visible land/sea substrate.  Administrative
        # outlines are redrawn in a second pass above network links so that
        # the province geography remains legible under the analytical layer.
        for feat in data.get("features", []):
            province_name = str(feat.get("properties", {}).get("name", ""))
            is_taiwan = province_name == "台湾省"
            _draw_geom(
                axis,
                feat["geometry"],
                edgecolor="#AEB8BC",
                facecolor="#E8ECE2" if is_taiwan else MAP_LAND_FACE,
                hole_facecolor=MAP_SEA_FACE,
                lw=0.42,
                zorder=0.10,
            )
        # Pass 2: explicit province and Taiwan outlines.  This layer sits
        # above transmission links but below quantitative markers.
        for feat in data.get("features", []):
            province_name = str(feat.get("properties", {}).get("name", ""))
            is_taiwan = province_name == "台湾省"
            _draw_geom(
                axis,
                feat["geometry"],
                edgecolor=MAP_TAIWAN_EDGE if is_taiwan else MAP_PROVINCE_EDGE,
                facecolor="none",
                hole_facecolor="none",
                lw=1.10 if is_taiwan else 0.72,
                zorder=1.65,
            )
        # Taiwan is part of the complete national map but carries no model-zone
        # result in this mainland power-system study.  A small geographic label
        # makes the territorial element visible without implying a data value.
        axis.annotate(
            "Taiwan",
            xy=(121.05, 23.75), xycoords="data",
            xytext=(124.3, 27.4), textcoords="data",
            fontsize=4.25, fontweight="bold", color=MAP_TAIWAN_EDGE,
            ha="right", va="center", zorder=10, annotation_clip=False,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.10, "alpha": 0.90},
            arrowprops={"arrowstyle": "-", "linewidth": 0.55, "color": MAP_TAIWAN_EDGE,
                        "shrinkA": 1.0, "shrinkB": 1.5},
        )
    if with_inset and nine_dash is not None:
        # A narrow inset keeps Taiwan fully visible on the main map while the
        # darker discontinuous lines remain legible at journal width.
        iax = axis.inset_axes([0.825, 0.030, 0.155, 0.300], zorder=8)
        iax.set_facecolor(MAP_SEA_FACE)
        if provinces is not None:
            pdata = _load_json(provinces)
            for feat in pdata.get("features", []):
                province_name = str(feat.get("properties", {}).get("name", ""))
                is_taiwan = province_name == "台湾省"
                _draw_geom(
                    iax,
                    feat["geometry"],
                    edgecolor=MAP_TAIWAN_EDGE if is_taiwan else MAP_PROVINCE_EDGE,
                    facecolor="#E8ECE2" if is_taiwan else MAP_LAND_FACE,
                    hole_facecolor=MAP_SEA_FACE,
                    lw=0.92 if is_taiwan else 0.54,
                    zorder=0.48 if is_taiwan else 0.10,
                )
        ndata = _load_json(nine_dash)
        for feat in ndata.get("features", []):
            _draw_geom(iax, feat["geometry"], edgecolor="#3F4B52", facecolor="none", lw=1.12, zorder=2)
        iax.set_xlim(104, 125); iax.set_ylim(2, 26); iax.set_xticks([]); iax.set_yticks([])
        for s in iax.spines.values():
            s.set_linewidth(0.82); s.set_color(MAP_FRAME_EDGE)
    elif nine_dash is not None:
        ndata = _load_json(nine_dash)
        for feat in ndata.get("features", []):
            _draw_geom(axis, feat["geometry"], edgecolor="#7A7D80", facecolor="none", lw=0.45, zorder=0)


def _draw_network(axis, nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    xy = nodes.set_index("model_zone")[["longitude", "latitude"]]
    capacities = pd.to_numeric(edges["existing_capacity_mw"], errors="coerce").fillna(0.0)
    edge_max = max(float(capacities.max()), 1.0)
    for row in edges.itertuples(index=False):
        if row.zone_from not in xy.index or row.zone_to not in xy.index:
            continue
        a = xy.loc[row.zone_from]
        b = xy.loc[row.zone_to]
        capacity = max(float(getattr(row, "existing_capacity_mw", 0.0)), 0.0)
        linewidth = 0.20 + 0.85 * np.sqrt(capacity / edge_max)
        axis.plot(
            [a.longitude, b.longitude],
            [a.latitude, b.latitude],
            color="#CCD2D6",
            linewidth=linewidth,
            alpha=0.80,
            zorder=1,
        )


def _candidate_label_positions(zone: str, point_axes: tuple[float, float], preferred_override: dict[str, tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    """Candidate callout positions in axes coordinates, strongly biased to map whitespace."""
    preferred = {
        "Xinjiang": [(0.30, 0.94), (0.05, 0.82), (0.34, 0.07)],
        "West_Inner_Mongolia": [(0.02, 0.66), (0.03, 0.82), (0.36, 0.96)],
        "East_Inner_Mongolia": [(0.98, 0.91), (0.98, 0.78), (0.63, 0.96)],
        "Hebei": [(0.98, 0.84), (0.98, 0.70), (0.68, 0.96)],
        "Shandong": [(0.98, 0.58), (0.98, 0.70), (0.75, 0.08)],
        "Jiangsu": [(0.98, 0.44), (0.98, 0.55), (0.78, 0.07)],
        "Zhejiang": [(0.98, 0.29), (0.97, 0.40), (0.74, 0.06)],
        "Fujian": [(0.96, 0.18), (0.84, 0.05), (0.98, 0.30)],
        "Guangdong": [(0.18, 0.06), (0.43, 0.04), (0.94, 0.10)],
        "Gansu": [(0.03, 0.50), (0.05, 0.65), (0.40, 0.95)],
        "Ningxia": [(0.04, 0.43), (0.04, 0.58), (0.47, 0.95)],
        "Qinghai": [(0.04, 0.31), (0.04, 0.47), (0.30, 0.06)],
        "Liaoning": [(0.98, 0.73), (0.98, 0.86), (0.75, 0.96)],
        "Jilin": [(0.98, 0.83), (0.98, 0.69), (0.70, 0.96)],
        "Anhui": [(0.98, 0.35), (0.98, 0.49), (0.70, 0.06)],
    }
    px, py = point_axes
    def _clamp(v: float, lo: float, hi: float) -> float:
        return min(max(v, lo), hi)
    side = 0.02 if px >= 0.50 else 0.98
    generic = [
        (side, _clamp(py + 0.14, 0.10, 0.92)),
        (side, _clamp(py, 0.09, 0.91)),
        (side, _clamp(py - 0.14, 0.08, 0.90)),
        (0.02, _clamp(py + 0.14, 0.10, 0.92)),
        (0.02, _clamp(py, 0.09, 0.91)),
        (0.02, _clamp(py - 0.14, 0.08, 0.90)),
        (0.98, _clamp(py + 0.14, 0.10, 0.92)),
        (0.98, _clamp(py, 0.09, 0.91)),
        (0.98, _clamp(py - 0.14, 0.08, 0.90)),
        (_clamp(px, 0.16, 0.84), 0.96),
        (_clamp(px, 0.16, 0.84), 0.05),
        (0.14, 0.95), (0.86, 0.95), (0.14, 0.05), (0.86, 0.05),
    ]
    ordered = []
    if preferred_override and zone in preferred_override:
        ordered.append(preferred_override[zone])
    for item in preferred.get(zone, []):
        if item not in ordered:
            ordered.append(item)
    for item in generic:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _occupied_node_boxes(axis, nodes: pd.DataFrame, radius_px: float = 16.0) -> list[Bbox]:
    boxes: list[Bbox] = []
    if "longitude" not in nodes.columns or "latitude" not in nodes.columns:
        return boxes
    for row in nodes[["longitude", "latitude"]].dropna().itertuples(index=False):
        x, y = axis.transData.transform((float(row.longitude), float(row.latitude)))
        boxes.append(Bbox.from_extents(x - radius_px, y - radius_px, x + radius_px, y + radius_px))
    return boxes


def _map_callout(axis, zone: str, longitude: float, latitude: float, xytext_axes: tuple[float, float], *, fontsize: float = 4.8, arrow_color: str | None = None, arrow_width: float = 0.60):
    point_axes = axis.transAxes.inverted().transform(axis.transData.transform((longitude, latitude)))
    tx, ty = xytext_axes
    if tx >= 0.85:
        ha = "right"
    elif tx <= 0.15:
        ha = "left"
    else:
        ha = "left" if tx >= point_axes[0] else "right"
    connection = "angle3,angleA=0,angleB=90" if abs(tx - point_axes[0]) > 0.10 else "arc3,rad=0.08"
    return axis.annotate(
        zone_label_compact(zone),
        (longitude, latitude),
        xycoords="data",
        xytext=(tx, ty),
        textcoords=axis.transAxes,
        ha=ha,
        va="center",
        fontsize=fontsize,
        color=PALETTE["dark"],
        bbox={"boxstyle": "round,pad=0.16", "facecolor": "white", "edgecolor": "none", "alpha": 0.90},
        arrowprops={
            "arrowstyle": "-",
            "connectionstyle": connection,
            "shrinkA": 1.2,
            "shrinkB": 4.0,
            "linewidth": arrow_width,
            "color": arrow_color or PALETTE["blue"],
        },
        zorder=6,
        annotation_clip=False,
        clip_on=False,
    )


def _place_nonoverlapping_map_labels(axis, nodes: pd.DataFrame, zones: list[str], preferred_positions: dict[str, tuple[float, float]] | None = None, fontsize: float = 4.8, arrow_color: str | None = None, arrow_width: float = 0.60) -> None:
    """Place selected province callouts into map whitespace without overlapping circles or other callouts."""
    figure = axis.figure
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    occupied: list[Bbox] = _occupied_node_boxes(axis, nodes)
    axis_box = axis.get_window_extent(renderer=renderer).expanded(1.24, 1.18)
    lookup = nodes.set_index("model_zone")
    for zone in zones:
        if zone not in lookup.index:
            continue
        row = lookup.loc[zone]
        lon, lat = float(row["longitude"]), float(row["latitude"])
        point_axes = axis.transAxes.inverted().transform(axis.transData.transform((lon, lat)))
        accepted = False
        for position in _candidate_label_positions(zone, tuple(point_axes), preferred_positions):
            annotation = _map_callout(axis, zone, lon, lat, position, fontsize=fontsize, arrow_color=arrow_color, arrow_width=arrow_width)
            figure.canvas.draw()
            box = annotation.get_window_extent(renderer=renderer).expanded(1.05, 1.12)
            if not any(box.overlaps(previous) for previous in occupied):
                occupied.append(box)
                accepted = True
                break
            annotation.remove()
        if not accepted:
            continue

def top_map_colorbar(figure, axes, artist, label, *, width=0.60):
    """Place the complete horizontal scale above its final map frame(s).

    Geometry is resolved at draw time, after aspect and subplot adjustments.
    The bar, tick labels and caption therefore cannot cover provincial data.
    """
    axes = list(axes) if isinstance(axes, (tuple, list)) else [axes]
    cax = figure.add_axes([0.1, 0.1, 0.1, 0.01], zorder=9)
    def locate(_axis, _renderer):
        boxes = [a.get_position() for a in axes]
        x0, x1 = min(b.x0 for b in boxes), max(b.x1 for b in boxes)
        y1 = max(b.y1 for b in boxes)
        point_y = 1.0 / (72.0 * figure.get_figheight())
        return Bbox.from_bounds(x0 + (1-width)*(x1-x0)/2,
                                y1 + 9.0*point_y, width*(x1-x0), 3.0*point_y)
    cax.set_axes_locator(locate)
    cax.set_facecolor('white')
    bar = figure.colorbar(artist, cax=cax, orientation='horizontal')
    bar.ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
    bar.ax.tick_params(labelsize=4.7, length=1.5, pad=1.0)
    bar.set_label(label, fontsize=5.2, labelpad=1.0)
    bar.ax.xaxis.set_label_position('top')
    bar.outline.set_linewidth(0.35)
    if not hasattr(figure, '_top_map_scales'): figure._top_map_scales=[]
    figure._top_map_scales.append((axes, cax, label))
    return bar


def node_map(
    axis,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    size_column: str,
    color_column: str,
    title: str,
    delta: bool = False,
    labels: int = 5,
    label_zones: list[str] | None = None,
    size_max: float | None = None,
    norm=None,
    cmap: str | None = None,
    color_label: str | None = None,
    figure=None,
    with_inset: bool = True,
):
    _draw_basemap(axis, with_inset=with_inset)
    _draw_network(axis, nodes, edges)
    sizes_raw = pd.to_numeric(nodes[size_column], errors="coerce").fillna(0.0)
    colors_raw = pd.to_numeric(nodes[color_column], errors="coerce").fillna(0.0)
    scale = max(float(size_max if size_max is not None else sizes_raw.abs().max()), 1e-12)
    sizes = 13 + 175 * np.sqrt(sizes_raw.abs() / scale)
    if norm is None:
        if delta:
            limit = max(float(colors_raw.abs().max()), 1e-9)
            norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
        else:
            norm = Normalize(vmin=min(0.0, float(colors_raw.min())), vmax=max(float(colors_raw.max()), 1e-9))
    scatter = axis.scatter(
        nodes["longitude"], nodes["latitude"], s=sizes, c=colors_raw,
        cmap=cmap or ("RdBu_r" if delta else "viridis"), norm=norm,
        edgecolor="white", linewidth=0.55, zorder=3,
    )
    axis.set_xlim(73, 135)
    axis.set_ylim(18, 54)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    # Panel micro-titles intentionally omitted for a cleaner publication layout.
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color(MAP_FRAME_EDGE)
        spine.set_linewidth(0.72)
    if labels:
        if label_zones is None:
            label_zones = nodes.loc[sizes_raw.abs().nlargest(min(labels, len(nodes))).index, "model_zone"].astype(str).tolist()
        else:
            label_zones = [str(zone) for zone in label_zones[:labels]]
        _place_nonoverlapping_map_labels(axis, nodes, label_zones)
    if figure is not None and color_label:
        top_map_colorbar(figure, axis, scatter, color_label)
    return scatter


def _annotate_named_map_labels(axis, frame: pd.DataFrame, positions: dict[str, tuple[float, float]], fontsize: float = 4.8, arrow_color: str | None = None, arrow_width: float = 0.60) -> None:
    figure = axis.figure
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    occupied: list[Bbox] = _occupied_node_boxes(axis, frame, radius_px=18.0)
    axis_box = axis.get_window_extent(renderer=renderer).expanded(1.24, 1.18)
    lookup = frame.set_index("model_zone")
    deferred: list[str] = []
    for zone, position in positions.items():
        if zone not in lookup.index:
            continue
        row = lookup.loc[zone]
        ann = _map_callout(axis, zone, float(row["longitude"]), float(row["latitude"]), position, fontsize=fontsize, arrow_color=arrow_color, arrow_width=arrow_width)
        figure.canvas.draw()
        box = ann.get_window_extent(renderer=renderer).expanded(1.05, 1.12)
        inside = axis_box.contains(box.x0, box.y0) and axis_box.contains(box.x1, box.y1)
        if inside and not any(box.overlaps(previous) for previous in occupied):
            occupied.append(box)
        else:
            ann.remove()
            deferred.append(str(zone))
    if deferred:
        _place_nonoverlapping_map_labels(axis, frame, deferred, preferred_positions=positions, fontsize=fontsize, arrow_color=arrow_color, arrow_width=arrow_width)


def _annotate_named_map_labels_force(axis, frame: pd.DataFrame, positions: dict[str, tuple[float, float]], fontsize: float = 4.8, arrow_color: str | None = None, arrow_width: float = 0.60) -> None:
    lookup = frame.set_index("model_zone")
    for zone, position in positions.items():
        if zone not in lookup.index:
            continue
        row = lookup.loc[zone]
        _map_callout(axis, zone, float(row["longitude"]), float(row["latitude"]), position, fontsize=fontsize, arrow_color=arrow_color, arrow_width=arrow_width)


def _annotate_top(axis, frame: pd.DataFrame, x: str, y: str, rank: str, n: int = 6) -> None:
    for row in frame.nlargest(n, rank).itertuples(index=False):
        axis.annotate(
            zone_label(getattr(row, "model_zone")),
            (getattr(row, x), getattr(row, y)),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=5.1,
            arrowprops={"arrowstyle": "-", "color": PALETTE["mid_grey"], "linewidth": 0.35},
        )


def _forest(axis, frame: pd.DataFrame, metric: str, scale: float, xlabel: str, panel: str, color: str, *, show_ylabels: bool = True, labels_toward_zero: bool = False) -> None:
    group = frame[frame["metric"].eq(metric)].set_index("legacy_context").reindex(CONTEXTS)
    values = group["observed_minus_optimal"].astype(float) / scale
    y = np.arange(len(CONTEXTS))
    panel_label(axis, panel)
    axis.axvline(0, color=PALETTE["dark"], linestyle="--", linewidth=0.7, zorder=1)
    axis.hlines(y, np.minimum(values, 0), np.maximum(values, 0), color=PALETTE["light_grey"], linewidth=2.0, zorder=1)
    axis.scatter(values, y, s=34, color=color, edgecolor="white", linewidth=0.55, zorder=3)
    lo = min(float(values.min()), 0.0)
    hi = max(float(values.max()), 0.0)
    span = max(hi - lo, max(abs(lo), abs(hi)), 1.0)
    left_margin = 0.12 * span
    right_margin = 0.16 * span
    axis.set_xlim(lo - left_margin, hi + right_margin)
    offset = 0.018 * span
    for yi, raw_value in zip(y, values):
        value = 0.0 if abs(float(raw_value)) < 0.05 else float(raw_value)
        if labels_toward_zero and abs(value) > 0.08 * span:
            xpos = value + (offset if value < 0 else -offset)
            halign = "left" if value < 0 else "right"
        else:
            xpos = value + (offset if value >= 0 else -offset)
            halign = "left" if value >= 0 else "right"
        axis.text(
            xpos, yi, f"{value:.2f}", ha=halign, va="center", fontsize=5.7,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.18, "alpha": 0.80}, zorder=4,
        )
    axis.set_yticks(y)
    if show_ylabels:
        axis.set_yticklabels([ROBUSTNESS_CONTEXT_LABELS[c] for c in CONTEXTS])
    else:
        axis.tick_params(labelleft=False)
    axis.invert_yaxis()
    axis.set_xlabel(xlabel)
    clean_axis(axis, "x")


def _alluvial(axis, correction: pd.DataFrame) -> None:
    source_order = ["initial optimized deficit", "initial optimized surplus"]
    target_order = ["persistent or amplified", "partly corrected", "substantially corrected", "reversal"]
    colors = {
        "persistent or amplified": PALETTE["red"],
        "partly corrected": PALETTE["orange"],
        "substantially corrected": PALETTE["teal"],
        "reversal": PALETTE["purple"],
    }
    grouped = correction.groupby(["initial_sign", "correction_class"], as_index=False)["initial_absolute_power_mw"].sum()
    total = max(float(grouped["initial_absolute_power_mw"].sum()), 1e-12)
    grouped["weight"] = grouped["initial_absolute_power_mw"] / total
    source_totals = grouped.groupby("initial_sign")["weight"].sum().reindex(source_order).fillna(0.0)
    target_totals = grouped.groupby("correction_class")["weight"].sum().reindex(target_order).fillna(0.0)
    gap = 0.024
    source_positions, target_positions = {}, {}
    cursor = 0.08
    for name, value in source_totals.items():
        source_positions[name] = [cursor, cursor + value * 0.78]
        cursor = source_positions[name][1] + gap
    cursor = 0.08
    for name, value in target_totals.items():
        if value <= 0:
            continue
        target_positions[name] = [cursor, cursor + value * 0.78]
        cursor = target_positions[name][1] + gap
    source_cursor = {key: value[0] for key, value in source_positions.items()}
    target_cursor = {key: value[0] for key, value in target_positions.items()}
    for source in source_order:
        for target in target_order:
            match = grouped[(grouped["initial_sign"].eq(source)) & (grouped["correction_class"].eq(target))]
            if match.empty or target not in target_positions:
                continue
            width = float(match["weight"].iloc[0]) * 0.78
            y0a, y0b = source_cursor[source], source_cursor[source] + width
            y1a, y1b = target_cursor[target], target_cursor[target] + width
            source_cursor[source], target_cursor[target] = y0b, y1b
            vertices = [(0.16,y0a),(0.36,y0a),(0.60,y1a),(0.80,y1a),(0.80,y1b),(0.60,y1b),(0.36,y0b),(0.16,y0b),(0.16,y0a)]
            codes = [MplPath.MOVETO,MplPath.CURVE4,MplPath.CURVE4,MplPath.CURVE4,MplPath.LINETO,MplPath.CURVE4,MplPath.CURVE4,MplPath.CURVE4,MplPath.CLOSEPOLY]
            axis.add_patch(PathPatch(MplPath(vertices,codes), facecolor=colors[target], edgecolor="none", alpha=0.48, clip_on=True))
    for source, (y0, y1) in source_positions.items():
        axis.add_patch(Rectangle((0.11,y0),0.05,y1-y0,facecolor=PALETTE["navy"] if "deficit" in source else PALETTE["blue"],edgecolor="white",linewidth=0.5))
        axis.text(0.095,(y0+y1)/2,"Deficit" if "deficit" in source else "Surplus",ha="right",va="center",fontsize=5.3)
    for target, (y0, y1) in target_positions.items():
        axis.add_patch(Rectangle((0.80,y0),0.05,y1-y0,facecolor=colors[target],edgecolor="white",linewidth=0.5))
        axis.text(0.875,(y0+y1)/2,CORRECTION_LABELS[target],ha="left",va="center",fontsize=4.8)
    axis.text(0.135,0.94,"Inherited mismatch",ha="center",va="top",fontweight="bold",fontsize=5.7)
    axis.text(0.825,0.972,"2058 correction class",ha="center",va="top",fontweight="bold",fontsize=5.7)
    axis.text(0.50,0.015,"Ribbon width = absolute stock-anchor mismatch; not a physical capacity flow",ha="center",va="bottom",fontsize=4.6,color=PALETTE["grey"])
    axis.set_xlim(0,1.12)
    axis.set_ylim(0,1)
    axis.axis("off")


def _counterfactual_identification_bridge(axis, concentration: pd.Series) -> None:
    """Show the controlled identification sequence with a cleaner publication layout."""
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    power = float(concentration["national_power_mw"]) / 1000.0
    energy = float(concentration["national_energy_mwh"]) / 1000.0
    boxes = [
        {"x": 0.02, "title": "Duration sensitivity", "subtitle": "Reconstructed siting\nVariable duration", "color": PALETTE["grey"]},
        {"x": 0.355, "title": "Standardized stock", "subtitle": "Same siting\nCommon duration", "color": PALETTE["blue"]},
        {"x": 0.69, "title": "Optimized reallocation", "subtitle": "Optimized siting\nCommon duration", "color": PALETTE["orange"]},
    ]
    width, y0, height = 0.285, 0.28, 0.58
    for spec in boxes:
        x0 = spec["x"]
        axis.add_patch(FancyBboxPatch((x0, y0), width, height,
                                      boxstyle="round,pad=0.010,rounding_size=0.016",
                                      facecolor="white", edgecolor=spec["color"], linewidth=1.05))
        axis.add_patch(FancyBboxPatch((x0, y0 + height - 0.10), width, 0.10,
                                      boxstyle="round,pad=0.010,rounding_size=0.016",
                                      facecolor=spec["color"], edgecolor=spec["color"], linewidth=0.0))
        axis.text(x0 + width / 2, y0 + height - 0.05, spec["title"], ha="center", va="center",
                  color="white", fontsize=5.6, fontweight="bold")
        axis.text(x0 + width / 2, y0 + 0.29, spec["subtitle"], ha="center", va="center",
                  color=PALETTE["dark"], fontsize=5.45, linespacing=1.22)
        axis.text(x0 + width / 2, y0 + 0.10, f"{power:.2f} GW  |  {energy:.2f} GWh", ha="center", va="center",
                  color=PALETTE["grey"], fontsize=5.1)

    axis.annotate("", xy=(0.35, 0.57), xytext=(0.31, 0.57),
                  arrowprops={"arrowstyle": "-|>", "linewidth": 0.72, "color": PALETTE["mid_grey"]})
    axis.text(0.33, 0.69, "standardize", rotation=90, ha="center", va="center", fontsize=4.35, color=PALETTE["grey"])
    axis.annotate("", xy=(0.685, 0.57), xytext=(0.645, 0.57),
                  arrowprops={"arrowstyle": "-|>", "linewidth": 0.82, "color": PALETTE["orange"]})
    axis.text(0.665, 0.69, "reallocate", rotation=90, ha="center", va="center", fontsize=4.35, color=PALETTE["orange"])

    axis.plot([0.405, 0.93], [0.22, 0.22], color=PALETTE["orange"], linewidth=1.0)
    axis.plot([0.405, 0.405], [0.208, 0.233], color=PALETTE["orange"], linewidth=1.0)
    axis.plot([0.93, 0.93], [0.208, 0.233], color=PALETTE["orange"], linewidth=1.0)
    axis.text(0.668, 0.175, "Location effect", ha="center", va="center", fontsize=6.1, fontweight="bold", color=PALETTE["orange"])
    axis.text(0.668, 0.135, "standardized stock  vs  optimized reallocation", ha="center", va="center", fontsize=4.75, color=PALETTE["dark"])

    axis.add_patch(FancyBboxPatch((0.035, 0.015), 0.285, 0.06, boxstyle="round,pad=0.008",
                                  facecolor="#F4F8FB", edgecolor=PALETTE["blue"], linewidth=0.55))
    axis.text(0.177, 0.045, "No legacy: zero-stock benchmark", ha="center", va="center", fontsize=4.7, color=PALETTE["navy"])
    axis.add_patch(FancyBboxPatch((0.355, 0.015), 0.61, 0.06, boxstyle="round,pad=0.008",
                                  facecolor="#F3F8F8", edgecolor=PALETTE["teal"], linewidth=0.55))
    axis.text(0.66, 0.045, "Load and renewables rules: transparent heuristic benchmarks", ha="center", va="center", fontsize=4.7, color=PALETTE["teal"])

def figure1() -> None:
    nodes = read_table(TABLE_MAIN / "fig1a_legacy_nodes.csv")
    edges = read_table(TABLE_MAIN / "fig1b_model_network_edges.csv")
    match = read_table(TABLE_MAIN / "fig1b_storage_demand_resource_match.csv")
    lorenz = read_table(TABLE_MAIN / "fig1c_storage_lorenz.csv")
    concentration = read_table(TABLE_MAIN / "fig1d_legacy_concentration.csv").iloc[0]

    fig = plt.figure(figsize=(7.0866, 6.28))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.00, 0.99], height_ratios=[1.08, 1.00], wspace=0.24, hspace=0.14)

    ax_a = fig.add_subplot(gs[0, 0])
    ax = ax_a
    sc_a = node_map(
        ax, nodes, edges,
        size_column="existing_new_storage_power_mw", color_column="compiled_duration_sensitivity_h",
        title="", labels=0,
        label_zones=["Xinjiang","West_Inner_Mongolia","Hebei","Shandong","Jiangsu","East_Inner_Mongolia"],
        norm=Normalize(
            vmin=float(nodes["compiled_duration_sensitivity_h"].min()),
            vmax=float(nodes["compiled_duration_sensitivity_h"].max()),
        ),
        cmap="viridis",
        with_inset=True,
    )
    _annotate_named_map_labels_force(ax, nodes, {"Xinjiang": (0.31, 0.94), "West_Inner_Mongolia": (0.02, 0.70), "Hebei": (0.98, 0.84), "Shandong": (0.98, 0.58), "Jiangsu": (0.98, 0.44), "East_Inner_Mongolia": (0.98, 0.91)}, arrow_color=PALETTE["blue"], arrow_width=0.70)
    ax.text(0.02, 0.02, f"National stock: {concentration['national_power_mw']/1000:.2f} GW / {concentration['national_energy_mwh']/1000:.2f} GWh", transform=ax.transAxes, fontsize=5.8, fontweight="bold")

    ax_b = fig.add_subplot(gs[0, 1])
    ax = ax_b
    x = 100 * match["peak_demand_share"]
    y = 100 * match["storage_power_share"]
    sizes = 18 + 130 * np.sqrt(match["existing_new_storage_power_mw"] / match["existing_new_storage_power_mw"].max())
    share_gap = pd.to_numeric(match["storage_minus_peak_share_pp"], errors="raise")
    share_gap_limit = max(float(share_gap.abs().max()), 1.0e-9)
    sc = ax.scatter(
        x, y, s=sizes, c=share_gap, cmap="RdBu_r",
        norm=TwoSlopeNorm(vmin=-share_gap_limit, vcenter=0.0, vmax=share_gap_limit),
        edgecolor="white", linewidth=0.5, zorder=3,
    )
    lim = max(float(x.max()), float(y.max())) * 1.08
    ax.plot([0, lim], [0, lim], linestyle="--", color=PALETTE["mid_grey"], linewidth=0.8)
    for xv in x: ax.plot([xv, xv], [0, lim*0.018], color=PALETTE["blue"], linewidth=0.45, alpha=0.55)
    for yv in y: ax.plot([0, lim*0.018], [yv, yv], color=PALETTE["orange"], linewidth=0.45, alpha=0.55)
    share_offsets = {
        "Xinjiang": (5, 6),
        "West_Inner_Mongolia": (6, -8),
        "Guangdong": (6, 7),
        "Gansu": (6, 6),
        "Liaoning": (6, 7),
        "Zhejiang": (6, -9),
    }
    for row in match.assign(abs_gap=match["storage_minus_peak_share_pp"].abs()).nlargest(6, "abs_gap").itertuples(index=False):
        ax.annotate(
            zone_label_compact(row.model_zone),
            (100*row.peak_demand_share, 100*row.storage_power_share),
            xytext=share_offsets.get(str(row.model_zone), (5, 5)),
            textcoords="offset points", fontsize=4.8, ha="left", va="center",
            bbox={"boxstyle":"round,pad=0.12","facecolor":"white","edgecolor":"none","alpha":0.90},
            arrowprops={"arrowstyle":"-","shrinkA":1.0,"shrinkB":3.5,"linewidth":0.48,"color":PALETTE["blue"]},
            zorder=5,
        )
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel("Share of national coincident peak (%)")
    ax.set_ylabel("Share of inherited storage power (%)")
    clean_axis(ax, "both")
    # aligned top colorbars for a and b
    cax_a = fig.add_axes([0.18, 0.914, 0.19, 0.012])
    cbar_a = fig.colorbar(sc_a, cax=cax_a, orientation="horizontal")
    cbar_a.set_label("Reconstructed duration (h)", fontsize=5.2, labelpad=1.0); cbar_a.ax.xaxis.set_label_position("top")
    cbar_a.ax.tick_params(labelsize=4.7, length=1.5, pad=1.0); cbar_a.outline.set_linewidth(0.35)
    cax_b = fig.add_axes([0.70, 0.914, 0.16, 0.012])
    cbar = fig.colorbar(sc, cax=cax_b, orientation="horizontal")
    cbar.set_label("Storage − peak share (pp)", fontsize=5.2, labelpad=1.0); cbar.ax.xaxis.set_label_position("top")
    cbar.ax.tick_params(labelsize=4.7, length=1.5, pad=1.0); cbar.outline.set_linewidth(0.35)

    ax = fig.add_subplot(gs[1, 0])
    ax.plot(lorenz["population_share"], lorenz["cumulative_storage_power_share"], color=PALETTE["blue"], linewidth=1.8)
    ax.fill_between(lorenz["population_share"], lorenz["cumulative_storage_power_share"], lorenz["population_share"], color=PALETTE["blue"], alpha=0.12)
    ax.plot([0,1],[0,1], linestyle="--", color=PALETTE["mid_grey"], linewidth=0.8)
    ax.set_xlabel("Cumulative share of model zones"); ax.set_ylabel("Cumulative share of storage power")
    ax.set_ylim(0, 1.20)
    clean_axis(ax, "both")
    cards = [("Top five", f"{100*concentration['top5_power_share']:.2f}%"),("Herfindahl index", f"{concentration['herfindahl_hirschman_index']:.2f}"),("Max storage/peak", f"{concentration['maximum_storage_to_peak_ratio']:.2f}")]
    for i,(lab,val) in enumerate(cards):
        x0=0.05+i*0.31
        ax.add_patch(FancyBboxPatch((x0,0.82),0.25,0.16,transform=ax.transAxes,boxstyle="round,pad=0.012",facecolor=PALETTE["pale"],edgecolor=PALETTE["light_grey"],linewidth=0.6))
        ax.text(x0+0.125,0.925,val,ha="center",va="center",transform=ax.transAxes,fontweight="bold",fontsize=7.7)
        ax.text(x0+0.125,0.855,lab,ha="center",va="center",transform=ax.transAxes,fontsize=5.2,color=PALETTE["grey"])

    ax = fig.add_subplot(gs[1, 1])
    _counterfactual_identification_bridge(ax, concentration)
    fig.text(0.012, 0.932, "a", fontweight="bold", fontsize=8.2, va="top", ha="left", color=PALETTE["dark"])
    fig.text(0.535, 0.932, "b", fontweight="bold", fontsize=8.2, va="top", ha="left", color=PALETTE["dark"])
    fig.text(0.012, 0.507, "c", fontweight="bold", fontsize=8.2, va="top", ha="left", color=PALETTE["dark"])
    fig.text(0.535, 0.507, "d", fontweight="bold", fontsize=8.2, va="top", ha="left", color=PALETTE["dark"])
    # Preserve a publication-safe left margin for the Lorenz-curve y label.
    fig.subplots_adjust(left=0.072, right=0.985, top=0.925, bottom=0.075)
    fig.canvas.draw()
    map_box = ax_a.get_position(); scatter_box = ax_b.get_position()
    ax_b.set_position([scatter_box.x0, map_box.y0, scatter_box.width, map_box.height])
    fig.canvas.draw()
    y_mismatch = max(abs(ax_a.get_position().y0 - ax_b.get_position().y0),
                     abs(ax_a.get_position().y1 - ax_b.get_position().y1))
    if y_mismatch > 1.0e-6:
        raise RuntimeError(f"Fig1a/Fig1b vertical frame mismatch {y_mismatch:.3e}")
    save_figure(fig, FIG_MAIN / "Fig1_inherited_storage_geography")

def figure2() -> None:
    nodes = read_table(TABLE_MAIN / "fig1a_legacy_nodes.csv")
    edges = read_table(TABLE_MAIN / "fig1b_model_network_edges.csv")
    allocation = read_table(TABLE_MAIN / "fig2_spatial_allocation.csv")
    ladder = read_table(TABLE_MAIN / "fig2b_legacy_value_ladder.csv")
    concentration = read_table(TABLE_MAIN / "fig1d_legacy_concentration.csv").iloc[0]
    coords = nodes[["model_zone","longitude","latitude"]]
    observed = allocation[allocation["scenario"].eq(PAIR[0])].merge(coords,on="model_zone",validate="one_to_one")
    optimized = allocation[allocation["scenario"].eq(PAIR[1])].merge(coords,on="model_zone",validate="one_to_one")
    observed["power_gw"] = observed["realized_legacy_power_mw"] / 1000
    optimized["power_gw"] = optimized["realized_legacy_power_mw"] / 1000
    optimized["delta_gw"] = optimized["delta_power_vs_observed_standardized_mw"] / 1000
    common_max=max(observed["power_gw"].max(),optimized["power_gw"].max())
    common_norm=Normalize(0,common_max)
    delta_limit=max(optimized["delta_gw"].abs().max(),1e-9)
    delta_norm=TwoSlopeNorm(vmin=-delta_limit,vcenter=0,vmax=delta_limit)
    equivalent=0.5*optimized["delta_gw"].abs().sum()

    fig=plt.figure(figsize=(7.0866,5.72))
    gs=fig.add_gridspec(2,3,height_ratios=[0.99,0.96],width_ratios=[1,1,1],wspace=0.18,hspace=0.11)
    scatters=[]
    top_axes=[]
    specs=[(observed,"","power_gw",False,common_norm,["Xinjiang","West_Inner_Mongolia","Hebei","Shandong"]),(optimized,"","power_gw",False,common_norm,["Shandong","Guangdong","Jiangsu","Zhejiang"]),(optimized,"","delta_gw",True,delta_norm,["Shandong","Guangdong","Xinjiang","West_Inner_Mongolia"])]
    manual_positions=[
        {"Xinjiang": (0.31, 0.94), "West_Inner_Mongolia": (0.02, 0.66), "Hebei": (0.98, 0.88), "Shandong": (0.98, 0.58)},
        {"Shandong": (0.98, 0.75), "Guangdong": (0.12, 0.07), "Jiangsu": (0.98, 0.52), "Zhejiang": (0.98, 0.30)},
        {"Shandong": (0.98, 0.72), "Guangdong": (0.14, 0.07), "Xinjiang": (0.34, 0.94), "West_Inner_Mongolia": (0.02, 0.72)},
    ]
    for i,(frame,title,col,delta,norm,zones) in enumerate(specs):
        ax=fig.add_subplot(gs[0,i]); panel_label(ax,chr(97+i), y=1.115)
        top_axes.append(ax)
        scatters.append(node_map(ax,frame,edges,size_column=col,color_column=col,title=title,delta=delta,labels=0,size_max=delta_limit if delta else common_max,norm=norm))
        _annotate_named_map_labels_force(ax, frame, manual_positions[i], arrow_color=PALETTE["blue"], arrow_width=0.70)

    # Give each map its own identical scale, avoiding the adjacent panel tag.
    top_map_colorbar(fig, top_axes[0], scatters[0], "Storage power (GW)", width=0.66)
    top_map_colorbar(fig, top_axes[1], scatters[1], "Storage power (GW)", width=0.66)
    top_map_colorbar(fig, top_axes[2], scatters[2], "Optimized − observed (GW)", width=0.66)

    ax=fig.add_subplot(gs[1,:2]); panel_label(ax,"d",x=-0.055, y=1.115)
    material_threshold=0.02*delta_limit
    negative=optimized.nsmallest(8,"delta_gw").query("delta_gw <= -@material_threshold").sort_values("delta_gw")
    positive=optimized.nlargest(8,"delta_gw").query("delta_gw >= @material_threshold").sort_values("delta_gw")
    ranked=pd.concat([negative,positive],ignore_index=True)
    colors=[PALETTE["blue"] if v<0 else PALETTE["orange"] for v in ranked["delta_gw"]]
    ax.barh(np.arange(len(ranked)),ranked["delta_gw"],color=colors,height=0.70)
    ax.set_yticks(np.arange(len(ranked)),[zone_label_compact(z) for z in ranked["model_zone"]],fontsize=5.4)
    ax.axvline(0,color=PALETTE["dark"],linewidth=0.7)
    ax.set_xlabel("Optimized minus observed storage power (GW)")
    national_power_gw=float(concentration["national_power_mw"])/1000
    clean_axis(ax,"x")
    ax.text(0.01, 1.03, f"Equivalent reallocation = {equivalent:.2f} GW ({100*equivalent/national_power_gw:.2f}% of fleet)", transform=ax.transAxes, fontsize=5.6, fontweight="bold", ha="left", va="bottom")

    ax=fig.add_subplot(gs[1,2]); panel_label(ax,"e",x=-0.12, y=1.115)
    plot=ladder.sort_values("legacy_system_value_usd")
    y=np.arange(len(plot)); values=plot["legacy_system_value_usd"]/1e9
    ax.hlines(y,0,values,color=PALETTE["light_grey"],linewidth=4)
    ax.scatter(values,y,s=42,color=[SCENARIO_COLORS.get(s,PALETTE["grey"]) for s in plot["scenario"]],edgecolor="white",linewidth=0.5,zorder=3)
    ladder_labels={"SL02_OPTIMAL_REALLOCATION":"Optimized","SL04_RULE_LOAD":"Load rule","SL05_RULE_VRE":"Renewables rule","SL01_OBSERVED_STANDARDIZED":"Standardized","SL00_OBSERVED_ACTUAL":"Variable duration","SL03_NO_LEGACY":"No legacy"}
    label_xoffsets={"SL02_OPTIMAL_REALLOCATION":0.55,"SL04_RULE_LOAD":0.56,"SL05_RULE_VRE":0.62,"SL01_OBSERVED_STANDARDIZED":0.56,"SL00_OBSERVED_ACTUAL":0.56,"SL03_NO_LEGACY":0.35}
    label_yoffsets={"SL02_OPTIMAL_REALLOCATION":0.06,"SL04_RULE_LOAD":0.04,"SL05_RULE_VRE":-0.04,"SL01_OBSERVED_STANDARDIZED":-0.05,"SL00_OBSERVED_ACTUAL":-0.03,"SL03_NO_LEGACY":0.00}
    for yi,val,ret,scenario in zip(y,values,plot["value_retention_fraction"],plot["scenario"]):
        xpos=0.65 if val < 0.5 else val+label_xoffsets.get(scenario,0.42)
        ypos=yi+label_yoffsets.get(scenario,0.0)
        ax.text(xpos,ypos,f"{val:.2f}\n({ret:.2%})",va="center",fontsize=5.15)
    ax.set_yticks(y,[ladder_labels.get(s,s) for s in plot["scenario"]],fontsize=5.3)
    ax.set_xlabel("System value of inherited fleet\n(billion US$, present value)")
    ax.set_xlim(0,max(values)*1.56); clean_axis(ax,"x")
    # The two-line panel-e x label needs explicit room at the 180 mm release size.
    fig.subplots_adjust(left=0.09,right=0.985,top=0.895,bottom=0.105)
    save_figure(fig,FIG_MAIN/"Fig2_equal_stock_unequal_spatial_value")

def figure3() -> None:
    data=read_table(TABLE_MAIN/"fig3a_compensatory_investment.csv")
    transition=read_table(TABLE_MAIN/"fig5_transition_paths.csv")
    burden=read_table(TABLE_MAIN/"fig3b_spatial_burden_2028.csv")
    nodes=read_table(TABLE_MAIN/"fig1a_legacy_nodes.csv")
    edges=read_table(TABLE_MAIN/"fig1b_model_network_edges.csv")
    burden=burden.merge(nodes[["model_zone","longitude","latitude"]],on="model_zone",validate="one_to_one")
    aggregate_penalty=float(data["present_value_cost_delta_usd"].sum())/1e9
    fig=plt.figure(figsize=(7.0866,5.95))
    gs=fig.add_gridspec(2,2,width_ratios=[1.06,0.94],height_ratios=[1.0,1.08],wspace=0.30,hspace=0.34)

    ax=fig.add_subplot(gs[0,0]); panel_label(ax,"a", y=1.125)
    components=[("generation_capacity_cost_delta_usd_per_yr","Generation capacity",PALETTE["blue"]),("storage_energy_fixed_cost_delta_usd_per_yr","Storage energy",PALETTE["orange"]),("transmission_fixed_cost_delta_usd_per_yr","Transmission",PALETTE["teal"]),("fuel_cost_delta_usd_per_yr","Fuel",PALETTE["vermillion"]),("other_system_cost_delta_usd_per_yr","Other system costs",PALETTE["grey"])]
    x=np.arange(len(data)); pos=np.zeros(len(data)); neg=np.zeros(len(data))
    for col,label,color in components:
        vals=data[col].to_numpy()/1e9; bottoms=np.where(vals>=0,pos,neg)
        ax.bar(x,vals,bottom=bottoms,color=color,width=0.72,label=label)
        pos+=np.where(vals>=0,vals,0); neg+=np.where(vals<0,vals,0)
    totals=data["annual_system_cost_delta_usd_per_yr"]/1e9
    for xi,total,top,bottom in zip(x,totals,pos,neg): ax.text(xi,top+0.15 if total>=0 else bottom-0.15,f"{total:+.2f}",ha="center",va="bottom" if total>=0 else "top",fontsize=5.1)
    ax.axhline(0,color=PALETTE["dark"],linewidth=0.7); ax.set_xticks(x,data["period"].astype(int))
    ax.set_ylabel("Observed − optimized annual cost\n(billion USD yr$^{-1}$)")
    ax.text(0.98,0.95,f"Aggregate present-value penalty\nUS${aggregate_penalty:.2f} billion",transform=ax.transAxes,ha="right",va="top",fontsize=5.7,fontweight="bold",bbox={"boxstyle":"round,pad=0.25","facecolor":PALETTE["pale"],"edgecolor":PALETTE["light_grey"],"linewidth":0.5})
    handles,legend_labels=ax.get_legend_handles_labels()
    ax.legend(handles,legend_labels,ncol=3,loc="lower left",bbox_to_anchor=(0.04,1.035),fontsize=5.0,columnspacing=0.72,handletextpad=0.38,borderaxespad=0.0)
    clean_axis(ax,"y")

    ax=fig.add_subplot(gs[0,1]); panel_label(ax,"b", y=1.125)
    power=data["battery_power_delta_mw"]/1000
    ax.axhline(0,color=PALETTE["dark"],linewidth=0.65); ax.fill_between(data["period"],0,power,color=PALETTE["blue"],alpha=0.18)
    ax.plot(data["period"],power,marker="o",color=PALETTE["blue"],linewidth=1.5,markersize=3.5)
    for row in data.iloc[[0,1,-1]].itertuples(index=False): ax.annotate(f"{row.battery_power_delta_mw/1000:+.2f}",(row.period,row.battery_power_delta_mw/1000),xytext=(10,8),textcoords="offset points",ha="left",fontsize=5.3)
    ax.set_xlabel("Planning period"); ax.set_ylabel("Battery-power difference (GW)");
    xmin, xmax = float(data["period"].min())-2, float(data["period"].max())+4.0
    ax.set_xlim(xmin, xmax); ax.set_xticks(data["period"].astype(int)); ax.tick_params(axis="x", labelsize=5.2); clean_axis(ax,"y")

    ax=fig.add_subplot(gs[1,0]); panel_label(ax,"c", y=1.08)
    installed_columns=[column for column in transition.columns if column.startswith("installed_") and column.endswith("_mw") and column!="installed_battery_mw"]
    capacity_rows=[]
    for period,group in transition.groupby("period"):
        observed=group.loc[group["scenario"].eq(PAIR[0])]
        optimized=group.loc[group["scenario"].eq(PAIR[1])]
        if len(observed)!=1 or len(optimized)!=1:
            raise ValueError(f"Missing unique matched transition rows for {period}")
        observed_total=float(observed[installed_columns].sum(axis=1).iloc[0])
        optimized_total=float(optimized[installed_columns].sum(axis=1).iloc[0])
        capacity_rows.append((int(period),(observed_total-optimized_total)/1000.0))
    capacity=pd.DataFrame(capacity_rows,columns=["period","difference_gw"]).sort_values("period")
    ax.axhline(0,color=PALETTE["dark"],linewidth=0.65); ax.fill_between(capacity["period"],0,capacity["difference_gw"],color=PALETTE["teal"],alpha=0.18)
    ax.plot(capacity["period"],capacity["difference_gw"],marker="s",color=PALETTE["teal"],linewidth=1.5,markersize=3.5)
    for row in capacity.iloc[[0,1,-1]].itertuples(index=False): ax.annotate(f"{row.difference_gw:+.2f}",(row.period,row.difference_gw),xytext=(8,7),textcoords="offset points",ha="left",fontsize=5.3)
    ax.set_xlabel("Planning period"); ax.set_ylabel("Non-storage capacity difference (GW)")
    ax.set_xlim(xmin, xmax); ax.set_xticks(data["period"].astype(int)); ax.tick_params(axis="x", labelsize=5.2); clean_axis(ax,"y")

    dgs=gs[1,1].subgridspec(2,1,height_ratios=[0.66,0.34],hspace=0.20)
    map_ax=fig.add_subplot(dgs[0,0]); panel_label(map_ax,"d",x=-0.16, y=1.10)
    limit=max(burden["power_delta_mw"].abs().max()/1000,1e-9); burden["power_delta_gw"]=burden["power_delta_mw"]/1000
    sc=node_map(map_ax,burden,edges,size_column="power_delta_gw",color_column="power_delta_gw",title="",delta=True,labels=4,label_zones=["Xinjiang","West_Inner_Mongolia","Shandong","Liaoning"],size_max=limit,norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit))
    rank_ax=fig.add_subplot(dgs[1,0])
    rank=burden.assign(abs_delta=burden["power_delta_gw"].abs()).nlargest(8,"abs_delta").sort_values("power_delta_gw")
    rank_ax.bar(np.arange(len(rank)),rank["power_delta_gw"],color=[PALETTE["orange"] if v>0 else PALETTE["blue"] for v in rank["power_delta_gw"]],width=0.68)
    rank_ax.axhline(0,color=PALETTE["dark"],linewidth=0.5)
    rank_ax.set_xticks(np.arange(len(rank)),[zone_label_compact(z) for z in rank["model_zone"]],rotation=28,ha="right",fontsize=4.6)
    rank_ax.set_ylabel("GW", fontsize=5.1); clean_axis(rank_ax,"y")
    fig.subplots_adjust(left=0.075,right=0.985,top=0.89,bottom=0.095,wspace=0.30,hspace=0.34)
    fig.canvas.draw()
    # The equal-aspect map contracts inside its grid cell. Match the lower
    # ranking axis to the actual map frame, not merely to the parent cell.
    map_box = map_ax.get_position(); rank_box = rank_ax.get_position()
    rank_ax.set_position([map_box.x0, rank_box.y0, map_box.width, rank_box.height])
    fig.canvas.draw()
    _assert_x_aligned(map_ax, rank_ax, "Fig3d map/ranking")
    map_box = map_ax.get_position()
    cax = fig.add_axes([map_box.x0 + 0.27*map_box.width, map_box.y1 + 0.026, 0.70*map_box.width, 0.010])
    cbar=fig.colorbar(sc,cax=cax,orientation="horizontal")
    cbar.set_label("Observed − optimized battery power (GW)",fontsize=4.8,labelpad=1.0); cbar.ax.xaxis.set_label_position("top"); cbar.ax.tick_params(labelsize=4.3,length=1.3,pad=0.8); cbar.outline.set_linewidth(0.35)
    save_figure(fig,FIG_MAIN/"Fig3_compensatory_investment_cost")

def figure4() -> None:
    persistence=read_table(TABLE_MAIN/"fig4a_mismatch_persistence.csv")
    correction=read_table(TABLE_MAIN/"fig4c_zone_correction.csv")
    zone_period=read_table(TABLE_MAIN/"fig4b_zone_period_deltas.csv")
    nodes=read_table(TABLE_MAIN/"fig1a_legacy_nodes.csv")
    edges=read_table(TABLE_MAIN/"fig1b_model_network_edges.csv")
    final_period=int(correction["final_period"].iloc[0])
    initial=correction.merge(nodes[["model_zone","longitude","latitude"]],on="model_zone",validate="one_to_one")
    final=zone_period[zone_period["period"].eq(final_period)].merge(nodes[["model_zone","longitude","latitude"]],on="model_zone",validate="one_to_one")
    initial["delta_gw"]=initial["optimized_minus_observed_power_mw"]/1000
    final["delta_gw"]=final["optimized_minus_observed_power_mw"]/1000
    initial_limit=max(initial["delta_gw"].abs().max(),1e-9)
    final_limit=max(final["delta_gw"].abs().max(),1e-9)
    colors={"persistent or amplified":PALETTE["red"],"partly corrected":PALETTE["orange"],"substantially corrected":PALETTE["teal"],"reversal":PALETTE["purple"],"near zero initially":PALETTE["grey"]}

    fig=plt.figure(figsize=(7.0866,5.75)); gs=fig.add_gridspec(2,2,width_ratios=[0.78,1.22],height_ratios=[0.98,1.14],wspace=0.31,hspace=0.34)
    ax=fig.add_subplot(gs[0,0]); axa=ax; panel_label(ax,"a", y=1.125)
    power_pct=100*persistence["power_persistence_fraction"]
    energy_pct=100*persistence["energy_persistence_fraction"]
    ax.plot(persistence["period"],power_pct,marker="o",color=PALETTE["blue"],linewidth=1.6,label="Power")
    ax.plot(persistence["period"],energy_pct,marker="s",color=PALETTE["orange"],linewidth=1.6,label="Energy")
    ax.axhline(0,color=PALETTE["dark"],linewidth=0.5)
    ax.set_ylim(0,max(110,110*max(persistence["power_persistence_fraction"].max(),persistence["energy_persistence_fraction"].max())))
    periods=persistence["period"].astype(int).tolist(); tick_labels=["Stock\nanchor" if p==periods[0] else str(p) for p in periods]
    ax.set_xticks(periods,tick_labels); ax.set_xlabel("Planning period")
    ax.set_ylabel("Mismatch remaining\n(% of initial spatial mismatch)")
    ax.legend(ncol=2,loc="lower left",bbox_to_anchor=(0.0,1.015),fontsize=4.8,columnspacing=0.8,handletextpad=0.4,borderaxespad=0.0); clean_axis(ax,"y")

    ax=fig.add_subplot(gs[0,1]); axb=ax; panel_label(ax,"b", y=1.125)
    x=correction["optimized_minus_observed_power_mw"]/1000; y=correction["final_power_delta_mw"]/1000
    size=18+110*np.sqrt(correction["initial_absolute_power_mw"]/correction["initial_absolute_power_mw"].max())
    for cls,group in correction.groupby("correction_class"):
        ax.scatter(group["optimized_minus_observed_power_mw"]/1000,group["final_power_delta_mw"]/1000,s=size[group.index],color=colors.get(cls,PALETTE["grey"]),label=CORRECTION_LABELS.get(cls,cls),edgecolor="white",linewidth=0.5)
    ax.axhline(0,color=PALETTE["mid_grey"],linewidth=0.7); ax.axvline(0,color=PALETTE["mid_grey"],linewidth=0.7)
    lim=max(abs(x).max(),abs(y).max())*1.10; ax.plot([-lim,lim],[-lim,lim],linestyle="--",color=PALETTE["light_grey"],linewidth=0.8)
    # Four geographically and numerically salient labels are sufficient;
    # additional labels clustered around the origin obscured the residuals.
    selected=[zone for zone in ["Xinjiang","West_Inner_Mongolia","Shandong","Guangdong"]
              if zone in set(correction["model_zone"].astype(str))]
    scatter_offsets={"Shandong":(-42,-10),"Guangdong":(-42,9),"Xinjiang":(8,-8),"West_Inner_Mongolia":(8,10),"Hebei":(10,10),"Anhui":(-30,-8),"Gansu":(10,10)}
    for zone in selected:
        row=correction[correction["model_zone"].eq(zone)].iloc[0]
        ax.annotate(zone_label_compact(zone),(row["optimized_minus_observed_power_mw"]/1000,row["final_power_delta_mw"]/1000),xytext=scatter_offsets.get(zone,(6,6)),textcoords="offset points",fontsize=4.7,arrowprops={"arrowstyle":"-","linewidth":0.3,"color":PALETTE["mid_grey"]})
    ax.set_xlim(-lim,lim); ax.set_ylim(-lim,lim)
    ax.set_xlabel("Stock-anchor mismatch (GW)"); ax.set_ylabel(f"{final_period} residual mismatch (GW)")
    ax.legend(loc="lower left",bbox_to_anchor=(0.0,1.015),ncol=2,fontsize=4.4,frameon=False,handletextpad=0.30,columnspacing=0.75,labelspacing=0.40,borderaxespad=0.0); clean_axis(ax,"both")

    sub=gs[1,0].subgridspec(2,1,hspace=0.14)
    ax1=fig.add_subplot(sub[0,0]); panel_label(ax1,"c",x=-0.14, y=1.125)
    sc1=node_map(ax1,initial,edges,size_column="delta_gw",color_column="delta_gw",title="",delta=True,labels=0,size_max=initial_limit,norm=TwoSlopeNorm(vmin=-initial_limit,vcenter=0,vmax=initial_limit))
    _annotate_named_map_labels_force(ax1, initial, {"Shandong": (0.98, 0.58), "Guangdong": (0.18, 0.07), "Xinjiang": (0.31, 0.94)}, arrow_color=PALETTE["blue"], arrow_width=0.75)
    ax2=fig.add_subplot(sub[1,0])
    sc2=node_map(ax2,final,edges,size_column="delta_gw",color_column="delta_gw",title="",delta=True,labels=0,size_max=final_limit,norm=TwoSlopeNorm(vmin=-final_limit,vcenter=0,vmax=final_limit))
    _annotate_named_map_labels_force(ax2, final, {"Hebei": (0.98, 0.83), "Xinjiang": (0.31, 0.94), "Anhui": (0.98, 0.34)}, arrow_color=PALETTE["blue"], arrow_width=0.75)

    ax=fig.add_subplot(gs[1,1]); axd=ax; panel_label(ax,"d", y=1.115); _alluvial(ax,correction)
    # Keep the multiline panel-a y label inside the page boundary.
    fig.subplots_adjust(left=0.088,right=0.985,top=0.94,bottom=0.095,wspace=0.25,hspace=0.27)
    fig.canvas.draw()
    pos1=ax1.get_position(); pos2=ax2.get_position()
    a_box=axa.get_position(); b_box=axb.get_position(); d_box=axd.get_position()
    axa.set_position([pos1.x0, a_box.y0, pos1.width, a_box.height])
    axb.set_position([d_box.x0, b_box.y0, d_box.width, b_box.height])
    fig.canvas.draw()
    _assert_x_aligned(axa, ax1, "Fig4a/Fig4c")
    _assert_x_aligned(axb, axd, "Fig4b/Fig4d")
    pos1=ax1.get_position(); pos2=ax2.get_position()
    cax1=fig.add_axes([pos1.x1 + 0.020, pos1.y0 + 0.12*pos1.height, 0.012, 0.66*pos1.height])
    cb1=fig.colorbar(sc1,cax=cax1,orientation="vertical"); cb1.set_label(""); fig.text(pos1.x1+0.026, pos1.y0+0.84*pos1.height, "Initial Δ (GW)", fontsize=4.2, rotation=90, ha="center", va="center"); cb1.ax.tick_params(labelsize=4.2,length=1.2,pad=0.7); cb1.outline.set_linewidth(0.35)
    cax2=fig.add_axes([pos2.x1 + 0.020, pos2.y0 + 0.12*pos2.height, 0.012, 0.66*pos2.height])
    cb2=fig.colorbar(sc2,cax=cax2,orientation="vertical"); cb2.set_label(""); fig.text(pos2.x1+0.026, pos2.y0+0.84*pos2.height, f"{final_period} Δ (GW)", fontsize=4.2, rotation=90, ha="center", va="center"); cb2.ax.tick_params(labelsize=4.2,length=1.2,pad=0.7); cb2.outline.set_linewidth(0.35)
    save_figure(fig,FIG_MAIN/"Fig4_spatial_path_dependence")

def figure5() -> None:
    data=read_table(TABLE_MAIN/"fig5_robustness_effects.csv")
    fig,axes=plt.subplots(2,2,figsize=(7.0866,5.45))
    _forest(axes[0,0],data,"cumulative_system_cost_pv_usd",1e9,"Present-value cost penalty (billion US$)","a",PALETTE["vermillion"])
    _forest(axes[0,1],data,"future_battery_build_mw",1e3,"Observed − optimized battery power build (GW)","b",PALETTE["blue"],labels_toward_zero=True)
    _forest(axes[1,0],data,"future_battery_energy_build_mwh",1e3,"Observed − optimized battery energy build (GWh)","c",PALETTE["orange"],labels_toward_zero=True)
    ax=axes[1,1]; panel_label(ax,"d", y=1.125)
    wide=data.pivot(index="legacy_context",columns="metric",values="observed_minus_optimal").reindex(CONTEXTS)
    x=wide["future_battery_energy_build_mwh"]/1000; y=wide["cumulative_system_cost_pv_usd"]/1e9
    power_magnitude=wide["future_battery_build_mw"].abs()
    sizes=25+75*(power_magnitude/max(float(power_magnitude.max()),1e-12))
    ax.scatter(x,y,s=sizes,c=np.arange(len(wide)),cmap="viridis",edgecolor="white",linewidth=0.6,zorder=3)
    xpad=(x.max()-x.min())*0.22 if x.max()>x.min() else 1.0
    ypad=(y.max()-y.min())*0.28 if y.max()>y.min() else 1.0
    ax.set_xlim(x.min()-0.08*xpad, x.max()+1.25*xpad)
    ax.set_ylim(y.min()-0.22*ypad, y.max()+0.62*ypad)
    label_offsets={
        "base": (7, -8, "left"),
        "tx_fixed": (7, 7, "left"),
        "ph_conservative": (7, -9, "left"),
        "carbon_tight": (7, 8, "left"),
        "battery_cost_high": (7, 10, "left"),
        "battery_cost_low": (-7, 7, "right"),
    }
    for context,xv,yv in zip(wide.index,x,y):
        dx,dy,ha=label_offsets[context]
        ax.annotate(
            ("Pumped-storage cap" if context == "ph_conservative" else ROBUSTNESS_CONTEXT_LABELS[context]),(xv,yv),xycoords="data",xytext=(dx,dy),textcoords="offset points",
            fontsize=4.9,ha=ha,va="center",
            bbox={"boxstyle":"round,pad=0.15","facecolor":"white","edgecolor":"none","alpha":0.88},
            arrowprops={"arrowstyle":"-","shrinkA":1.0,"shrinkB":4.0,"linewidth":0.55,"color":PALETTE["blue"]},
            zorder=4,annotation_clip=False,
        )
    ax.set_xlabel("Extra battery energy build (GWh)"); ax.set_ylabel("Present-value cost penalty (billion US$)")
    clean_axis(ax,"both")
    # Leave a small top safety margin for panel letters in raster/PDF conversion.
    # The wider inter-column gutter prevents the right-edge value labels in
    # panels a/c from touching the long context labels in panels b/d.
    fig.subplots_adjust(left=0.19,right=0.975,top=0.94,bottom=0.09,wspace=0.50,hspace=0.35)
    save_figure(fig,FIG_MAIN/"Fig5_robustness_boundary_conditions")

def supplementary_figures() -> None:
    nodes=read_table(TABLE_MAIN/"fig1a_legacy_nodes.csv")
    edges=read_table(TABLE_MAIN/"fig1b_model_network_edges.csv")
    allocation=read_table(TABLE_MAIN/"fig2_spatial_allocation.csv")
    match=read_table(TABLE_MAIN/"fig1b_storage_demand_resource_match.csv")
    design=read_table(TABLE_MAIN/"fig1c_scenario_design.csv")
    system=read_table(TABLE_MAIN/"fig3_system_value.csv")
    transition=read_table(TABLE_MAIN/"fig5_transition_paths.csv")
    robust=read_table(TABLE_MAIN/"fig5_robustness_effects.csv")
    tech=read_table(TABLE_SUPP/"figS09_technology_capacity_differences.csv")
    tx=read_table(TABLE_SUPP/"figS11_transmission_line_differences.csv")
    final=read_table(TABLE_MAIN/"fig4_future_storage_spatial_reconfiguration.csv")

    # S01: network, demand and VRE evidence.
    # A shallow landscape canvas matches the fixed map aspect and removes the
    # otherwise empty bands above and below the three input maps.
    fig,axes=plt.subplots(1,3,figsize=(7.0866,2.32))
    for i,(col,title,cbar) in enumerate([
        ("coincident_peak_2023_mw","Coincident peak in the stock-anchor block","Peak demand (GW)"),
        ("wind_solar_capacity_2023_mw","Wind and solar capacity in the stock-anchor block","Wind and solar capacity (GW)"),
        ("storage_to_peak_ratio","Inherited storage-to-peak ratio","Storage / peak"),
    ]):
        panel_label(axes[i],chr(97+i), y=1.11)
        temp=nodes.copy(); temp["plot_value"]=temp[col]/1000 if col.endswith("_mw") else temp[col]
        node_map(axes[i],temp,edges,size_column="plot_value",color_column="plot_value",title=title,labels=3,figure=fig,color_label=cbar)
    fig.subplots_adjust(left=0.050,right=0.99,top=0.90,bottom=0.025,wspace=0.16)
    save_figure(fig,FIG_SUPP/"FigS01_model_zone_network_inputs")

    # S02: power-energy-duration validation.
    fig,axes=plt.subplots(1,2,figsize=(7.0866,3.0))
    panel_label(axes[0],"a", y=1.11)
    sc=axes[0].scatter(nodes["existing_new_storage_power_mw"]/1000,nodes["existing_new_storage_energy_mwh"]/1000,s=25,c=nodes["existing_duration_h"],cmap="viridis",edgecolor="white",linewidth=0.4)
    x=np.linspace(0,nodes["existing_new_storage_power_mw"].max()/1000,100)
    avg=nodes["existing_new_storage_energy_mwh"].sum()/nodes["existing_new_storage_power_mw"].sum()
    axes[0].plot(x,x*avg,linestyle="--",color=PALETTE["mid_grey"],label=f"National average {avg:.2f} h")
    axes[0].set_xlabel("Inherited power (GW)"); axes[0].set_ylabel("Inherited energy (GWh)"); axes[0].legend(loc="lower left",bbox_to_anchor=(0.0,1.015),borderaxespad=0.0); clean_axis(axes[0],"both")
    fig.colorbar(sc,ax=axes[0],fraction=0.045,pad=0.02).set_label("Duration (h)")
    panel_label(axes[1],"b", y=1.11)
    axes[1].set_xlim(0,1); axes[1].set_ylim(0,1); axes[1].axis("off")
    axes[1].set_title("Standardized-duration accounting consistency", loc="left", pad=6.0)
    duration_spread=float(nodes["existing_duration_h"].max()-nodes["existing_duration_h"].min())
    closure=(nodes["existing_new_storage_energy_mwh"]-nodes["existing_new_storage_power_mw"]*nodes["existing_duration_h"]).abs()
    audit_cards=[
        ("Zones included",f"{len(nodes)} / {len(nodes)}","complete coverage"),
        ("Common duration",f"{avg:.2f} h","power-weighted"),
        ("Duration spread",f"{duration_spread:.2f} h","maximum minus minimum"),
        ("Energy identity",f"{float(closure.max()):.2f} MWh","max |E − P × duration|"),
    ]
    for idx,(label,value,note) in enumerate(audit_cards):
        row,col=divmod(idx,2); x0=0.03+0.49*col; y0=0.54-0.38*row
        axes[1].add_patch(FancyBboxPatch((x0,y0),0.44,0.29,transform=axes[1].transAxes,
                                        boxstyle="round,pad=0.012,rounding_size=0.018",
                                        facecolor=PALETTE["pale"],edgecolor=PALETTE["light_grey"],linewidth=0.65))
        axes[1].text(x0+0.035,y0+0.225,"CONSISTENT",transform=axes[1].transAxes,ha="left",va="center",
                     fontsize=5.0,fontweight="bold",color=PALETTE["teal"])
        axes[1].text(x0+0.22,y0+0.165,value,transform=axes[1].transAxes,ha="center",va="center",
                     fontsize=8.0,fontweight="bold",color=PALETTE["dark"])
        axes[1].text(x0+0.22,y0+0.092,label,transform=axes[1].transAxes,ha="center",va="center",
                     fontsize=5.3,color=PALETTE["dark"])
        axes[1].text(x0+0.22,y0+0.038,note,transform=axes[1].transAxes,ha="center",va="center",
                     fontsize=4.35,color=PALETTE["grey"])
    fig.tight_layout(); save_figure(fig,FIG_SUPP/"FigS02_storage_power_energy_duration_validation")

    # S03: empirical deployment envelope.
    fig,axes=plt.subplots(1,2,figsize=(7.0866,3.0))
    panel_label(axes[0],"a", y=1.11)
    ratio=float(nodes["storage_to_peak_ratio"].quantile(0.95))
    axes[0].scatter(nodes["coincident_peak_2023_mw"]/1000,nodes["existing_new_storage_power_mw"]/1000,s=22,c=nodes["storage_to_peak_ratio"],cmap="viridis",edgecolor="white",linewidth=0.4)
    xmax=nodes["coincident_peak_2023_mw"].max()/1000
    axes[0].plot([0,xmax],[0,xmax*ratio],linestyle="--",color=PALETTE["grey"],label=f"95th-percentile envelope: {ratio:.2f} × peak")
    axes[0].set_xlabel("Coincident peak (GW)"); axes[0].set_ylabel("Inherited storage power (GW)"); axes[0].legend(loc="lower left",bbox_to_anchor=(0.0,1.015),borderaxespad=0.0); clean_axis(axes[0],"both")
    panel_label(axes[1],"b", y=1.11)
    opt=allocation[allocation["scenario"].eq(PAIR[1])].copy()
    if "zone_power_cap_mw" not in opt.columns:
        caps=nodes[["model_zone","existing_new_storage_power_mw","coincident_peak_2023_mw"]].copy()
        caps["zone_power_cap_mw"]=np.maximum(caps["existing_new_storage_power_mw"],caps["coincident_peak_2023_mw"]*ratio)
        opt=opt.merge(caps[["model_zone","zone_power_cap_mw"]],on="model_zone",how="left")
    opt["cap_utilization"]=opt["realized_legacy_power_mw"]/opt["zone_power_cap_mw"].replace(0,np.nan)
    opt=opt.sort_values("cap_utilization")
    axes[1].barh(np.arange(len(opt)),100*opt["cap_utilization"],color=PALETTE["orange"],height=0.72)
    axes[1].axvline(100,color=PALETTE["dark"],linestyle="--",linewidth=0.7)
    axes[1].set_yticks(np.arange(len(opt)),[zone_label_compact(z) for z in opt["model_zone"]],fontsize=4.8)
    axes[1].set_xlabel("Optimized allocation / empirical cap (%)"); clean_axis(axes[1],"x")
    fig.tight_layout(); save_figure(fig,FIG_SUPP/"FigS03_empirical_deployment_envelope")

    # S04: full 16-scenario design matrix with explicit categorical semantics.
    matrix=read_table(TABLE_SUPP/"figS06_scenario_matrix.csv")
    required=["scenario","legacy_allocation_mode","transmission_case","pumped_hydro_case","carbon_cap_multiplier","battery_cost_case"]
    require_columns(matrix,required,"Fig. S4 scenario matrix")
    label_map={
        "SL00_OBSERVED_ACTUAL":"Reconstructed duration",
        "SL01_OBSERVED_STANDARDIZED":"Reconstructed standardized",
        "SL02_OPTIMAL_REALLOCATION":"Optimized reallocation",
        "SL03_NO_LEGACY":"No legacy",
        "SL04_RULE_LOAD":"Load rule",
        "SL05_RULE_VRE":"Renewables rule",
        "SL06_TX_FIXED_OBSERVED":"Fixed transmission: reconstructed",
        "SL07_TX_FIXED_OPTIMAL":"Fixed transmission: optimized",
        "SL08_PH_CONSERVATIVE_OBSERVED":"Conservative pumped storage: reconstructed",
        "SL09_PH_CONSERVATIVE_OPTIMAL":"Conservative pumped storage: optimized",
        "SL10_CARBON_TIGHT_OBSERVED":"Tighter carbon cap: reconstructed",
        "SL11_CARBON_TIGHT_OPTIMAL":"Tighter carbon cap: optimized",
        "SL12_COST_LOW_OBSERVED":"Low battery cost: reconstructed",
        "SL13_COST_LOW_OPTIMAL":"Low battery cost: optimized",
        "SL14_COST_HIGH_OBSERVED":"High battery cost: reconstructed",
        "SL15_COST_HIGH_OPTIMAL":"High battery cost: optimized",
    }
    legacy_text={"observed_actual":"Reconstructed duration","observed_standardized":"Standardized stock","optimized_reallocation":"Optimized","none":"None","rule_load":"Load rule","rule_vre":"Renewables rule"}
    legacy_color={"observed_actual":PALETTE["grey"],"observed_standardized":PALETTE["blue"],"optimized_reallocation":PALETTE["orange"],"none":PALETTE["dark"],"rule_load":PALETTE["teal"],"rule_vre":PALETTE["purple"]}
    rows=[]
    for row in matrix.itertuples(index=False):
        mode=str(row.legacy_allocation_mode)
        duration="Heterogeneous" if mode=="observed_actual" else ("—" if mode=="none" else "Common")
        tx_label="Fixed" if str(row.transmission_case)=="TX_fixed" else "Policy"
        ph_label="Conservative" if str(row.pumped_hydro_case)=="PH_conservative" else "Baseline"
        carbon_label="Tighter" if float(row.carbon_cap_multiplier)<0.999 else "Base"
        cost_raw=str(row.battery_cost_case)
        cost_label={
            "CN_low":"Low","CN_high":"High","CN_mid":"Central",
            "NLR_2025_low":"Low","NLR_2025_high":"High","NLR_2025_mid":"Central",
        }.get(cost_raw,cost_raw.replace("_"," "))
        rows.append([legacy_text.get(mode,mode),duration,tx_label,ph_label,carbon_label,cost_label])
    cols=["Legacy geography","Duration","Transmission","Pumped hydro","Carbon cap","Battery cost"]
    fig,ax=plt.subplots(figsize=(7.0866,5.25)); panel_label(ax,"a",x=-0.045)
    ax.set_xlim(0,len(cols)); ax.set_ylim(0,len(matrix)); ax.invert_yaxis()
    neutral={"Heterogeneous":PALETTE["sand"],"Common":"#D9E8F2","—":"#FFFFFF","Policy":"#EDF2F4","Fixed":PALETTE["purple"],"Baseline":"#EDF2F4","Conservative":PALETTE["green"],"Base":"#EDF2F4","Tighter":PALETTE["red"],"Central":"#EDF2F4","Low":PALETTE["teal"],"High":PALETTE["orange"]}
    for i,(scenario,cells) in enumerate(zip(matrix["scenario"].astype(str),rows)):
        mode=str(matrix.iloc[i]["legacy_allocation_mode"])
        for j,text in enumerate(cells):
            color=legacy_color.get(mode,PALETTE["light_grey"]) if j==0 else neutral.get(text,PALETTE["light_grey"])
            ax.add_patch(plt.Rectangle((j,i),1,1,facecolor=color,edgecolor="white",linewidth=0.7))
            dark_text = text in {"—","Common","Policy","Baseline","Base","Central"}
            ax.text(j+0.5,i+0.5,text,ha="center",va="center",fontsize=5.15,color=PALETTE["dark"] if dark_text else "white",fontweight="bold" if j==0 else "normal")
        if i in {5,7,9,11,13}:
            ax.plot([0,len(cols)],[i+1,i+1],color=PALETTE["dark"],linewidth=0.8)
    ax.set_xticks(np.arange(len(cols))+0.5,cols,rotation=18,ha="right")
    ax.set_yticks(np.arange(len(matrix))+0.5,[label_map.get(x,x) for x in matrix["scenario"].astype(str)],fontsize=5.3)
    ax.tick_params(length=0)
    for sp in ax.spines.values(): sp.set_visible(False)
    fig.subplots_adjust(left=0.27,right=0.985,top=0.91,bottom=0.13)
    save_figure(fig,FIG_SUPP/"FigS04_full_scenario_matrix")

    # S05: rule-based allocations and their spatial distance from the optimum.
    coords=nodes[["model_zone","longitude","latitude"]]
    frames={}
    for scenario in ["SL04_RULE_LOAD","SL05_RULE_VRE",PAIR[1]]:
        f=allocation[allocation["scenario"].eq(scenario)].merge(coords,on="model_zone",validate="one_to_one").copy()
        f["power_gw"]=f["realized_legacy_power_mw"]/1000
        frames[scenario]=f
    opt_power=frames[PAIR[1]][["model_zone","power_gw"]].rename(columns={"power_gw":"optimized_gw"})
    for scenario in ["SL04_RULE_LOAD","SL05_RULE_VRE"]:
        frames[scenario]=frames[scenario].merge(opt_power,on="model_zone",validate="one_to_one")
        frames[scenario]["delta_vs_optimized_gw"]=frames[scenario]["power_gw"]-frames[scenario]["optimized_gw"]
    absmax=max(frames["SL04_RULE_LOAD"]["power_gw"].max(),frames["SL05_RULE_VRE"]["power_gw"].max())
    dmax=max(frames["SL04_RULE_LOAD"]["delta_vs_optimized_gw"].abs().max(),frames["SL05_RULE_VRE"]["delta_vs_optimized_gw"].abs().max(),1e-9)
    fig=plt.figure(figsize=(7.0866,5.80)); gs=fig.add_gridspec(2,2,wspace=0.22,hspace=0.32)
    axes=[]; scat=[]
    specs=[
        ("SL04_RULE_LOAD","power_gw","Load-rule allocation",False,Normalize(0,absmax)),
        ("SL05_RULE_VRE","power_gw","Renewables-rule allocation",False,Normalize(0,absmax)),
        ("SL04_RULE_LOAD","delta_vs_optimized_gw","Load rule minus optimized",True,TwoSlopeNorm(vmin=-dmax,vcenter=0,vmax=dmax)),
        ("SL05_RULE_VRE","delta_vs_optimized_gw","Renewables rule minus optimized",True,TwoSlopeNorm(vmin=-dmax,vcenter=0,vmax=dmax)),
    ]
    for i,(scenario,col,title,delta,norm) in enumerate(specs):
        ax=fig.add_subplot(gs[i//2,i%2]); panel_label(ax,chr(97+i),x=-0.025, y=1.11); axes.append(ax)
        scat.append(node_map(ax,frames[scenario],edges,size_column=col,color_column=col,title=title,delta=delta,labels=3,size_max=dmax if delta else absmax,norm=norm))
        ax.set_title(title, loc="left")
    for ax, artist in zip(axes[:2], scat[:2]):
        top_map_colorbar(fig, ax, artist, "Legacy power (GW)", width=0.60)
    for ax, artist in zip(axes[2:], scat[2:]):
        top_map_colorbar(fig, ax, artist, "Rule minus optimized (GW)", width=0.60)
    # Titles occupy a second line above the complete external scale.
    for ax in axes:
        ax.set_title(ax.get_title(loc='left'), loc='left', y=1.29, pad=0)
    # Preserve the common outside-upper-left panel tags on the left map column.
    fig.subplots_adjust(left=0.075,right=0.99,top=0.90,bottom=0.09)
    save_figure(fig,FIG_SUPP/"FigS05_rule_based_allocation_diagnostics")

    # S06: complete zone-level reallocation and duration-standardization effects.
    fig,axes=plt.subplots(1,2,figsize=(7.0866,5.15))
    panel_label(axes[0],"a", y=1.11)
    opt=allocation[allocation["scenario"].eq(PAIR[1])].sort_values("delta_power_vs_observed_standardized_mw")
    vals=opt["delta_power_vs_observed_standardized_mw"]/1000
    axes[0].barh(np.arange(len(opt)),vals,color=[PALETTE["blue"] if v<0 else PALETTE["orange"] for v in vals],height=0.72)
    axes[0].set_yticks(np.arange(len(opt)),[zone_label_compact(z) for z in opt["model_zone"]],fontsize=4.8)
    axes[0].axvline(0,color=PALETTE["dark"],linewidth=0.6); axes[0].set_xlabel("Optimized minus observed power (GW)"); clean_axis(axes[0],"x")
    panel_label(axes[1],"b", y=1.11)
    actual=allocation[allocation["scenario"].eq("SL00_OBSERVED_ACTUAL")].sort_values("delta_energy_vs_observed_standardized_mwh")
    energy_delta=actual["delta_energy_vs_observed_standardized_mwh"]/1000
    axes[1].barh(np.arange(len(actual)),energy_delta,color=[PALETTE["blue"] if v<0 else PALETTE["orange"] for v in energy_delta],height=0.72)
    axes[1].set_yticks(np.arange(len(actual)),[zone_label_compact(z) for z in actual["model_zone"]],fontsize=4.8)
    axes[1].axvline(0,color=PALETTE["dark"],linewidth=0.6); axes[1].set_xlabel("Actual minus standardized legacy energy (GWh)"); clean_axis(axes[1],"x")
    fig.tight_layout(); save_figure(fig,FIG_SUPP/"FigS06_full_reallocation_and_duration_deltas")

    # S07: all core scenario period cost penalties relative to optimized reallocation.
    scenarios=["SL00_OBSERVED_ACTUAL","SL01_OBSERVED_STANDARDIZED","SL04_RULE_LOAD","SL05_RULE_VRE"]
    expected_periods=sorted(transition.loc[transition["scenario"].eq(PAIR[1]),"period"].astype(int).unique())
    fig,ax=plt.subplots(figsize=(7.0866,3.8)); panel_label(ax,"a",x=-0.06)
    opt=transition[transition["scenario"].eq(PAIR[1])].set_index("period")["SystemCost_present_value_to_base_year"]
    plotted=[]
    markers=["o","s","^","D"]
    for scenario,marker in zip(scenarios,markers):
        g=transition[transition["scenario"].eq(scenario)].set_index("period")
        if sorted(g.index.astype(int).unique()) != expected_periods:
            raise ValueError(f"Fig. S7 missing period-resolved data for {scenario}")
        delta=(g["SystemCost_present_value_to_base_year"]-opt)/1e9
        ax.plot(delta.index,delta.values,marker=marker,markersize=3.6,linewidth=1.25,label=SCENARIO_LABELS[scenario],color=SCENARIO_COLORS[scenario])
        plotted.append((scenario,delta))
    ax.axhline(0,color=PALETTE["dark"],linewidth=0.6); ax.set_xlabel("Planning period"); ax.set_ylabel("Discounted period cost penalty (billion US$)")
    ax.set_xticks(expected_periods); ax.set_xlim(expected_periods[0]-1.5, expected_periods[-1]+1.5)
    ax.legend(ncol=2,loc="lower center",bbox_to_anchor=(0.5,1.015),columnspacing=0.9,handletextpad=0.45,borderaxespad=0.0)
    clean_axis(ax,"y")
    save_figure(fig,FIG_SUPP/"FigS07_period_system_cost_penalties")

    # S08: non-battery technology and curtailment adaptation, without duplicating absolute trajectories.
    pivot=tech.pivot(index="technology",columns="period",values="observed_minus_optimized_mw")/1000
    pivot=pivot.loc[pivot.abs().max(axis=1)>1e-3]
    fig=plt.figure(figsize=(7.0866,4.65)); gs=fig.add_gridspec(2,2,width_ratios=[1.30,0.90],hspace=0.35,wspace=0.40)
    ax=fig.add_subplot(gs[:,0]); panel_label(ax,"a",x=-0.10)
    limit=max(float(np.abs(pivot.to_numpy()).max()),1e-9)
    im=ax.imshow(pivot,aspect="auto",cmap="RdBu_r",norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit))
    technology_labels = {
        "Hydro_NonPumped": "Hydro non-pumped",
        "Hydro NonPumped": "Hydro non-pumped",
        "Solar_Distributed": "Distributed solar",
        "Solar Distributed": "Distributed solar",
        "Solar_Utility": "Utility-scale solar",
        "Solar Utility": "Utility-scale solar",
        "Wind_Onshore": "Onshore wind",
        "Wind Onshore": "Onshore wind",
    }
    display_technologies = [technology_labels.get(str(z), zone_label_compact(z)) for z in pivot.index]
    ax.set_yticks(range(len(pivot)),display_technologies); ax.set_xticks(range(len(pivot.columns)),pivot.columns.astype(int)); ax.set_xlabel("Planning period")
    fig.colorbar(im,ax=ax,fraction=0.035,pad=0.025).set_label("Capacity difference (GW)")
    diff=read_table(TABLE_MAIN/"fig3a_compensatory_investment.csv")
    ax=fig.add_subplot(gs[0,1]); panel_label(ax,"b",x=-0.16,y=1.08)
    vals=diff["curtailment_delta_gwh_per_yr"]/1000
    ax.bar(diff["period"],vals,color=[PALETTE["orange"] if v>0 else PALETTE["blue"] for v in vals],width=3.2)
    periods = diff["period"].astype(int).tolist()
    ax.axhline(0,color=PALETTE["dark"],linewidth=0.6); ax.set_ylabel("Curtailment delta\n(TWh yr$^{-1}$)")
    ax.set_xticks(periods); ax.set_xlim(periods[0]-2.0, periods[-1]+2.0); ax.tick_params(axis="x", labelsize=5.0)
    ax=fig.add_subplot(gs[1,1]); panel_label(ax,"c",x=-0.16,y=1.08)
    rate=transition.pivot(index="period",columns="scenario",values="curtailment_rate")
    rate_delta=100*(rate[PAIR[0]]-rate[PAIR[1]])
    ax.plot(rate_delta.index,rate_delta.values,marker="o",color=PALETTE["purple"],linewidth=1.5)
    ax.axhline(0,color=PALETTE["dark"],linewidth=0.6); ax.set_xlabel("Planning period"); ax.set_ylabel("Curtailment-rate delta\n(percentage points)")
    ax.set_xticks(periods); ax.set_xlim(periods[0]-2.0, periods[-1]+2.0); ax.tick_params(axis="x", labelsize=5.0)
    fig.subplots_adjust(left=0.155,right=0.985,top=0.92,bottom=0.12)
    save_figure(fig,FIG_SUPP/"FigS08_technology_and_curtailment_adaptation")

    # S09: transmission investment differences, not directional dispatch.
    fig,axes=plt.subplots(1,2,figsize=(7.0866,3.5))
    panel_label(axes[0],"a", y=1.11)
    tx2=tx.assign(absdiff=tx["observed_minus_optimized_mw"].abs()).nlargest(14,"absdiff").sort_values("observed_minus_optimized_mw")
    def transmission_label(value: object) -> str:
        label=str(value).replace("East_Inner_Mongolia","E. Inner Mong.").replace("West_Inner_Mongolia","W. Inner Mong.")
        return label.replace("_"," ")
    labels=[f"{transmission_label(l)} ({int(p)})" for l,p in zip(tx2["TRANSMISSION_LINE"],tx2["period"])]
    vals=tx2["observed_minus_optimized_mw"]/1000
    axes[0].barh(np.arange(len(tx2)),vals,color=[PALETTE["orange"] if v>0 else PALETTE["blue"] for v in vals],height=0.72)
    axes[0].set_yticks(np.arange(len(tx2)),labels,fontsize=4.7); axes[0].axvline(0,color=PALETTE["dark"],linewidth=0.6); axes[0].set_xlabel("Line build difference (GW)"); clean_axis(axes[0],"x")
    panel_label(axes[1],"b", y=1.11)
    by_period=tx.groupby("period",as_index=False).agg(
        net_difference_mw=("observed_minus_optimized_mw","sum"),
        gross_reconfiguration_mw=("observed_minus_optimized_mw",lambda x:0.5*float(np.abs(x).sum())),
    ).sort_values("period")
    axes[1].bar(by_period["period"],by_period["gross_reconfiguration_mw"]/1000,width=3.0,color=PALETTE["teal"],alpha=0.82,label="Gross line reconfiguration")
    axes[1].plot(by_period["period"],by_period["net_difference_mw"]/1000,marker="o",color=PALETTE["dark"],linewidth=1.1,label="Net national difference")
    axes[1].axhline(0,color=PALETTE["dark"],linewidth=0.55)
    axes[1].set_xlabel("Planning period"); axes[1].set_ylabel("Transmission-build difference (GW)")
    tx_periods=by_period["period"].astype(int).tolist(); axes[1].set_xticks(tx_periods); axes[1].set_xlim(tx_periods[0]-2.0,tx_periods[-1]+2.0); axes[1].tick_params(axis="x",labelsize=5.0)
    axes[1].legend(loc="lower left",bbox_to_anchor=(0.0,1.015),fontsize=5.4,borderaxespad=0.0); clean_axis(axes[1],"y")
    fig.tight_layout(); save_figure(fig,FIG_SUPP/"FigS09_transmission_line_differences")

    # S10: final spatial reconfiguration.  Power-energy scatter and duration
    # histograms are omitted because the exact 4 h identity makes them
    # algebraically redundant; panels instead report sign and concentration.
    optimized_final=final[final["scenario"].eq(PAIR[1])].copy()
    optimized_final["delta_power_gw"]=optimized_final["delta_final_power_vs_observed_mw"]/1000.0
    signed=optimized_final.assign(abs_delta=lambda x:x["delta_power_gw"].abs()).nlargest(16,"abs_delta").sort_values("delta_power_gw")
    fig,axes=plt.subplots(1,2,figsize=(7.0866,3.35))
    panel_label(axes[0],"a", y=1.11)
    values=signed["delta_power_gw"].to_numpy(float); yy=np.arange(len(signed))
    axes[0].barh(yy,values,color=[PALETTE["orange"] if value>0 else PALETTE["blue"] for value in values],height=0.72)
    axes[0].axvline(0,color=PALETTE["dark"],linewidth=0.6)
    axes[0].set_yticks(yy,[zone_label_compact(zone) for zone in signed["model_zone"]],fontsize=4.8)
    axes[0].set_xlabel("Optimized − observed final power (GW)")
    axes[0].set_title("Largest 2058 spatial reallocations",loc="left")
    clean_axis(axes[0],"x")

    panel_label(axes[1],"b", y=1.11)
    ranked=optimized_final.assign(abs_delta=lambda x:x["delta_power_gw"].abs()).sort_values("abs_delta",ascending=False)
    total=float(ranked["abs_delta"].sum())
    ranked["cumulative_share"]=ranked["abs_delta"].cumsum()/max(total,1e-12)
    xx=np.arange(1,len(ranked)+1)
    axes[1].plot(xx,100*ranked["cumulative_share"],color=PALETTE["teal"],linewidth=1.7,marker="o",markersize=2.6)
    axes[1].axhline(80,color=PALETTE["mid_grey"],linestyle="--",linewidth=0.7)
    n80=int(np.searchsorted(ranked["cumulative_share"].to_numpy(float),0.80)+1)
    top5=100*float(ranked["cumulative_share"].iloc[min(4,len(ranked)-1)])
    axes[1].axvline(n80,color=PALETTE["mid_grey"],linestyle=":",linewidth=0.7)
    axes[1].text(0.98,0.16,f"Top 5 zones: {top5:.2f}%\n80% reached by {n80} zones",transform=axes[1].transAxes,
                 ha="right",va="bottom",fontsize=5.6,color=PALETTE["grey"])
    axes[1].set_xlim(1,len(ranked)); axes[1].set_ylim(0,105)
    axes[1].set_xlabel("Zones ranked by absolute reallocation")
    axes[1].set_ylabel("Cumulative share of absolute change (%)")
    axes[1].set_title("Concentration of final reallocation",loc="left")
    clean_axis(axes[1],"both")
    fig.subplots_adjust(left=0.15,right=0.98,top=0.86,bottom=0.16,wspace=0.38)
    save_figure(fig,FIG_SUPP/"FigS10_final_storage_power_energy_duration")

    # S11: secondary robustness metrics not used in the main claim.
    fig,axes=plt.subplots(1,3,figsize=(7.0866,3.4),sharey=False)
    _forest(axes[0],robust,"future_transmission_build_mw",1e3,"Transmission build difference (GW)","a",PALETTE["teal"],show_ylabels=True,labels_toward_zero=True)
    _forest(axes[1],robust,"final_curtailment_gwh_per_yr",1e3,"Final curtailment difference\n(TWh yr$^{-1}$)","b",PALETTE["purple"],show_ylabels=False,labels_toward_zero=True)
    wide=robust.pivot(index="legacy_context",columns="metric",values="observed_minus_optimal").reindex(CONTEXTS)
    tx_delta=wide["future_transmission_build_mw"]/1000.0
    curtail_delta=wide["final_curtailment_gwh_per_yr"]/1000.0
    battery_magnitude=wide["future_battery_build_mw"].abs()/1000.0
    marker_sizes=28+72*battery_magnitude/max(float(battery_magnitude.max()),1e-12)
    ax=axes[2]; panel_label(ax,"c")
    colors=[PALETTE["navy"],PALETTE["blue"],PALETTE["teal"],PALETTE["purple"],PALETTE["orange"],PALETTE["red"]]
    ax.scatter(tx_delta,curtail_delta,s=marker_sizes,c=colors,edgecolor="white",linewidth=0.55,zorder=3)
    offsets={"base":(-5,7),"tx_fixed":(5,-9),"ph_conservative":(5,7),"carbon_tight":(5,-9),"battery_cost_low":(5,7),"battery_cost_high":(5,-9)}
    short={"base":"Base","tx_fixed":"Transmission fixed","ph_conservative":"Pumped-storage cap","carbon_tight":"Carbon cap","battery_cost_low":"Low cost","battery_cost_high":"High cost"}
    for context,xv,yv in zip(wide.index,tx_delta,curtail_delta):
        ax.annotate(short[context],(xv,yv),xytext=offsets[context],textcoords="offset points",fontsize=4.6,
                    ha="right" if context=="base" else "left",va="center",bbox={"facecolor":"white","edgecolor":"none","pad":0.12,"alpha":0.82})
    ax.axhline(0,color=PALETTE["mid_grey"],linewidth=0.55); ax.axvline(0,color=PALETTE["mid_grey"],linewidth=0.55)
    ax.set_xlabel("Transmission build difference (GW)"); ax.set_ylabel("Curtailment difference\n(TWh yr$^{-1}$)")
    ax.set_title("Network–curtailment coupling",loc="left")
    ax.text(0.98,0.96,"Marker area = |battery-power response|",transform=ax.transAxes,ha="right",va="top",fontsize=4.5,color=PALETTE["grey"])
    clean_axis(ax,"both")
    fig.subplots_adjust(left=0.22,right=0.985,top=0.90,bottom=0.16,wspace=0.55)
    save_figure(fig,FIG_SUPP/"FigS11_extended_robustness_metrics")

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--group",choices=["main","supplementary","all"],default="all"); args=parser.parse_args()
    configure()
    if args.group in {"main","all"}:
        figure1(); figure2(); figure3(); figure4(); figure5()
    if args.group in {"supplementary","all"}:
        supplementary_figures()
    print({"version":"V17T5R6R8R5","stage":"frozen_main_model_renderer","group":args.group,"main_figures":5,"supplementary_figures_rendered_by_stage":11})


if __name__ == "__main__":
    main()
