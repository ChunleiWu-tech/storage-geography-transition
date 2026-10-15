# V20 模型与结论边界合同

## 1. 研究角色

V20 是冻结 V17 空间锁定研究之上的**加法式纠偏规划层**。它不回写或替换 01/02/03 的既有结论，也不允许把历史储能重新分配后再称为“未来纠偏”。

- V17：识别 inherited-storage spatial lock-in；
- V20：在 inherited stock 已经存在的条件下，优化未来新增投资以降低该 lock-in 的剩余代价。

## 2. Layer A：2033 matched correction

8 个 case 构成 4 个 Observed–Optimal 配对。BASE 与 ADAPTIVE 的 deliberate intervention 只允许发生在声明的未来储能机会集；Observed/Optimal 配对仍只承载 inherited geography 差异。差分中的差分用于区分：

1. 原始 legacy penalty；
2. adaptive opportunity set 后的 residual legacy penalty；
3. correction value / repair fraction。

所有数值必须来自 strict solver-native OPTIMAL 结果；TIME_LIMIT incumbent 不进入正式结论。

## 3. Layer B：2028–2058 动态路径

投资期固定为 2028、2033、2038、2043、2048、2053、2058。模型保留历史 Battery / Hydro_Pumped 等存量载体，并禁止把 2023 stock-anchor 当作新建期。未来 V18_* 候选是独立的新增投资设计。

Headline 设计空间仅包含：

- LFP 4 h；
- VRFB 10 h；
- VRFB 24 h；
- PSH 10 h；
- PSH 24 h。

模型内生决定每个允许建设期、每个模型区、每个离散技术—时长设计的新增功率容量。储能能量容量由候选设计的固定 energy-to-power ratio 与功率容量共同决定。因此 V20 是**离散 technology-duration portfolio optimization**，不是连续的 E/P 比自由优化。

发电扩张和跨区输电扩张继续与储能共同优化，因此“纠偏”可能通过储能、输电或系统其他容量调整完成，而不是预设只能靠新增储能解决。

## 4. 资源约束

PSH 10 h 与 24 h 不是两套独立地理资源。Julia core 中 `V18_PSH_Shared_Provincial_Resource_Ceiling` 将既有 Hydro_Pumped 与全部 V18 PSH duration designs 合并计入同一模型区资源上限，防止 duration option 造成资源潜力重复计算。

CAES / H2 缺少与 32 模型区一致的工程地质/盐穴/供水/接网资源 ledger，因此仅作为 pressure test，不能升级为 headline 省级选址建议。

## 5. 技术成本证据

- LFP 4 h CAPEX：NLR/NREL 2025 4 h complete-system low/mid/high 年度轨迹；
- VRFB / PSH：PNNL ESGC Cost and Performance Database v2024 的 Point / 100 MW 多技术 benchmark；
- 非 LFP headline technologies：不外推到公开数据源时间边界之后；2030 后 evidence-direct 路径保持 2030 benchmark；
- DOE SI2030：仅作为 RD&D / innovation-potential 和 claim-boundary 证据，不把 LCOS 降幅直接转换为 whole-system CAPEX multiplier。

未来 LFP 候选的成本路径来自 NLR；其跨技术比较所需的候选性能/寿命参数由 PNNL portfolio 表提供。该混合证据边界必须在方法中显式说明，不能写成“所有 LFP 参数均来自 NLR”。

## 6. V20 equal-evidence-horizon 必跑敏感性

`V20EH01_OBSERVED` / `V20EH02_OPTIMAL` 复制动态 core pair，仅将 V18_LFP_4h 的 2033–2058 CAPEX/FOM 固定到 NLR 2030 mid anchor。除此之外 scientific input files 保持不变。

该 pair 不声称“LFP 实际不会继续降本”，只用于回答：长期技术组合是否被不同数据源的预测时间边界驱动。

长期 technology-winner 只有在以下证据下定性稳健时才能进入 headline：

1. evidence-direct；
2. equal-evidence-horizon；
3. 原 low/high battery-cost sensitivity。

否则只能表述为“对未来技术成本证据边界敏感”。

## 7. 时序边界（V20-HF2）

Layer A 与 Layer B/C 使用不同但**各自预先声明**的时序合同，二者不能混写：

- Layer A：独立 2033 correction matched design，保留 `monthly_linked`；
- Layer B/C：2028–2058 动态规划 headline，强制使用 V17-native `intraday_cyclic` representative-day chronology。

Layer B/C 这样设计是为了只改变 future opportunity set，而不同时改变 chronology formulation。它适合识别未来新增容量、技术—时长设计、空间、建设期和输电协同路径；**不支持 intermonth / seasonal operational shifting claim**。

`monthly_linked` 在 HF2 中降级为独立 diagnostic/sensitivity；若出现 INFEASIBLE，必须保留 `infeasibility_conflict_constraints.csv` 与 `infeasibility_context.json`，不得把该结果解释成现实系统物理不可行。关键全年运行结论仍需与 03 full-8760 验证链衔接。

## 8. 允许的论文主张

V20 可以支持：

- 在 frozen inherited stock 下，未来新增容量的低成本纠偏价值；
- 模型区级新增储能技术—时长—容量—建设期组合；
- 储能与输电之间的补偿/替代关系；
- 历史空间锁定中可被未来投资修复与仍然残留的部分。

V20 不直接支持：

- 具体工程站址；
- CAES/H2 的省级部署处方；
- 连续最优 duration；
- 超出证据时间边界的确定性技术成本预测；
- 未经 8760 replay 的全年可靠性结论；
- 由 Layer B/C intraday representative-day 结果推导的跨月或季节储能运行价值。
