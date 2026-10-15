# FULL8760 四 case：投稿最终方法与证据状态

| case | 最终证书路线 | 状态 |
|---|---|---|
| `TY2033_FULL8760_OPTIMAL` | HF18P2 minimum ideal local flexibility distance；Barrier/no crossover | 严格证书完成 |
| `TY2033_FULL8760_LDES_OPTIMAL` | 同上 | 严格证书完成 |
| `TY2033_FULL8760_LDES_OBSERVED` | R24P2 componentwise、scale-aware quality attribution 与 8 项原单位物理审计 | 严格证书完成 |
| `TY2033_FULL8760_OBSERVED` | 同上求解；R24P3 对唯一绝对 `ComplVio` 尺度误判做 fail-closed 后求解复证 | 严格证书完成 |

最终服务器成功标志为 `POSTSOLVE COMPLEMENTARITY RECOVERY PASS` 与
`COMBINED ALL FOUR CERTIFICATES COMPLETED`。R24P3 不调用 Gurobi，不改变输入、固定组合、
约束、RHS、目标或 8760 chronology；它保留所有原始质量值，仅要求尺度化互补性满足既定
`BarConvTol=1e-8`，同时保持其余原生质量门、来源谱系和原单位物理审计不变。

证书成功不等于原固定组合可行。每个 case 的科学结论必须读取
`V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json` 中的 `classification`、
`original_fixed_portfolio_feasible` 和 `total_robustness_distance_mw`；正距离是固定组合相对理想
局部灵活性的最小缺口，不是实际新增技术建设量。
