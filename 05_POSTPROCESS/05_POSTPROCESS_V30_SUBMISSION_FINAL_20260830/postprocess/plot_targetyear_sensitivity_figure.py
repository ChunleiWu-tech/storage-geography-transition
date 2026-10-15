#!/usr/bin/env python3
"""Render Supplementary Fig. 12 from V17T2R5 audited target-year tables."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

from ne_style import PALETTE, clean_axis, configure, panel_label, save_figure
from targetyear_sensitivity_common import PAIR_LABELS, PAIR_ORDER
from v17t5_paths import FIG_SUPP, TABLE_TARGETYEAR


def read(name: str) -> pd.DataFrame:
    path = TABLE_TARGETYEAR / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def short_pair(pair_id: str) -> str:
    return {
        "TY2028_CHRONO": "2028\nlinked SOC",
        "TY2033_CHRONO": "2033\nlinked SOC",
        "TY2033_CHRONO_LDES": "2033 linked SOC\n+ tech-specific LDES",
        "TY2033_CHRONO_1H": "2033 linked SOC\n1 h discretization",
    }[pair_id]


def matrix_pair(pair_id: str) -> str:
    return {
        "TY2028_CHRONO": "2028\n4 h",
        "TY2033_CHRONO": "2033\n4 h",
        "TY2033_CHRONO_LDES": "2033 + LDES\n4 h",
        "TY2033_CHRONO_1H": "2033\n1 h",
    }[pair_id]


def residual_pair(pair_id: str) -> str:
    return {
        "TY2028_CHRONO": "2028 4 h",
        "TY2033_CHRONO": "2033 4 h",
        "TY2033_CHRONO_LDES": "2033 + LDES",
        "TY2033_CHRONO_1H": "2033 1 h",
    }[pair_id]


def signed_stacked_bar(axis, components: pd.DataFrame, pairs: pd.DataFrame) -> None:
    component_order = ["Generation capacity", "Storage energy", "Transmission", "Fuel", "Other system"]
    colors = {
        "Generation capacity": PALETTE["navy"],
        "Storage energy": PALETTE["teal"],
        "Transmission": PALETTE["purple"],
        "Fuel": PALETTE["orange"],
        "Other system": PALETTE["grey"],
    }
    y = np.arange(len(PAIR_ORDER))
    positive = np.zeros(len(PAIR_ORDER))
    negative = np.zeros(len(PAIR_ORDER))
    for component in component_order:
        values = []
        for pair_id in PAIR_ORDER:
            row = components.loc[(components["pair_id"] == pair_id) & (components["component"] == component)]
            if len(row) != 1:
                raise ValueError(f"Missing unique cost component {component} for {pair_id}")
            values.append(float(row["observed_minus_optimized_million_usd_per_yr"].iloc[0]))
        values = np.asarray(values)
        left = np.where(values >= 0, positive, negative)
        axis.barh(y, values, left=left, height=0.56, color=colors[component], label=component, zorder=3)
        positive += np.where(values >= 0, values, 0)
        negative += np.where(values < 0, values, 0)
    penalties = pairs.set_index("pair_id").loc[PAIR_ORDER, "annual_location_penalty_million_usd_per_yr"].to_numpy(float)
    extent_min = float(np.min(negative))
    extent_max = float(np.max(positive))
    extent_span = max(extent_max - extent_min, 1.0)
    for yi, value in zip(y, penalties):
        # Always place the net label to the right of the positive stack. This
        # keeps negative-net annotations inside the plotting area and away
        # from the long scenario labels on the left.
        x_text = positive[yi] + 0.025 * extent_span
        axis.text(x_text, yi, f"Net {value:+.1f}", ha="left", va="center", fontsize=5.7)
    axis.axvline(0, color=PALETTE["dark"], lw=0.65)
    axis.set_xlim(extent_min - 0.08 * extent_span, extent_max + 0.24 * extent_span)
    axis.set_yticks(y, [short_pair(p) for p in PAIR_ORDER])
    axis.invert_yaxis()
    axis.set_xlabel("Reconstructed standardized − optimized annual cost\n(million USD yr$^{-1}$)")
    clean_axis(axis, grid_axis="x")
    axis.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.50, 1.01), columnspacing=1.0, handlelength=1.2)


def row_normalized_matrix(axis, frame: pd.DataFrame, metric_order: list[str], title_units: bool = True) -> None:
    pivot = frame.pivot(index="metric", columns="pair_id", values="observed_minus_optimized").reindex(index=metric_order, columns=PAIR_ORDER)
    units = frame.drop_duplicates("metric").set_index("metric")["unit"].reindex(metric_order)
    values = pivot.to_numpy(float)
    scaled = np.zeros_like(values)
    for i in range(values.shape[0]):
        maxabs = np.nanmax(np.abs(values[i]))
        scaled[i] = values[i] / maxabs if np.isfinite(maxabs) and maxabs > 0 else 0.0
        # Display tolerance is half the published 0.01 Mt CO2/yr precision.
        # Preserve values for labels and the source table; neutralize colour only.
        if metric_order[i] == "Net emissions":
            scaled[i, np.abs(values[i]) < 0.005] = 0.0
    image = axis.imshow(scaled, cmap="RdBu_r", norm=TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1), aspect="auto")
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            value = values[i, j]
            if abs(value) < 5e-4:
                text = "\u22480"
            elif abs(value) >= 100:
                text = f"{value:+.0f}"
            elif abs(value) >= 10:
                text = f"{value:+.1f}"
            elif abs(value) >= 1:
                text = f"{value:+.2f}"
            else:
                text = f"{value:+.3f}"
            color = "white" if abs(scaled[i, j]) > 0.58 else PALETTE["dark"]
            axis.text(j, i, text, ha="center", va="center", fontsize=5.5, color=color)
    labels = [f"{metric}\n({units.loc[metric]})" if title_units else metric for metric in metric_order]
    axis.set_yticks(np.arange(len(metric_order)), labels)
    axis.set_xticks(np.arange(len(PAIR_ORDER)), [matrix_pair(p) for p in PAIR_ORDER])
    axis.tick_params(axis="x", length=0, pad=2, labelsize=5.5)
    axis.tick_params(axis="y", length=0, pad=2, labelsize=5.5)
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.set_xticks(np.arange(-0.5, len(PAIR_ORDER), 1), minor=True)
    axis.set_yticks(np.arange(-0.5, len(metric_order), 1), minor=True)
    axis.grid(which="minor", color="white", linewidth=1.0)
    axis.tick_params(which="minor", bottom=False, left=False)
    return image


def main() -> None:
    configure()
    pairs = read("targetyear_pairwise_observed_minus_optimal.csv")
    components = read("figS12b_cost_component_decomposition.csv")
    investment = read("figS12c_compensatory_investment.csv")
    operation = read("figS12d_operational_response.csv")
    attenuation = read("targetyear_ldes_attenuation.csv").iloc[0]
    ldes_mix = read("figS12c_ldes_technology_mix.csv")

    pairs = pairs.set_index("pair_id").loc[PAIR_ORDER].reset_index()
    fig = plt.figure(figsize=(7.0866, 6.05))
    gs = fig.add_gridspec(2, 2, left=0.155, right=0.975, bottom=0.18, top=0.925, wspace=0.42, hspace=0.52)
    axa = fig.add_subplot(gs[0, 0])
    axb = fig.add_subplot(gs[0, 1])
    axc = fig.add_subplot(gs[1, 0])
    axd = fig.add_subplot(gs[1, 1])

    # a, exact annual location penalties under linked SOC and LDES pressure test.
    y = np.arange(len(PAIR_ORDER))
    penalties = pairs["annual_location_penalty_million_usd_per_yr"].to_numpy(float)
    colors = [PALETTE["blue"], PALETTE["blue"], PALETTE["purple"], PALETTE["teal"]]
    axa.barh(y, penalties, height=0.56, color=colors, zorder=3)
    axa.axvline(0, color=PALETTE["dark"], lw=0.65)
    axa.set_yticks(y, [short_pair(p) for p in PAIR_ORDER])
    axa.invert_yaxis()
    axa.set_xlabel("Annual location penalty (million USD yr$^{-1}$)")
    clean_axis(axa, grid_axis="x")
    span = max(np.max(np.abs(penalties)), 1.0)
    for yi, (_, row) in enumerate(pairs.iterrows()):
        value = float(row["annual_location_penalty_million_usd_per_yr"])
        fraction = 100 * float(row["annual_location_penalty_fraction_of_optimized"])
        # Large bars carry a high-contrast internal label; small bars use an
        # external label toward the centre. This avoids both the long y labels
        # on the left and the neighbouring panel on the right.
        if abs(value) >= 0.18 * span:
            x_text = value - np.sign(value) * 0.025 * span
            ha = "right" if value > 0 else "left"
            color = "white"
        else:
            x_text = value + 0.025 * span
            ha = "left"
            color = PALETTE["dark"]
        axa.text(
            x_text, yi, f"{value:+.1f}\n({fraction:+.3f}%)",
            ha=ha, va="center", fontsize=5.8, color=color,
        )
    retention = float(attenuation["ldes_retention_fraction"])
    attenuation_fraction = float(attenuation["ldes_attenuation_fraction"])
    axa.text(
        0.02,
        -0.28,
        f"LDES retention: {retention*100:.1f}%  |  attenuation: {attenuation_fraction*100:+.1f}%",
        transform=axa.transAxes,
        ha="left",
        va="top",
        fontsize=5.7,
        color=PALETTE["dark"],
    )

    # b, exact decomposition of observed minus optimized cost.
    signed_stacked_bar(axb, components, pairs)

    # c, show only materially changing investment metrics. Invariant zero rows
    # are excluded from the matrix and LDES zero deployment is stated exactly.
    material = (
        investment.groupby("metric")["observed_minus_optimized"]
        .apply(lambda values: float(np.nanmax(np.abs(pd.to_numeric(values, errors="coerce")))))
    )
    metric_order = [
        metric
        for metric in [
            "Battery power", "Battery energy", "Pumped-hydro power",
            "Pumped-hydro energy", "LDES power", "LDES energy", "Transmission build",
        ]
        if material.get(metric, 0.0) > 5e-4
    ]
    if not metric_order:
        metric_order = ["Battery power"]
    row_normalized_matrix(
        axc,
        investment,
        metric_order,
    )
    mix_totals = ldes_mix.groupby("legacy_allocation_mode")["build_power_mw"].sum()
    observed_ldes_gw = float(mix_totals.get("observed_standardized", 0.0)) / 1000.0
    optimized_ldes_gw = float(mix_totals.get("optimized_reallocation", 0.0)) / 1000.0
    if max(abs(observed_ldes_gw), abs(optimized_ldes_gw)) <= 1e-9:
        ldes_note = "Technology-specific LDES: no deployment in either member (0 GW)."
    else:
        deployed_flag = ldes_mix["deployed"].map(lambda value: str(value).lower() in {"true", "1"})
        deployed = sorted(ldes_mix.loc[deployed_flag, "technology"].astype(str).unique())
        ldes_note = (
            f"LDES deployment: {observed_ldes_gw:.2f}/{optimized_ldes_gw:.2f} GW "
            f"(reconstructed/optimized); deployed: {', '.join(deployed) if deployed else 'none'}."
        )
    axc.text(
        0.0, -0.25,
        "Exact reconstructed-standardized − optimized values; invariant zero rows omitted.\n" + ldes_note,
        transform=axc.transAxes, fontsize=5.4, ha="left", va="top", linespacing=1.25,
    )

    # d, non-degenerate operational/system response plus chronology certificate.
    # Gross charging/discharging totals are excluded because alternative
    # cost-equivalent dispatch solutions make them degeneracy-sensitive.
    row_normalized_matrix(
        axd,
        operation,
        ["VRE curtailment", "Net emissions", "Average system cost"],
    )
    residual_chunks = []
    for row in pairs.itertuples(index=False):
        residual_chunks.append(
            f"{residual_pair(row.pair_id)}: "
            f"{row.max_pair_soc_linkage_residual_mwh:.2e}/{row.max_pair_soc_bound_violation_mwh:.2e}"
        )
    residual_lines = [
        "Max |SOC-link residual| / bound violation (MWh)",
        ";  ".join(residual_chunks[:2]),
        ";  ".join(residual_chunks[2:]),
    ]
    axd.text(
        0.0, -0.21,
        "\n".join(residual_lines),
        transform=axd.transAxes, fontsize=4.7, ha="left", va="top", linespacing=1.12
    )

    panel_label(axa, "a", x=-0.16, y=1.08)
    panel_label(axb, "b", x=-0.16, y=1.08)
    panel_label(axc, "c", x=-0.16, y=1.08)
    panel_label(axd, "d", x=-0.16, y=1.08)

    save_figure(fig, FIG_SUPP / "FigS12_targetyear_linked_chronology_ldes")
    print("Supplementary Fig. 12 rendered from audited V17T2R5 source tables.")


if __name__ == "__main__":
    main()
