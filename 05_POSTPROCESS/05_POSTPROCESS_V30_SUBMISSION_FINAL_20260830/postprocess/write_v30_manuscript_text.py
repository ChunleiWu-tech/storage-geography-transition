#!/usr/bin/env python3
"""Write claim-bounded manuscript inserts for the new V20/FULL8760 evidence."""
from __future__ import annotations

import pandas as pd

from v17t5_paths import TABLE_FULL8760, TABLE_V20, TEXT_DIR


def main() -> None:
    correction = pd.read_csv(TABLE_V20 / "v20_layer_a_correction_metrics.csv")
    horizon = pd.read_csv(TABLE_V20 / "v20_evidence_horizon_penalty.csv")
    full = pd.read_csv(TABLE_FULL8760 / "full8760_certificate_summary.csv")
    metric = correction.set_index("metric")["value"]
    direct = float(horizon.loc[horizon.evidence_regime.eq("Evidence-direct"), "legacy_penalty_billion_usd"].iloc[0])
    equal = float(horizon.loc[horizon.evidence_regime.eq("Equal horizon"), "legacy_penalty_billion_usd"].iloc[0])
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    result = f"""# V30 results insert — future correction and continuous-8760 boundary

## Future-storage correction

In the 2033 matched target-year experiment, expanding the evidence-bounded storage opportunity set changed the observed-minus-optimized annual system-cost penalty from {metric['Baseline residual legacy lock-in']:.3f} to {metric['Adaptive residual legacy lock-in']:.3f} million USD yr−1. This corresponds to a correction value of {metric['Adaptive correction value']:.3f} million USD yr−1 and a repair fraction of {100*metric['Repair fraction']:.2f}%. The comparison is a controlled model difference-in-differences, not a historical causal estimate.

Across the 2028–2058 representative-period pathway, the core observed-minus-optimized present-value penalty was {direct:.3f} billion USD under the evidence-direct cost regime and {equal:.3f} billion USD under the equal-evidence-horizon sensitivity. These present-value quantities are not added to the annualized 2033 Layer-A quantities.

## Continuous-8760 validation boundary

All four R24P3 certificates passed. The fixed source portfolios had minimum ideal-local-flexibility robustness distances ranging from {full.total_robustness_distance_mw.min()/1000:.2f} to {full.total_robustness_distance_mw.max()/1000:.2f} GW under continuous cyclic non-leap 8760-hour chronology. A positive distance is a technology-neutral lower-bound feasibility gap; it is not an actual technology build, an economic system cost, or an original fixed-portfolio feasibility pass.

## Mandatory interpretation boundaries

- Layer A is a 2033 annualized-cost matched comparison; Layer B/C is a multi-period present-value comparison.
- Layer B/C uses V17-native intraday-cyclic representative chronology and does not support seasonal-operation claims.
- CAES/H2 expanded-portfolio cases are pressure tests and do not support headline province-siting claims.
- FULL8760 distance results validate a feasibility boundary and do not replace the economic pathway results.
"""
    (TEXT_DIR / "V30_NEW_EVIDENCE_RESULTS_DRAFT_EN.md").write_text(result, encoding="utf-8")
    captions = """# V30 new figure captions

**Fig. 6 | Future-storage correction of inherited spatial lock-in in 2033.** Panels report the matched observed-minus-optimized annualized-cost penalty, adaptive technology-duration and spatial choices, duration, compensatory portfolio shifts, and declared transmission/expanded-portfolio boundaries. Expanded CAES/H2 results are pressure-test-only.

**Fig. 7 | Future pathway and chronology-validation boundaries.** Panels separate the 2028–2058 representative-period investment pathway and matched present-value penalties from the continuous-8760 fixed-portfolio robustness certificate. The FULL8760 distance is a technology-neutral feasibility-gap measure, not an actual build or cost.

**Fig. S13 | Complete continuous-8760 robustness certificates.** Total minimum ideal-local-flexibility distances, firm/absorption decomposition, largest model-zone contributions, and strict release gates for the four fixed source portfolios.

**Fig. S14 | Extended future-storage robustness.** Complete Layer-A matched pairs, observed-inheritance portfolio variants, optimized-inheritance build timing, and the technology-mix response to the equal-evidence-horizon sensitivity.
"""
    (TEXT_DIR / "V30_NEW_FIGURE_CAPTIONS_EN.md").write_text(captions, encoding="utf-8")
    print("V30 manuscript-ready text: PASS")


if __name__ == "__main__":
    main()
