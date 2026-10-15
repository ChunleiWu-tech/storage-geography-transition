# V20-HF3 active entrypoints

Recommended targeted retest after the HF2 Layer-B infeasibility:

1. `CHECK_V20_MANIFEST.bat` (fresh extraction only)
2. `CHECK_V20_STATIC.bat`
3. `CHECK_V20_RUNTIME.bat`
4. `RUN_V20_HF3_RETEST_B2C2_4_1x10.bat`

The HF3 ZIP already ships validated prepared cases, so the targeted B2+C2 retest does not require `PREP_V20.bat` first. Use `PREP_V20.bat` only when you intentionally want a clean rebuild of all prepared cases. Do not copy HF1/HF2 result folders into HF3.

After B2+C2 strict PASS, resume the standard run-first sequence:

- `RUN_V20_PHASE1_CORE_8_1x10.bat`
- `RUN_V20_REMAINING_18_1x10.bat`
- `BUILD_V20_RESULTS.bat`

Granular resume-safe entries:
- `RUN_V20_A4_PRIMARY_1x10.bat`
- `RUN_V20_A8_1x10.bat`
- `RUN_V20_B2_CORE_1x10.bat`
- `RUN_V20_B16_1x10.bat`
- `RUN_V20_C2_EQUAL_HORIZON_1x10.bat`

Optional diagnostics only (never publication-promoted):
- `RUN_V20_B2_FEASIBILITY_ISOLATION_DIAGNOSTIC_1x10.bat`

Layer B/C headline runtime remains locked by `data/processed/v20_layer_b_runtime_contract.csv` to `intraday_cyclic + evidence_bounded`. `V20_ENV_DEFAULTS.bat` controls numerical budgets only and does not change scientific inputs, objective, constraints, solver optimality tolerances, or publication acceptance rules.
