# V20 技术成本与证据边界

## 核心原则

V20 不为了“让所有技术都有一条 2058 学习曲线”而人为外推数据。不同技术的公开权威证据具有不同时间边界，因此 V20 把 **证据直接情景（evidence-direct）** 与 **证据时间边界敏感性（equal-evidence-horizon）** 分开。

### Evidence-direct 主情景

- LFP 4 h：直接采用 NLR/NREL 2025 技术报告 Appendix Table 2 的年度 low/mid/high 完整系统成本轨迹。主情景用 mid；V17 已有 cost-low / cost-high 对应情景继续承担电池成本不确定性。
- VRFB / PSH：采用 PNNL Energy Storage Cost and Performance Database v2024 的 2030 Point / 100 MW benchmark；2028 仅在实际源年份之间插值，2030 后保持 2030 benchmark，不外推。
- CAES / H2：仅 pressure test。缺少与本文 32 区域一致的地质/盐穴/供水/接网资源供给曲线，因此不进入 headline 省级选址结论。

### V20 mandatory equal-evidence-horizon pair

长期技术竞争存在一个真实的证据非对称：LFP 有 2030 后直接年度轨迹，而 VRFB/PSH 的统一多技术数据库仅到 2030。V20 不通过虚构 VRFB/PSH 学习率解决这个问题，而增加 2 个必须运行的 matched cases：

- `V20EH01_OBSERVED`
- `V20EH02_OPTIMAL`

它们分别复制 `SL01_OBSERVED_STANDARDIZED` 与 `SL02_OPTIMAL_REALLOCATION`，除 `V18_LFP_4h` 在 2033–2058 的未来建设 CAPEX/FOM 被固定为 **NLR 2030 mid 直接值**外，其余 scientific inputs byte-identical。

因此，任何关于“2058 谁是技术赢家”的 headline 结论，都必须同时报告：

1. evidence-direct 结果；
2. equal-evidence-horizon 结果；
3. 原 16 主线中的电池 cost-low / cost-high pair。

若结论只在 evidence-direct 下成立，则应解释为 **对技术成本证据边界敏感**，不能升级为稳健技术优胜结论。

## DOE SI2030 的使用规则

DOE SI2030 Methodology、Flow Battery、PSH、CAES、Bidirectional Hydrogen 和 2024 LDES summary 提供的是 RD&D/innovation pathway 与 LCOS 层面的前瞻证据。LCOS 同时受 CAPEX、效率、寿命、替换、O&M 等影响。V20 **不把 SI2030 LCOS 降幅直接转换为 whole-system CAPEX multiplier**，避免把研发潜力误当成 BAU 投资成本预测。

其中 CAES/H2 技术报告进一步支持其明显的地质、基础设施与电价依赖边界，但仍不提供本文 32 模型区可直接使用的资源供给曲线。

这些材料用于：
- 支撑技术仍具有长期创新潜力的证据分层；
- 解释为什么不能把 PNNL 2030 hold 误称为“技术成本永远不下降”；
- 定义未来可扩展的 innovation-upside pressure test，但该测试不属于 V20 required runs。

## 选址边界

- LFP / VRFB：32 个模型区级配置，不是具体站址 GIS 选址。
- PSH：10 h 与 24 h 候选共享既有 zone-specific Hydro_Pumped resource ceiling，不能重复占用同一资源潜力。
- CAES / H2：无省级地质资源 ledger，pressure test only。

## 时序边界

Layer B 是 2028–2058 多期容量扩展 + V17-native `intraday_cyclic` representative-day chronology。它可以回答未来建设时序、技术组合与空间纠偏路径，但**不能**据此宣称跨月/季节运行价值，也不是连续 8760 多天气年可靠性证明。linked-month 仅作为独立诊断/敏感性；关键配置的全年运行结论应通过既有 full-8760 validation/handoff 路线进行后续 replay。
