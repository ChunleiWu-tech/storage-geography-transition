"""Neutral accounting summaries and quantitative solver diagnostics."""
import numpy as np
import pandas as pd


def apply(fig, panels, key, output):
    if key == 'FigS02':
        nodes = pd.read_csv(output / 'Postprocess/tables/main/fig1a_legacy_nodes.csv')
        power = nodes.existing_new_storage_power_mw
        energy = nodes.existing_new_storage_energy_mwh
        duration = nodes.existing_duration_h
        residual = (energy - power * duration).abs().max() / 1000
        ax = panels[1]
        ax.clear()
        ax.set_position([.61, .19, .36, .59])
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
        rows = [
            ('Coverage', f'{len(nodes)} / {len(nodes)} zones'),
            ('Common duration', f'{energy.sum()/power.sum():.4f} h'),
            ('Duration spread', '< 1e−12 h' if duration.max()-duration.min() < 1e-12 else f'{duration.max()-duration.min():.3g} h'),
            ('Maximum accounting\nresidual', f'{residual:.3g} GWh'),
        ]
        for y, (label, value) in zip([.84, .62, .40, .16], rows):
            ax.text(0, y, label, va='center', ha='left', fontsize=7.2, linespacing=1.35)
            ax.text(1, y, value, va='center', ha='right', fontsize=7.2)
            ax.plot([0, 1], [y-.10, y-.10], color='#cccccc', lw=.5)
        ax.text(-.10, 1.23, 'b', transform=ax.transAxes, fontsize=9, weight='bold')

    if key == 'FigS13':
        quality = pd.read_csv(output / 'Postprocess/tables/full8760_validation/full8760_numerical_quality.csv')
        summary = pd.read_csv(output / 'Postprocess/tables/full8760_validation/full8760_certificate_summary.csv')
        gates = pd.read_csv(output / 'Postprocess/tables/full8760_validation/full8760_certificate_gate_matrix.csv')
        quality = quality.set_index('scenario').loc[summary.scenario]
        optimal = gates[gates.gate.eq('Native OPTIMAL')].set_index('scenario').loc[summary.scenario, 'passed']
        assert optimal.astype(str).str.lower().eq('true').all()
        columns = ['primal_dual_relative_gap', 'gurobi_constr_vio', 'objective_readback_error_mw']
        values = quality[columns].to_numpy(float)
        assert np.isfinite(values).all() and (values >= 0).all()
        ax = panels[3]
        ax.clear()
        ax.set_position([.705, .17, .28, .28])
        ax.set_xlim(-.5, 2.5); ax.set_ylim(3.6, -.7)
        for i in range(4):
            if i % 2 == 0:
                ax.axhspan(i-.46, i+.46, color='#f1f3f5', zorder=0)
            for j in range(3):
                ax.text(j, i, f'{values[i,j]:.2e}', ha='center', va='center', fontsize=7.2)
        ax.set_yticks(range(4), ['Existing', 'Reference', 'Existing + LDES', 'Reference + LDES'])
        ax.set_xticks(range(3), ['Relative\nprimal–dual\ngap', 'Maximum\nconstraint\nviolation', 'Objective\nresidual\n(MW)'])
        ax.tick_params(axis='both', length=0, labelsize=7.2, pad=6)
        ax.xaxis.tick_top()
        for spine in ax.spines.values(): spine.set_visible(False)
        ax.text(-.15, 1.25, 'd', transform=ax.transAxes, fontsize=9, weight='bold')
        # The other panels retain their source arrays, labels and units.
        panels[2].set_position([.16, .17, .32, .28])
        for text in panels[2].texts:
            if text.get_text() == 'c': text.set_position((-.10, 1.25))
        for axis in fig.axes:
            if hasattr(axis, '_colorbar'):
                axis.set_position([.502, .195, .012, .225])
