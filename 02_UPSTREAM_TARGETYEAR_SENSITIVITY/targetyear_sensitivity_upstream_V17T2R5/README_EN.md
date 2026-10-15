# Target-year sensitivity upstream: eight source-locked linked-SOC cases

Data version: `NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2`

This standalone package performs independent 2028 and 2033 capacity-and-dispatch re-optimizations with state of charge (SOC) linked across twelve representative months. Four matched pairs test the inherited-storage location effect at 2028 and 2033, a technology-specific long-duration energy storage (LDES) portfolio at 2033, and a one-hour representative-day discretization at 2033.

The analysis is not a full multi-period transition path and not an 8,760-hour continuous chronological simulation. The 2033 cases do not inherit endogenous 2028 builds. The one-hour pair is a bounded reconstruction that exactly preserves each current four-hour block mean; it is a temporal-discretization sensitivity only.

Within every pair, national inherited new-type storage is fixed at 135,930 MW and 351,120 MWh (`2.583094239682189 h`). All physical inputs are file-identical between the reference and optimized members except the inherited-storage spatial allocation and its policy file.

The LDES pair enables eight discrete technology-duration options: CAES at 10, 24 and 100 h; vanadium redox flow batteries at 10 and 24 h; hydrogen storage at 100 h; and pumped hydropower at 10 and 24 h. Parameters are anchored to the frozen PNNL/DOE v2024 engineering database, and the pumped-hydro variants share the provincial resource ceiling with the original pumped-hydro technology. The legacy `CAS` rows remain only for base-template compatibility and are disabled outside their validated scope.

Four-hour battery costs use the low, mid and high complete-system trajectories from NLR 2025. The separately supplied one-hour dataset is excluded because it does not close to the current four-hour load blocks, shares no VRE project keys with the model, and contains capacity factors above one.

For the 2033 one-hour pair, both pair members receive the same pre-specified numerical ladder: 12 h scaled Barrier without crossover (`Method=2`), then 24 h direct Dual Simplex (`Method=1`), then 24 h deterministic concurrent simplex (`Method=5`) only if the prior route does not obtain a strict solver-native optimum. This changes only the numerical algorithm, not the scientific model, tolerances, inputs, objective or constraints.

Official/frozen source snapshots required by the publication source gate are bundled locally in this package; no sibling source directory is required.

Run the complete eight-case workflow:

```powershell
$env:V17T2R5_JULIA = "C:\path\to\julia.exe"
$env:V17_SOLVER_THREADS = "10"
.\RUN_V17T2R5_CLEAN_REBUILD_AND_RUN_ALL_8_1x10.bat
```

Prepare and validate inputs without solving:

```powershell
.\RUN_V17T2R5_PREPARE_TARGETYEAR_CASES.bat
```

Publication release requires solver-native `OPTIMAL` status for all eight current-source cases, linked-SOC and physics audits, matched-pair identity checks, and immutable result lineage. `TIME_LIMIT` incumbents and diagnostic cleanup solutions are never publication outputs.
