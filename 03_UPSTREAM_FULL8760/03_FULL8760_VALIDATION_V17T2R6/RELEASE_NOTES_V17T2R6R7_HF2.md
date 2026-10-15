# V17T2R6R7-HF2 exact-projection reduction

HF2 is an algebraically equivalent computational reduction of the active full-8760 LP. It was introduced after both CORE scenarios exhausted the prespecified 12-hour scaled-Barrier route and 24-hour homogeneous-Barrier fallback without a solver-certified optimum.

## Scientific invariants

HF2 does not change any scenario input, load, VRE or hydro series, existing-storage geography, investment option, technology cost, fuel or carbon policy, transmission representation, planning-reserve equation, operating-reserve equation, full-year cyclic chronology, economic objective, solver tolerance, solver route, time limit, or publication gate.

The output schema is unchanged. CCS dispatch for non-CCS projects and startup-cost contributions for projects outside the active startup/shutdown set are exported as their exact structural value of zero.

## Exact reductions

1. CCS dispatch and CCS commitment variables are created only for `CCS_GENS`. In the unreduced formulation, every non-CCS project has `GenCapacityCCS == 0`; the corresponding lower/upper constraints therefore fix both variables to zero. Removing these fixed-zero columns and their rows is exact.
2. Startup and shutdown variables and their inter-hour consistency equality are created only when startup cost, minimum uptime, or minimum downtime is nonzero. For every omitted project, those variables occur nowhere else and have zero objective coefficient. For any retained commitment path, the eliminated equality can be reconstructed with `Startup[t] = max(Commit[t] - Commit[t-1], 0)` and `Shutdown[t] = max(Commit[t-1] - Commit[t], 0)`. Projection is therefore exact, including the year-end cyclic link.

For each CORE case this removes 9,636,000 hourly columns. For each LDES case it removes 18,536,160 hourly columns. Counts are derived from the frozen inputs and checked pairwise by `tools/check_julia_8760_static.py`; the proof and per-case counts are recorded in `audits/V17T2R6_8760_JULIA_STATIC_AUDIT.json`. Every attempted solve also records the active and omitted counts in `solve_status.csv`.

## Validation status

- Static Julia delimiter/contract audit: PASS.
- Exact-projection code and frozen-input proof audit: PASS.
- Package QA and source/case identity checks: required before handoff.
- Target-machine Julia/Gurobi runtime preflight: pending because Julia is not installed in the editing environment.
- Four full-8760 solver-certified reruns: required. HF2 is deliberately marked `RERUN_REQUIRED`, not publication-ready, until those runs and all existing publication gates pass.

## 中文说明

HF2 只删除“必为零的 CCS 小时变量”和“可从保留的机组承诺路径精确补回、且成本及最小启停约束均为零的启停变量”。负荷、成本、8760 连续时序、储能、输电、备用、碳约束、求解容差及发表验收门槛均未改变。当前版本必须在目标 Julia/Gurobi 机器完成预检和四场正式重跑后，才可恢复 publication-ready 标记。
