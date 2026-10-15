# China storage planning — V17

V17 is the clean publication-strict release in which the **solver-certified stage-1 economic optimum is the formal result**. Stage 2 is retained only as an optional experiment that attempts to select a sparser representation from a highly degenerate optimal face. Failure or non-convergence of that experiment does not invalidate a certified, constraint-feasible stage-1 solution.

## Formal solver and release architecture

1. **Stage 1: official economic planning solution.** The LP minimizes the scaled economic objective `SystemCost / 1e6`. The primary route uses Gurobi Barrier (`Method=2`, `Crossover=0`, `LPWarmStart=0`, `BarConvTol=1e-8`).
2. **Solver certification.** Release requires MOI `OPTIMAL`, feasible primal and dual result states, at least one result, Gurobi native status/certificate checks, and consistency between the native and scaled economic objectives. `ObjBound` and the reconstructed JuMP dual objective remain non-blocking diagnostics.
3. **Model feasibility and export audits.** Unit-aware physical constraints, no-CDR scope, legacy-storage allocation, planning reserve coverage, and strict output closure remain mandatory.
4. **Stage 2: optional sparse-face diagnostic.** PStart/primal-simplex, concurrent, Barrier, and dual cleanup profiles remain available only through explicit diagnostic execution. They may test whether a lower-throughput gross-flow representation can be found within the economic band and aggregate investment locks. They are not part of the official batch fallback tree and cannot replace, approve, or reject the stage-1 result.
5. **Degeneracy disclosure.** Gross unit/timepoint dispatch, simultaneous charge/discharge components, directional transmission flows, and reserve-transfer flows are marked `DegeneracySensitive=true` and `OperationalMechanismInterpretationAllowed=false`. They may be used only for accounting reconstruction, aggregate balances, and reproducibility—not for cycling, routing, congestion-causality, or operating-mechanism claims.
6. **Publication-valid outputs.** Investment, capacity, retirement, cost, policy, annual aggregate, net-balance, and constraint-closure outputs come from the official stage-1 solution and remain release-eligible after strict audits.
7. **Failure-safe implementation.** No basis files, `VBasis`, `CBasis`, `CrossoverBasis`, `DStart`, generic JuMP starts, or serialized PStart are used. Non-finite diagnostics are written as JSON `null`. Julia top-level-only declarations are statically audited, and the production source is actually loaded before a solve.

The study is intentionally no-CDR. `NBCCS info rows = 0` and `NBCCS limits rows = 0` are expected when `allow_nbccs=false`; fossil-generator CCS remains scenario-controlled.

## First local run

```powershell
$env:JULIA_EXE = "C:\path\to\julia.exe"
$env:V17_SOLVER_THREADS = "10"
Remove-Item Env:V17_PYTHON -ErrorAction SilentlyContinue

.\CHECK_V17_RELEASE.bat
.\CHECK_V17_SOURCE_LOAD.bat
.\CHECK_V17_RUNTIME.bat
.\RUN_V17_SL00_PRIMARY_ONLY_1x10.bat
```

The primary run publishes the certified stage-1 solution directly. When the primary stage-1 algorithm itself is not certified, the controlled launcher retries alternative **stage-1 solver algorithms** in fresh Julia processes:

```powershell
.\RUN_V17_SL00_CONTROLLED_1x10.bat
```

After SL00 passes:

```powershell
.\RUN_V17_SPATIAL_LEGACY_FULL_1x10.bat
```

An optional cleanup experiment is isolated from the release chain:

```powershell
.\RUN_V17_SL00_SPARSE_FACE_DIAGNOSTIC_1x10.bat
```

Its output is diagnostic-only and is never promoted to `outputs/<scenario>__main`.
