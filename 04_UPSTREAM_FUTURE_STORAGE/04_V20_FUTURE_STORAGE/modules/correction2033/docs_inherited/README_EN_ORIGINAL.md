# V18R1 — Least-cost correction of inherited storage spatial lock-in

V18R1 is a **separate corrective-planning package** built on the byte-frozen V17T2R5 target-year scientific core. It does not replace or modify the V17 diagnostic experiment. V17 identifies whether inherited storage geography creates persistent system-level lock-in; V18R1 asks how much of that residual penalty can be repaired in 2033 by expanding the admissible future storage capacity, model-zone siting, technology and discrete-duration choices.

The frozen Julia core is `base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl`, SHA-256 `2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84`.

V18R1 is deliberately a **2033 single-target-year capacity-and-dispatch re-optimization**, not a 2025–2050 investment-timing pathway. It uses the frozen 12 representative months, 72 four-hour timepoints and monthly-linked SOC. Full-8760 validation remains a separate V17 layer. The inherited end-2025 storage stock remains the controlled starting legacy; the 2023 build-year label in the frozen SWITCH/V17 input structure is a model anchor and is not reinterpreted as a real-world 2023 stock estimate.

The package contains eight cases in four matched observed-versus-optimized legacy pairs: FC_BASE, FC_ADAPTIVE, FC_ADAPTIVE_TXFIXED and FC_EXPANDED_PRESSURE. Primary claims come only from FC01–FC04. The evidence-bounded adaptive portfolio retains the frozen V17 4 h Li-ion and base pumped hydro opportunity set and adds VRFB 10/24 h and resource-shared PSH 10/24 h candidates derived from the packaged PNNL v2024 2033 table. The expanded CAES/H2 portfolio is a pressure test only because no province-specific CAES/H2 resource ledger is supplied.

The primary repair metric is the reduction in the matched observed-minus-optimized legacy penalty when the adaptive storage opportunity set is enabled. It is a model difference-in-differences quantity, not an empirical historical causal estimate, and it is intentionally not clipped to [0,1].

A separate publication-quality six-panel **Main Fig. 6** is generated only after all eight results pass strict solver-native optimality, physical, chronology, export and lineage gates. It reports residual-lock-in repair, technology mix, province-by-technology allocation, province-level duration, compensatory investment shifts, and transmission/technology robustness. Outputs are PDF, SVG and 600-dpi PNG at native 180-mm width using the same Nature-family visual system as the existing postprocessor.

Recommended Windows workflow:

```cmd
call CHECK_V18R1_PACKAGE.bat
call CHECK_V18R1_RUNTIME.bat
call RUN_V18R1_PREPARE_ALL_8.bat
call RUN_V18R1_PRIMARY_4_1x10.bat
call RUN_V18R1_ROBUSTNESS_4_1x10.bat
call RUN_V18R1_BUILD_SUMMARY_AND_FIG6.bat
```

`TIME_LIMIT`, `ITERATION_LIMIT`, `NO_SOLUTION`, failed physical audits, incomplete exports or stale source/result fingerprints are never publication results.
