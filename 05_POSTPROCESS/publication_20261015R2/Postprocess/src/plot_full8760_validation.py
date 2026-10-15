#!/usr/bin/env python3
"""Render the complete supplementary full-year hourly-feasibility figure."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from ne_style import PALETTE, clean_axis, configure, panel_label, save_figure
from v17t5_paths import FIG_SUPP, TABLE_FULL8760


def read(name: str) -> pd.DataFrame:
    path = TABLE_FULL8760 / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def main() -> None:
    configure()
    summary = read("full8760_certificate_summary.csv")
    components = read("full8760_robustness_components.csv")
    zones = read("full8760_zone_robustness.csv")
    gates = read("full8760_certificate_gate_matrix.csv")
    order = summary["case_label"].tolist()
    display_order = [label.replace(" inheritance", "") for label in order]

    fig = plt.figure(figsize=(7.0866, 7.00))
    gs = fig.add_gridspec(2, 2, left=0.145, right=0.975, bottom=0.19, top=0.91, wspace=0.50, hspace=0.47)
    axa = fig.add_subplot(gs[0, 0]); axb = fig.add_subplot(gs[0, 1])
    axc = fig.add_subplot(gs[1, 0]); axd = fig.add_subplot(gs[1, 1])

    # a. Minimum added diagnostic capacity; the axis starts at zero because
    # absolute magnitude is the claim.
    vals = summary["total_robustness_distance_mw"].to_numpy(float) / 1000.0
    colors = [PALETTE["blue"], PALETTE["orange"], PALETTE["cyan"], PALETTE["purple"]]
    y = np.arange(len(order))
    axa.barh(y, vals, color=colors, edgecolor=PALETTE["dark"], linewidth=0.45)
    axa.set_yticks(y, display_order); axa.invert_yaxis(); axa.set_xlim(left=0)
    for yi, value in zip(y, vals):
        axa.text(value, yi, f" {value:.2f}", va="center", ha="left", fontsize=5.8)
    axa.set_xlabel("Minimum additional balancing capacity (GW)")
    axa.set_title("Full-year hourly feasibility gap of fixed portfolios", loc="left")
    clean_axis(axa, "x")

    # b. Technology-neutral diagnostic-capacity decomposition.
    pivot = components.pivot(index="case_label", columns="component", values="robustness_distance_mw").reindex(order) / 1000.0
    left = np.zeros(len(pivot))
    component_labels = {
        "Ideal firm capacity": "Firm-supply capacity",
        "Ideal surplus absorption": "Surplus-absorption capacity",
    }
    for component, color in (("Ideal firm capacity", PALETTE["navy"]), ("Ideal surplus absorption", PALETTE["sand"])):
        values = pivot.get(component, pd.Series(0.0, index=pivot.index)).to_numpy(float)
        axb.barh(y, values, left=left, color=color, edgecolor="white", linewidth=0.45,
                 label=component_labels[component])
        left += values
    axb.set_yticks(y, display_order); axb.invert_yaxis(); axb.set_xlim(left=0)
    axb.set_xlabel("Diagnostic capacity component (GW)")
    axb.set_title("Firm-supply and surplus-absorption components", loc="left")
    handles, labels = axb.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.758, 0.982),
               ncol=1, borderaxespad=0.0, handlelength=1.4)
    clean_axis(axb, "x")

    # c. Largest zone contributions, common zone set across all cases.
    zone_totals = zones.groupby("LOAD_ZONE", as_index=True)["TotalRobustnessDistance_MW"].max().sort_values(ascending=False)
    top = zone_totals.head(12).index
    heat = zones.loc[zones["LOAD_ZONE"].isin(top)].pivot_table(
        index="LOAD_ZONE", columns="case_label", values="TotalRobustnessDistance_MW", aggfunc="sum", fill_value=0.0
    ).reindex(index=top, columns=order) / 1000.0
    vmax = max(float(np.nanmax(heat.to_numpy(float))), 1.0e-9)
    image = axc.imshow(heat.to_numpy(float), aspect="auto", cmap="Blues", vmin=0, vmax=vmax)
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            value = float(heat.iloc[i, j])
            axc.text(j, i, f"{value:.2f}", ha="center", va="center",
                     fontsize=4.7, color="white" if value > 0.55 * vmax else PALETTE["dark"])
    axc.set_xticks(np.arange(len(order)), [x.replace(" inheritance", "") for x in order], rotation=35, ha="right")
    axc.set_yticks(np.arange(len(heat.index)), heat.index)
    axc.set_title("Largest zonal contributions to the feasibility gap", loc="left")
    axc.set_xlabel("")
    axc.tick_params(length=0, labelsize=5.2)
    for spine in axc.spines.values(): spine.set_visible(False)
    fig.colorbar(image, ax=axc, fraction=0.04, pad=0.02).ax.tick_params(labelsize=5.0)

    # d. Route-aware numerical certification evidence, not another magnitude plot.
    # Some solver routes do not report the enhanced physical-audit field; these
    # cells are identified as not reported rather than being treated as failures.
    matrix = gates.pivot(index="case_label", columns="gate", values="passed").reindex(index=order)
    gate_order = ["Native OPTIMAL", "Primal/dual feasible", "Source lineage", "Physical audit", "Certificate"]
    gate_labels = ["Optimal solution", "Primal and dual feasibility", "Input consistency", "Additional physical checks", "Overall assessment"]
    matrix = matrix.reindex(columns=gate_order)
    state = matrix.map(
        lambda value: 0 if pd.isna(value) else (2 if str(value).lower() in {"true", "1"} else 1)
    )
    axd.imshow(
        state.to_numpy(int),
        cmap=ListedColormap([PALETTE["light_grey"], PALETTE["red"], PALETTE["teal"]]),
        vmin=0, vmax=2, aspect="auto",
    )
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            cell = state.iloc[i, j]
            label = "Unavailable" if cell == 0 else ("Satisfied" if cell == 2 else "Not satisfied")
            axd.text(j, i, label, ha="center", va="center", fontsize=4.7,
                     color=PALETTE["dark"] if cell == 0 else "white")
    axd.set_xticks(np.arange(len(gate_labels)), gate_labels, rotation=28, ha="right")
    axd.set_yticks(np.arange(len(order)), display_order)
    axd.set_title("Numerical solution evidence", loc="left")
    axd.tick_params(length=0, labelsize=5.1)
    for spine in axd.spines.values(): spine.set_visible(False)

    for axis, label in zip((axa, axb, axc, axd), "abcd"):
        panel_label(axis, label, x=-0.17, y=1.11)
    fig.text(
        0.145, 0.018,
        "The feasibility gap is the minimum technology-neutral firm-supply plus surplus-absorption capacity needed for hourly balance.\n"
        "Zero indicates hourly feasibility without augmentation; positive values are diagnostic distances, not actual builds or costs.\n"
        "An unavailable optional quality field for two solver routes does not alter the reported optimality or feasibility evidence.",
        ha="left", va="bottom", fontsize=5.0, color=PALETTE["dark"], linespacing=1.24,
    )
    save_figure(fig, FIG_SUPP / "FigS13_full8760_robustness_certificates")


if __name__ == "__main__":
    main()
