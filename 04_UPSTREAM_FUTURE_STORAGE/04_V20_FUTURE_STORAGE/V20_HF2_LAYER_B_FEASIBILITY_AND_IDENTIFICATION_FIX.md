# V20-HF2 Layer B feasibility + identification fix

This hotfix is a bounded scientific/runtime correction after two observed runtime outcomes:

- `SL01_OBSERVED_STANDARDIZED` under the former Layer-B monthly-linked/evidence-bounded runtime returned solver-native `INFEASIBLE`;
- `SL02_OPTIMAL_REALLOCATION` exposed a deterministic indexing conflict: its 2023 endogenous legacy Battery allocation was simultaneously required to satisfy national MW/MWh closure and forced to zero by a constraint named `Future_Build`.

HF2 does **not** reinterpret either result as a real-world infeasibility. Instead it restores the experiment's identification discipline:

1. 2023 legacy reallocation is stock, not future build. Future-build exclusions now apply only after 2023.
2. Layer B/C headline dynamic planning preserves the validated V17 `intraday_cyclic` chronology, so the only structural intervention is the future storage opportunity set.
3. A non-publication feasibility-isolation diagnostic compares `intraday_cyclic + portfolio disabled`, `monthly_linked + portfolio disabled`, and `monthly_linked + evidence_bounded`, retaining solver conflict exports when applicable.
4. Layer A remains unchanged and continues to use its independent 2033 monthly-linked correction design.

Publication boundary: Layer B/C can support future investment technology-duration-location-year pathway claims, but not intermonth/seasonal storage-operation claims.
