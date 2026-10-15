#!/usr/bin/env python3
"""Render publication figures for future-storage results.

Fig. 6 answers where and how much storage is built in the 2033 correction.
Fig. 7 answers when, where and under which context future storage changes.
Fig. S14 gives a compact overview of all 26 evaluated configurations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.lines import Line2D
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from ne_style import PALETTE, clean_axis, configure, panel_label, save_figure
from plot_spatial_legacy_figures import MAP_FRAME_EDGE, _annotate_named_map_labels_force, _draw_basemap, top_map_colorbar
from v17t5_paths import FIG_MAIN, FIG_SUPP, TABLE_FULL8760, TABLE_V20


TABLE_V31 = TABLE_V20.parent / "future_storage_v31"
TECH_ORDER = [
    "Li-ion/LFP 4 h", "Base PSH", "VRFB 10 h", "VRFB 24 h",
    "PSH 10 h", "PSH 24 h", "CAES 10 h", "CAES 24 h",
    "CAES 100 h", "H2 100 h",
]
TECH_COLORS = {
    "Li-ion/LFP 4 h": PALETTE["navy"], "Base PSH": PALETTE["grey"],
    "VRFB 10 h": PALETTE["teal"], "VRFB 24 h": PALETTE["cyan"],
    "PSH 10 h": PALETTE["orange"], "PSH 24 h": PALETTE["sand"],
    "CAES 10 h": PALETTE["purple"], "CAES 24 h": "#9A8BC2",
    "CAES 100 h": "#B9ADD4", "H2 100 h": PALETTE["yellow"],
}


def _assert_x_aligned(axis_a, axis_b, label: str, tol: float = 1.0e-6) -> None:
    box_a, box_b = axis_a.get_position(), axis_b.get_position()
    mismatch = max(abs(box_a.x0 - box_b.x0), abs(box_a.x1 - box_b.x1))
    if mismatch > tol:
        raise RuntimeError(f"{label}: horizontal frame mismatch {mismatch:.3e}")


def _signed_two(value: float) -> str:
    value = 0.0 if abs(float(value)) < 0.005 else float(value)
    return "0.00" if value == 0.0 else f"{value:+.2f}"
LAYER_COLORS = {"A": PALETTE["navy"], "B": PALETTE["teal"], "C": PALETTE["orange"]}
MAP_LABEL_POSITIONS = {
    "West_Inner_Mongolia": (0.02, 0.73), "East_Inner_Mongolia": (0.98, 0.90),
    "Jilin": (0.98, 0.82), "Liaoning": (0.98, 0.73), "Hebei": (0.98, 0.64),
    "Shandong": (0.98, 0.55), "Jiangsu": (0.98, 0.43), "Shanghai": (0.98, 0.34),
    "Zhejiang": (0.98, 0.27), "Fujian": (0.98, 0.17), "Guangdong": (0.06, 0.08),
    "Henan": (0.04, 0.48), "Hubei": (0.04, 0.30), "Gansu": (0.03, 0.60),
}


def read(root, name: str) -> pd.DataFrame:
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def _map_axis(axis) -> None:
    _draw_basemap(axis, with_inset=True)
    axis.set_xlim(73, 135)
    axis.set_ylim(18, 54)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color(MAP_FRAME_EDGE)
        spine.set_linewidth(0.72)


def _map_colorbar(fig, axis, artist, label: str, *, y: float = 0.865,
                  outside_above: bool = False) -> None:
    # Compatibility arguments are retained, but every map now uses an
    # external top scale that follows the final aligned map frame.
    top_map_colorbar(fig, axis, artist, label, width=0.60)


def _top_zones(frame: pd.DataFrame, value: str, n: int = 5) -> list[str]:
    return frame.nlargest(n, value)["zone"].astype(str).tolist()


def _map_portfolio(fig, axis, frame: pd.DataFrame) -> None:
    _map_axis(axis)
    values = frame["observed_power_gw"].to_numpy(float)
    duration = frame["observed_duration_h"].fillna(0.0).to_numpy(float)
    size_scale = max(float(np.max(values)), 1.0)
    sizes = 14.0 + 185.0 * np.sqrt(np.clip(values, 0, None) / size_scale)
    finite_duration = duration[np.isfinite(duration) & (duration > 0)]
    vmin = float(np.min(finite_duration)) if finite_duration.size else 0.0
    vmax = float(np.max(finite_duration)) if finite_duration.size else 1.0
    if np.isclose(vmin, vmax):
        vmax = vmin + 1.0
    artist = axis.scatter(
        frame.longitude, frame.latitude, s=sizes, c=duration,
        cmap="viridis", norm=Normalize(vmin=vmin, vmax=vmax),
        edgecolor="white", linewidth=0.55, zorder=3,
    )
    label_frame = frame.copy()
    label_frame["model_zone"] = label_frame["zone"].astype(str)
    selected = _top_zones(frame, "observed_power_gw", n=4)
    positions = {zone: MAP_LABEL_POSITIONS[zone] for zone in selected if zone in MAP_LABEL_POSITIONS}
    _annotate_named_map_labels_force(axis, label_frame, positions, fontsize=4.5, arrow_color=PALETTE["grey"])
    _map_colorbar(fig, axis, artist, "Duration (h); area = new power")
    axis.set_title("Observed 2033: location, scale and duration", loc="left", y=1.30, pad=0)


def _map_difference(fig, axis, frame: pd.DataFrame, *, column: str, title: str,
                    sign_label: str, colorbar_y: float = 0.865,
                    colorbar_outside_above: bool = False,
                    title_y: float | None = None) -> None:
    _map_axis(axis)
    values = frame[column].to_numpy(float)
    abs_values = np.abs(values)
    limit = max(float(np.max(abs_values)), 1.0e-9)
    sizes = 14.0 + 185.0 * np.sqrt(abs_values / limit)
    artist = axis.scatter(
        frame.longitude, frame.latitude, s=sizes, c=values,
        cmap="RdBu_r", norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
        edgecolor="white", linewidth=0.55, zorder=3,
    )
    selected = frame.nlargest(min(5, len(frame)), "abs_difference_gw")["zone"].astype(str).tolist()
    label_frame = frame.copy()
    label_frame["model_zone"] = label_frame["zone"].astype(str)
    positions = {zone: MAP_LABEL_POSITIONS[zone] for zone in selected if zone in MAP_LABEL_POSITIONS}
    _annotate_named_map_labels_force(axis, label_frame, positions, fontsize=4.5, arrow_color=PALETTE["grey"])
    _map_colorbar(
        fig, axis, artist,
        f"{sign_label}\nSymbol area shows absolute change",
        y=colorbar_y,
        outside_above=colorbar_outside_above,
    )
    axis.set_title(title, loc="left", y=1.30 if title_y is None else title_y, pad=0)


def _dumbbell(axis, frame: pd.DataFrame, *, y_col: str, observed_col: str,
              optimized_col: str, xlabel: str, title: str, annotations: list[str] | None = None) -> None:
    y = np.arange(len(frame))
    observed = frame[observed_col].to_numpy(float)
    optimized = frame[optimized_col].to_numpy(float)
    for yi, left, right in zip(y, observed, optimized):
        axis.plot([left, right], [yi, yi], color=PALETTE["mid_grey"], linewidth=1.35, zorder=1)
    axis.scatter(observed, y, s=34, color=PALETTE["navy"], edgecolor="white", linewidth=0.55, zorder=3)
    axis.scatter(optimized, y, s=34, color=PALETTE["orange"], marker="s", edgecolor="white", linewidth=0.55, zorder=3)
    axis.set_yticks(y, frame[y_col].astype(str))
    axis.invert_yaxis()
    axis.set_xlabel(xlabel)
    axis.set_title(title, loc="left")
    clean_axis(axis, "x")
    legend = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=PALETTE["navy"], markeredgecolor="white", label="Observed"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor=PALETTE["orange"], markeredgecolor="white", label="Optimized"),
    ]
    axis.legend(handles=legend, ncol=2, loc="lower right", bbox_to_anchor=(1.0, 1.012),
                borderaxespad=0.0, fontsize=5.2, columnspacing=0.8, handletextpad=0.35)
    if annotations is not None:
        span = max(float(np.ptp(np.r_[observed, optimized])), max(abs(observed).max(), abs(optimized).max()) * 0.12, 1.0)
        axis.set_xlim(min(observed.min(), optimized.min()) - 0.04 * span,
                      max(observed.max(), optimized.max()) + 0.42 * span)
        for yi, left, right, text in zip(y, observed, optimized, annotations):
            axis.text(max(left, right) + 0.06 * span, yi, text,
                      ha="left", va="center", fontsize=5.2, color=PALETTE["grey"])


def plot_fig6(pair_metrics: pd.DataFrame, adaptive_zone: pd.DataFrame) -> None:
    fig = plt.figure(figsize=(7.0866, 7.42))
    gs = fig.add_gridspec(2, 2, left=0.15, right=0.985, bottom=0.105, top=0.925, wspace=0.40, hspace=0.38)
    axa, axb, axc, axd = [fig.add_subplot(gs[i, j]) for i in range(2) for j in range(2)]

    _map_portfolio(fig, axa, adaptive_zone)
    _map_difference(fig, axb, adaptive_zone, column="optimized_minus_observed_power_gw",
                    title="Optimized − observed reallocation",
                    sign_label="Optimized − observed (GW)")

    annotations = [f"Δ {_signed_two(value)} GW" for value in pair_metrics.optimized_minus_observed_power_gw]
    _dumbbell(axc, pair_metrics, y_col="pair_label", observed_col="observed_power_gw",
              optimized_col="optimized_power_gw", xlabel="New storage power (GW)",
              title="Matched 2033 portfolio scale", annotations=annotations)

    y = np.arange(len(pair_metrics))
    realloc = pair_metrics.half_l1_reallocation_gw.to_numpy(float)
    axd.barh(y, realloc, color=PALETTE["teal"], edgecolor="white", linewidth=0.5)
    axd.set_yticks(y, pair_metrics.pair_label.astype(str))
    axd.invert_yaxis()
    axd.set_xlim(0, max(realloc) * 1.82)
    for yi, value, penalty in zip(y, realloc, pair_metrics.residual_penalty_million_usd_per_yr):
        axd.text(value + 0.025 * max(realloc), yi,
                 f"{value:.2f} GW\n{penalty/1000:.2f} billion USD yr$^{{-1}}$",
                 va="center", fontsize=5.0, linespacing=1.12)
    axd.set_xlabel("Equivalent spatial reallocation (GW)")
    axd.set_title("Spatial correction and residual penalty", loc="left")
    clean_axis(axd, "x")
    axd.text(0.0, -0.25, "Expanded* denotes the resource-unconstrained technology sensitivity. Baseline and Adaptive have the same effective storage build at reported precision.",
             transform=axd.transAxes, fontsize=5.1, color=PALETTE["grey"], ha="left")

    for axis, label in zip((axa, axb, axc, axd), "ABCD"):
        panel_label(axis, label)
    fig.canvas.draw()
    lower_y1 = min(axa.get_position().y0, axb.get_position().y0) - 0.055
    for map_axis, lower_axis in ((axa, axc), (axb, axd)):
        map_box=map_axis.get_position(); lower_box=lower_axis.get_position()
        lower_axis.set_position([map_box.x0, lower_box.y0, map_box.width, lower_y1-lower_box.y0])
    fig.canvas.draw()
    _assert_x_aligned(axa, axc, "Fig6a/Fig6c")
    _assert_x_aligned(axb, axd, "Fig6b/Fig6d")
    save_figure(fig, FIG_MAIN / "Fig6_future_storage_correction_of_spatial_lockin")


def _stacked_timing(axis, timing: pd.DataFrame, *, difference: bool) -> list[str]:
    value = "observed_minus_optimized_gw" if difference else "observed_power_gw"
    table = timing.pivot_table(index="build_year", columns="technology_group", values=value, aggfunc="sum", fill_value=0.0)
    table = table.sort_index()
    technologies = [tech for tech in TECH_ORDER if tech in table and float(table[tech].abs().sum()) > 1.0e-7]
    x = np.arange(len(table))
    if not difference:
        bottom = np.zeros(len(table))
        for tech in technologies:
            values = table[tech].to_numpy(float)
            axis.bar(x, values, bottom=bottom, width=0.72, color=TECH_COLORS[tech],
                     edgecolor="white", linewidth=0.4, label=tech)
            bottom += values
        total_max = max(float(np.max(bottom)), 1.0)
        axis.set_ylim(0, total_max * 1.16)
        for xi, total in zip(x, bottom):
            axis.text(xi, total + 0.020 * total_max, f"{total:.2f}",
                      ha="center", va="bottom", fontsize=5.1, color=PALETTE["dark"])
        axis.set_ylabel("New power (GW)")
    else:
        positive = np.zeros(len(table))
        negative = np.zeros(len(table))
        for tech in technologies:
            values = table[tech].to_numpy(float)
            bottoms = np.where(values >= 0, positive, negative)
            axis.bar(x, values, bottom=bottoms, width=0.72, color=TECH_COLORS[tech],
                     edgecolor="white", linewidth=0.4, label=tech)
            positive += np.clip(values, 0, None)
            negative += np.clip(values, None, 0)
        axis.axhline(0, color=PALETTE["dark"], linewidth=0.55)
        net_total = table[technologies].sum(axis=1).to_numpy(float)
        span = max(float(np.max(positive) - np.min(negative)), 1.0)
        axis.set_ylim(float(np.min(negative)) - 0.11 * span,
                      float(np.max(positive)) + 0.11 * span)
        for xi, total, upper, lower in zip(x, net_total, positive, negative):
            ypos = upper + 0.022 * span if total >= 0 else lower - 0.022 * span
            axis.text(xi, ypos, _signed_two(total), ha="center",
                      va="bottom" if total >= 0 else "top", fontsize=5.1,
                      color=PALETTE["dark"])
        axis.set_ylabel("Observed − optimized (GW)")
    axis.set_xticks(x, table.index.astype(int).astype(str), rotation=30, ha="right")
    axis.set_xlabel("Build year")
    clean_axis(axis, "y")
    return technologies


def plot_fig7(timing: pd.DataFrame, core_zone: pd.DataFrame, contexts: pd.DataFrame,
              full8760: pd.DataFrame) -> None:
    fig = plt.figure(figsize=(7.0866, 8.34))
    gs = fig.add_gridspec(3, 2, left=0.14, right=0.975, bottom=0.105, top=0.89,
                          height_ratios=[1.0, 1.0, 0.62], wspace=0.39, hspace=0.55)
    axa, axb = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    axc, axd = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])
    axe = fig.add_subplot(gs[2, :])

    technologies = _stacked_timing(axa, timing, difference=False)
    axa.set_title("Existing-layout pathway: build timing", loc="left")
    _stacked_timing(axb, timing, difference=True)
    axb.set_title("Existing − reference additions", loc="left")

    handles = [Line2D([0], [0], marker="s", markersize=6, linestyle="none",
                      markerfacecolor=TECH_COLORS[tech], markeredgecolor="none", label=tech) for tech in technologies]
    fig.legend(handles=handles, ncol=min(5, len(handles)), loc="upper center",
               bbox_to_anchor=(0.56, 0.973), columnspacing=0.85, handletextpad=0.35)

    _map_difference(fig, axc, core_zone, column="observed_minus_optimized_power_gw",
                    title="Cumulative regional build differences, 2028–2058",
                    sign_label="Observed − optimized (GW)",
                    colorbar_outside_above=True, title_y=1.34)

    y = np.arange(len(contexts))
    net = contexts.observed_minus_optimized_power_gw.to_numpy(float)
    colors = [PALETTE["orange"] if value >= 0 else PALETTE["blue"] for value in net]
    axd.barh(y, net, color=colors, edgecolor="white", linewidth=0.45, height=0.62)
    context_labels = contexts.context.astype(str).replace(
        {"Pumped-storage constraint": "Pumped-storage cap"}
    )
    axd.set_yticks(y, context_labels)
    axd.invert_yaxis()
    axd.axvline(0, color=PALETTE["dark"], linewidth=0.55)
    span = max(float(np.max(np.abs(net))), 1.0)
    axd.set_xlim(-1.35 * span, 2.65 * span)
    for yi, value, penalty in zip(y, net, contexts.legacy_penalty_billion_usd):
        value_x = value + 0.035 * span if value >= 0 else value + 0.10 * span
        axd.text(value_x, yi, _signed_two(value),
                 ha="left", va="center",
                 fontsize=5.1, color=PALETTE["dark"])
        axd.text(1.55 * span, yi, f"{penalty:.2f} billion US$ penalty", ha="left", va="center",
                 fontsize=5.15, color=PALETTE["grey"])
    axd.set_xlabel("Observed − optimized cumulative new power (GW)")
    axd.set_title("Net capacity adaptation across seven contexts", loc="left", y=1.34, pad=0)
    clean_axis(axd, "x")
    # The Layer-B/Layer-C distinction is retained in the caption and table;
    # omitting a second below-axis note prevents collision with the x label.

    order = ["Observed inheritance", "Optimized inheritance", "Observed + LDES", "Optimized + LDES"]
    full = full8760.set_index("case_label").reindex(order).reset_index()
    x = np.arange(len(full))
    distance = full.total_robustness_distance_mw.to_numpy(float) / 1000.0
    bar_colors = [PALETTE["blue"], PALETTE["orange"], PALETTE["cyan"], PALETTE["purple"]]
    axe.bar(x, distance, width=0.62, color=bar_colors, edgecolor="white", linewidth=0.5)
    axe.set_xticks(x, ["Observed", "Optimized", "Observed\n+ LDES", "Optimized\n+ LDES"])
    axe.set_ylim(0, max(distance) * 1.42)
    for xi, value in zip(x, distance):
        axe.text(xi, value + 0.025 * max(distance), f"{value:.2f}", ha="center", va="bottom", fontsize=5.6)
    axe.set_ylabel("Minimum additional balancing capacity (GW)")
    axe.set_title("Full-year hourly feasibility gap of fixed portfolios", loc="left")
    clean_axis(axe, "y")
    axe.text(0.995, 0.91,
             "All four have positive hourly feasibility gaps\nZero would certify an unaugmented fixed portfolio",
             transform=axe.transAxes, ha="right", va="top", fontsize=5.3, color=PALETTE["grey"])
    axe.text(0.0, -0.34,
             "The metric minimizes technology-neutral firm-supply and surplus-absorption capacity added only for diagnosis; it is not an actual build or cost (Fig. S13).",
             transform=axe.transAxes, ha="left", fontsize=5.1, color=PALETTE["grey"])

    for axis, label in zip((axa, axb, axe), "abe"):
        panel_label(axis, label)
    for axis, label in ((axc, "c"), (axd, "d")):
        axis.text(
            -0.12, 1.215, label, transform=axis.transAxes,
            fontweight="bold", fontsize=8.2, va="bottom", ha="left",
            color=PALETTE["dark"], clip_on=False,
        )
    fig.canvas.draw()
    map_box=axc.get_position(); top_box=axa.get_position()
    axa.set_position([map_box.x0, top_box.y0, map_box.width, top_box.height])
    d_box=axd.get_position()
    axd.set_position([d_box.x0, map_box.y0, d_box.width, map_box.height])
    fig.canvas.draw()
    _assert_x_aligned(axa, axc, "Fig7a/Fig7c")
    y_mismatch=max(abs(axc.get_position().y0-axd.get_position().y0),
                   abs(axc.get_position().y1-axd.get_position().y1))
    if y_mismatch > 1.0e-6:
        raise RuntimeError(f"Fig7c/Fig7d vertical frame mismatch {y_mismatch:.3e}")
    save_figure(fig, FIG_MAIN / "Fig7_future_pathway_and_validation_boundaries")


def _heatmap(axis, frame: pd.DataFrame, *, column: str, row_order: list[str], columns: list, title: str, xlabel: str) -> None:
    table = frame.pivot_table(index="scenario", columns=column, values="power_share_pct", aggfunc="sum", fill_value=0.0)
    table = table.reindex(index=row_order, columns=columns, fill_value=0.0)
    # Static target-year portfolios do not contain a construction trajectory.
    static_rows = []
    if column == "build_year":
        if "layer" not in frame.columns:
            raise ValueError("Timing plots require an explicit analysis layer")
        static_ids = set(frame.loc[frame.layer.eq("A"), "scenario"])
        static_rows = [i for i, scenario in enumerate(row_order) if scenario in static_ids]
        table.loc[list(static_ids & set(table.index)), :] = np.nan
    cmap = plt.get_cmap("Blues").copy()
    cmap.set_bad("#e8e8e8")
    artist = axis.imshow(table.to_numpy(float), aspect="auto", cmap=cmap, vmin=0, vmax=100)
    for i in static_rows:
        axis.text((len(columns)-1)/2, i, "N/A", ha="center", va="center", fontsize=7.2, color="#555")
    axis.set_xticks(np.arange(len(columns)), [str(x) for x in columns], rotation=38, ha="right")
    axis.set_yticks([])
    axis.set_xlabel(xlabel)
    axis.set_title(title, loc="left")
    axis.tick_params(length=0)
    for spine in axis.spines.values():
        spine.set_visible(False)
    cax = axis.inset_axes([0.58, 1.025, 0.40, 0.025])
    bar = axis.figure.colorbar(artist, cax=cax, orientation="horizontal", ticks=[0, 50, 100])
    bar.ax.tick_params(labelsize=4.6, length=1.3, pad=0.8)
    bar.set_label("Power share (%)", fontsize=5.0, labelpad=0.8)
    bar.ax.xaxis.set_label_position("top")
    bar.outline.set_linewidth(0.35)


def plot_figs14(metrics: pd.DataFrame, technology: pd.DataFrame, timing: pd.DataFrame) -> None:
    metrics = metrics.sort_values("scenario_order").reset_index(drop=True)
    row_order = metrics.scenario.astype(str).tolist()
    y = np.arange(len(metrics))
    colors = metrics.layer.map(LAYER_COLORS).tolist()
    fig = plt.figure(figsize=(7.0866, 9.75))
    gs = fig.add_gridspec(2, 2, left=0.255, right=0.98, bottom=0.16, top=0.925, wspace=0.34, hspace=0.31)
    axa, axb, axc, axd = [fig.add_subplot(gs[i, j]) for i in range(2) for j in range(2)]

    power = metrics.power_gw.to_numpy(float)
    axa.barh(y, power, color=colors, edgecolor="white", linewidth=0.35)
    axa.set_yticks(y, metrics.scenario_label.astype(str))
    axa.invert_yaxis()
    axa.set_xscale("log")
    axa.set_xlabel("Total new power (GW, log scale)")
    axa.set_title("All 26 future-storage configurations", loc="left")
    clean_axis(axa, "x")

    duration = metrics.duration_h.to_numpy(float)
    for yi, value, color in zip(y, duration, colors):
        axb.plot([0, value], [yi, yi], color=PALETTE["light_grey"], linewidth=0.9)
        axb.scatter(value, yi, s=19, color=color, edgecolor="white", linewidth=0.35, zorder=3)
    axb.set_yticks([])
    axb.invert_yaxis()
    axb.set_xlim(0, max(duration) * 1.08)
    axb.set_xlabel("Power-weighted duration (h)")
    axb.set_title("Duration structure", loc="left")
    clean_axis(axb, "x")

    tech_columns = [tech for tech in TECH_ORDER if tech in set(technology.technology_group.astype(str))]
    _heatmap(axc, technology, column="technology_group", row_order=row_order, columns=tech_columns,
             title="Technology composition", xlabel="Technology-duration option")
    years = sorted(pd.to_numeric(timing.build_year, errors="raise").astype(int).unique().tolist())
    _heatmap(axd, timing, column="build_year", row_order=row_order, columns=years,
             title="Build-timing composition", xlabel="Build year")

    layer_handles = [Line2D([0], [0], marker="s", linestyle="none", markerfacecolor=LAYER_COLORS[layer],
                            markeredgecolor="none", label=label)
                     for layer, label in (("A", "2033 configurations"), ("B", "Multi-period pathways"),
                                          ("C", "Equal-horizon comparison"))]
    fig.legend(handles=layer_handles, ncol=3, loc="upper center", bbox_to_anchor=(0.60, 0.978),
               columnspacing=1.1, handletextpad=0.35)
    for axis, label in zip((axa, axb, axc, axd), "ABCD"):
        panel_label(axis, label)
    fig.text(0.255, 0.030,
             "The same 26 configurations and ordering are retained across panels.\n"
             "The 2033 configurations are annual target-year comparisons; multi-period and equal-horizon pathways span 2028–2058.\n"
             "Expanded* is a boundary-condition scenario.",
             fontsize=5.0, ha="left", va="bottom", linespacing=1.24)
    save_figure(fig, FIG_SUPP / "FigS14_future_storage_extended_robustness")


def main() -> None:
    configure()
    pair_metrics = read(TABLE_V31, "fig6_layer_a_pair_metrics.csv")
    adaptive_zone = read(TABLE_V31, "fig6_adaptive_zone_portfolios.csv")
    timing = read(TABLE_V31, "fig7_core_timing_by_technology.csv")
    core_zone = read(TABLE_V31, "fig7_core_zone_difference.csv")
    contexts = read(TABLE_V31, "fig7_context_pair_metrics.csv")
    metrics = read(TABLE_V31, "figS14_all26_case_metrics.csv")
    technology = read(TABLE_V31, "figS14_all26_technology_shares.csv")
    timing_all = read(TABLE_V31, "figS14_all26_timing_shares.csv")
    full8760 = read(TABLE_FULL8760, "full8760_certificate_summary.csv")
    plot_fig6(pair_metrics, adaptive_zone)
    plot_fig7(timing, core_zone, contexts, full8760)
    plot_figs14(metrics, technology, timing_all)
    print("V31 future-storage publication figures: PASS")


if __name__ == "__main__":
    main()
