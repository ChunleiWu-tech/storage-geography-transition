# V20-HF5 求解退化根因与等价修复技术审计

## 技术结论

FC08 及剩余 V20 case 的共同故障不是“某个算法偶然不好”，而是原 LP 含有大批数学上必为零或对目标与可行域投影无贡献的小时坐标。它们形成固定零列、重复限制和目标中性退化方向，使 Barrier 的原始/对偶残差长期停滞，也使 simplex 在高度退化的基之间移动。

HF5 不修改任何科学输入、政策、成本、时间权重、目标函数含义、物理约束含义或验收容差。它只显式消去可由原方程严格证明为冗余的坐标，并在导出时补回全表的零值，因此保留原输出模式。

## 关键证据

| 证据范围 | 发电项目 | 时间点 | CCS 项目 | 有实际启停作用的项目 | 等价消去的小时变量 |
|---|---:|---:|---:|---:|---:|
| FC08_EXPANDED_OPTIMAL | 625 | 72 | 96 | 96 | 152,352 |
| 每个 Layer B SL case | 529 | 504 | 96 | 96 | 872,928 |

HF4 的 FC08 Barrier 在 43,200 秒达到约 34,586 次迭代仍触发 `TIME_LIMIT`；随后 dual simplex 的不可行量在约 `10^11` 到 `10^15` 间大幅摆动。两者与高度退化、病态基/列结构一致，但日志本身只说明症状；上表的变量定义与输入逐项核对才是结构根因证据。

## 等价消元的数学依据

### 非 CCS 项目的 CCS 小时变量恒为零

对 `g ∉ CCS_GENS`，原模型按构造给出 `GenCapacityCCS[g,p] = 0`。原 CCS 承诺上界与调度上界因此均为零，非负变量 `CommitGenCCS[g,t]`、`DispatchGenCCS[g,t]` 只能取零。删除这些变量及其零上下界行，不改变其余变量的目标或可行域投影。导出函数对这些坐标重建为 `0.0`。

### 无启停作用项目的 Startup/Shutdown 对是目标中性扩展

当某项目同时满足 `startup_om = 0`、`min_uptime = 0`、`min_downtime = 0` 时，`Startup` 与 `Shutdown` 除下式外不再出现：

`Commit[t-1] + Startup[t] - Shutdown[t] = Commit[t]`。

任意承诺轨迹都可令二者分别等于承诺变化的正部和负部，从而满足该式；两者又均无目标成本。因此删除它们不限制 `Commit` 的任何可行轨迹，并消除一个非负、目标中性的退化方向。导出时其启动成本贡献重建为零。

### optimized_reallocation 的既有 32 个能量坐标投影保持不变

仅在 `optimized_reallocation` 中，2023 Battery 能量由统一时长关系 `E[g] = duration × P[g]` 精确决定。HF5 保留 HF4 对这 32 个坐标的投影；observed case 不启用这项投影。全国功率闭合、分区上界、输入恒等式硬校验及完整输出重建全部保留。

## 求解与验收设置

- `FeasibilityTol = 1e-7`，未变。
- `OptimalityTol = 1e-7`，未变。
- `BarConvTol = 1e-8`，未变。
- `TIME_LIMIT`、无解值、非 `OPTIMAL` 仍不能发布。
- 原 HF4 的 12+24+24 小时三次独立尝试会在每次重启时丢失 Barrier 轨迹。HF5 将同样 60 小时总预算给一次连续 scaled Barrier；若提前取得严格最优会立即返回。
- 所有已存在且重新通过指纹和严格发布门的 `__main` 结果直接保留，不重算、不覆盖。

这与 Gurobi 官方数值指南的原则一致：数值问题优先通过模型重构处理，调整容差通常不是有效修复。官方还明确指出 Barrier 只有在原始/对偶可行性、互补性和目标差满足 `BarConvTol` 后才返回最优。参见 [Gurobi 数值问题指南](https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide.html)、[数值参数说明](https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/numeric_parameters.html) 和 [BarConvTol 参数](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-BarConvTol)。

## 验证边界与成功定义

当前补丁能静态证明：父模型哈希不变、容差常量不变、精确变量计数成立、Python 运行器可编译、输出重建函数存在、旧严格结果采用 resume-safe 跳过。由于本工作区没有可调用的 Julia/Gurobi，本地静态 PASS 不等于数值求解成功。

最终成功仍必须由运行机产生：Gurobi `Status=2`、JuMP `OPTIMAL`、原始与对偶均为 `FEASIBLE_POINT`、严格物理审计及发布门全部 PASS。任何单项未通过，case 保持未完成，不会被包装成结果。

## 推荐执行

旧 HF4 FC08/V20 不能与 HF5 同时写这个 V20 目录；但位于 8760、敏感性等其他包且使用独立输出目录的 Julia 可以并行。高配置机器需要并行时，显式设置允许开关。把补丁解压覆盖到 `04_V20_FUTURE_STORAGE` 后执行：

```bat
cd /d C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\04_V20_FUTURE_STORAGE
set "V20_HF5_ALLOW_OTHER_JULIA=1"
call RUN_V20_HF5_RESUME_REQUIRED_26_1x10.bat
```

Layer A 日志位于 `modules\correction2033\future_correction_batch_logs\FC08_EXPANDED_OPTIMAL\hf5_reduced_scaled_barrier.log`；Layer B 日志位于 `batch_logs\<scenario>__hf5_reduced_scaled_barrier_official.log`；总进度位于 `audits\v20\V20_HF5_REQUIRED_26_PROGRESS.json`。

## 后续问题

若缩减后的某 case 仍在完整预算内无法达到严格最优，应保存该 case 的 HF5 完整日志和 `solve_status.csv`。下一步应依据缩减后模型的 Kappa/残差轨迹继续定位剩余的相关行或缩放来源，而不是降低容差或接受 `TIME_LIMIT`。
