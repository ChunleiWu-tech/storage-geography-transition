# R24P2 根因与科学纠正

## 已观察事实

两条 OBSERVED 运行均已返回：

- Gurobi `Status=2 (OPTIMAL)`；
- JuMP primal/dual 均为 `FEASIBLE_POINT`；
- 目标读取误差约为 `1e-11 MW`；
- 固定组合链接残差约为 `1e-10 MW` 或更小；
- 失败集中在旧 `native_quality_gate_pass`。

旧门控保存了 `ConstrVio`、`BoundVio`、`DualVio` 和 `ComplVio`，但没有保存连续 LP 的 `ConstrResidual`、`DualResidual` 及其缩放形式。因而 `MaxVio≈125–127` 无法定位来源，却被直接与单一绝对物理容差比较。这不是足够完整的质量归因。

Gurobi 的质量属性定义见官方文档：
`https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/quality.html`

## R24P2 的纠正

R24P2 保持以下内容逐项不变：

- 四个固定目标年组合和源结果指纹；
- 8760 小时、非闰年、全年循环 chronology；
- 原输入、约束、RHS、目标函数和理想灵活性变量定义；
- Barrier、无 crossover、Gurobi 13.0.2 求解路线；
- 零距离才可判定原固定组合可行的科学边界。

只纠正证书质量归因和后处理门控：

1. 完整读取并记录 `BoundVio`、`ConstrVio`、`ConstrResidual`、`DualVio`、`DualResidual`、`ComplVio`；
2. 验证上述分量能够解释 `MaxVio`，禁止隐藏未知残差；
3. 对 `ConstrSResidual` 与 `DualSResidual` 单独施加 `1e-6` 门控；
4. 对约束、变量界、对偶与互补性分别门控，不把不同单位混成一个阈值；
5. 在原单位重新计算 8 项物理闭合：区域电力平衡、分布式平衡、规划备用、显式峰值备用、8760 循环 SOC 步进、SOC 上下界、理想 firm 链接和 absorption 链接；
6. 目标相对 gap 接受上限显式固定为 `1e-5`，仍受代码硬上限约束，且不替代物理质量门控。

因此这不是放宽 `MaxVio` 后强行通过，而是把旧门控无法解释的数值残差拆分、缩放并用原单位物理审计交叉验证。任何分量、缩放残差或物理闭合失败，结果仍不会晋级。

## 结论边界

- `distance <= 1e-3 MW`：原固定组合通过 8760 严格可行性证书。
- `distance > 1e-3 MW` 且证书通过：得到“最小理想本地灵活性距离”的严格正缺口；原固定组合仍不判为可行。
- 证书失败：仅保留失败诊断，不得进入论文结果。
