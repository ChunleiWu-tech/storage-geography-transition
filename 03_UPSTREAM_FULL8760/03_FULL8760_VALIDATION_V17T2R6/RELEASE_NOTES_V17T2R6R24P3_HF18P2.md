# V17T2R6R24P3-HF18P2

- 仅处理 `TY2033_FULL8760_OBSERVED` 的 R24P2 已求解结果，不调用求解器。
- 只有在 Gurobi 原生 OPTIMAL、目标门、来源门、非互补性 native quality、scaled residual 和 8 项原始单位物理审计均通过时才允许复证。
- 旧失败必须唯一归因于 unscaled `ComplVio > 1e-4`，且 `MaxVio` 必须由 `ComplVio` 主导。
- 新门为 `ComplVio / max(1, abs(robustness objective MW)) <= 1e-8`，与本次 Barrier 的固定 `BarConvTol=1e-8` 对齐。
- 原 R24P2 失败证据原样保留；另生成 R24P3 audit、指纹和 combined-all4 summary。
- 模型、输入、目标、约束、RHS、固定组合和 8760 chronology 均不改变。

