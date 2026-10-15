# V20 release notes

V20 is a clean additive successor to V19. It preserves the frozen scientific cores and adds a mandatory equal-evidence-horizon matched sensitivity instead of inventing unsupported post-2030 learning curves for VRFB/PSH.

Key changes:

- short Windows-safe package root and source-document names;
- authoritative evidence ledger with NLR/NREL 2025, PNNL v2024, DOE SI2030 Flow/PSH, and DOE 2024 LDES summary;
- DOE SI2030 LCOS/innovation results are explicitly **not** converted into whole-system CAPEX scalars;
- Layer C: `V20EH01_OBSERVED` / `V20EH02_OPTIMAL`, in which only future `V18_LFP_4h` CAPEX/FOM after 2030 is held at the source-direct NLR 2030 mid benchmark;
- cell-level audit proves the equal-horizon intervention changes only the declared 192 LFP cost rows per case;
- original low/mid/high battery-cost scenarios are verified to propagate into the future LFP candidate;
- resume-safe Layer B 16-case and Layer C 2-case runners using strict result fingerprints;
- run-first Phase 1 executes only 8 decisive cases before committing to the remaining 18;
- V20-specific numerical budgets use 12 h Barrier / 24 h fallback ceilings for difficult exact LPs without changing scientific inputs, objective, tolerances, or acceptance criteria;
- runtime static checks remain re-runnable after solver outputs exist; distribution-only cleanliness is enforced separately with `check_v20_package.py --release-clean`;
- figure design intentionally deferred until the required numerical results are complete; use one Fig. 6 if readable, otherwise split correction and dynamic pathway into Fig. 6 + Fig. 7.

Required V20 solve count: 8 + 16 + 2 = 26.

## V20 final run-first hardening

- Added explicit Python + Julia + Gurobi runtime gate and repaired inherited V17 source-load compatibility entrypoint.
- Added deeper frozen-input / numerical-certificate static audits before long solves.
- Added official DOE SI2030 Methodology, CAES and Bidirectional Hydrogen assessments to the evidence ledger; these remain claim-boundary / pressure-test evidence and are not converted into BAU CAPEX learning curves.
- Kept Fig.6 versus Fig.6+Fig.7 unresolved until 26/26 strict results are available.

## V20-HF1 provenance hotfix

- No scientific model, case input, technology portfolio, cost trajectory or solver policy changed.
- Re-synchronized `audits/PUBLICATION_SOURCE_FINGERPRINT.json` to the final packaged `OFFICIAL_SOURCE_ARCHIVE_INDEX.csv/.json`.
- Re-stamped dependent root prepared-case provenance metadata/fingerprints.
- Root publication source/case gate now passes 37/37 before long solver execution.



## V20-HF2 bounded science/runtime fix

- Fixed a real stock/future-build indexing conflict in the dynamic core: the `V18_Disable_Legacy_*_Future_Build` constraints now apply only for build years strictly after the 2023 stock anchor. The optimized equal-total legacy Battery reallocation in `SL02` is no longer forced simultaneously to national closure and zero.
- Hardened the generic `Disable_New_Battery_*` constraints with the same optimized-stock exception.
- Layer B/C headline runtime now reads an explicit `data/processed/v20_layer_b_runtime_contract.csv` and forces `intraday_cyclic + evidence_bounded`. This preserves the validated V17 chronology and isolates the future-portfolio intervention from chronology changes.
- Layer B/C strict acceptance now requires `storage_intermonth_soc_linked=false` and `storage_long_duration_claim_supported=false`; no intermonth/seasonal claim can be promoted from these runs.
- Runtime `storage_chronology_scope` is now emitted from the actual selected chronology mode instead of a hard-coded monthly label.
- Added an optional, non-publication `RUN_V20_B2_FEASIBILITY_ISOLATION_DIAGNOSTIC_1x10.bat` that separates the V17-native intraday baseline, chronology-only linked-month intervention, and linked-month + portfolio intervention, retaining built-in solver conflict evidence.
- No case scientific input CSV, technology portfolio, technology cost, policy, objective, or Layer-A target-year core is changed by HF2.

## V20-HF3 bounded PSH capacity-plan compatibility fix

HF3 supersedes HF2 for Layer B/C execution. The inherited `Hydro_Pumped` planning floor is now evaluated over the physical PSH family (legacy stock + V18 PSH 10 h/24 h designs) whenever the future portfolio is active. The shared provincial PSH resource ceiling is unchanged. No scientific input CSV or Layer-A target-year core changed. Use `RUN_V20_HF3_RETEST_B2C2_4_1x10.bat` before broader execution.
