# V18 证据核验、参数用途与发布边界（2026-08-09）

## 1. 证据使用原则

V18 把来源分为三类：

- **参数证据**：官方实验室/政府数据库，可直接形成模型输入，但必须保留单位、年份、技术、功率和时长口径；
- **中国现实校核**：国家能源局公开数据，用于检查模型技术集合和时长设计是否与中国发展事实相容；
- **机制证据**：同行评议研究只用于决定模型应考虑哪些机制/验证，不把其容量结果直接搬入中国输入。

## 2. NLR/NREL 2025 电池成本

冻结原始报告：

`shared_source_snapshots/official/NLR_Cost_Projections_Utility_Scale_Battery_Storage_2025_Update.pdf`

SHA256：`90a33468917abf4284fae5296df6c85a87a52594c1da4acf3a8783fde558e150`

V18 使用报告 Appendix Table 2 的 4 h utility-scale lithium-ion 年度 low/mid/high 成本路径。`data/processed/nlr_2025_battery_4h_costs.csv` 保留完整年度表；静态审计对 2024、2028、2033、2038、2043、2048、2053、2058、2060 的数值逐项锁定。

报告同时给出通用时长成本结构：总 $/kW 由功率部件 $/kW 与能量部件 $/kWh × duration 组成。因此 V18 **不把 4 h 的 $/kWh 机械乘到 8/10 h**。R1 采用“4 h 年际轨迹 × PNNL 同口径 2030 duration ratio”保持可审计性；这是一种证据有界缩放，不声称是 NLR/NREL 对 8/10 h 的直接预测。

## 3. PNNL ESGC v2024

冻结原始数据库：

`shared_source_snapshots/official/PNNL_ESGC_Cost_Performance_Database_v2024.xlsx`

SHA256：`ef50e87012361e2a10d3df97cb61b93d38eae9255539ca76061e0c5feef501e9`

`data/processed/pnnl_v2024_point_100mw_selected_storage.csv` 只保留本研究所用的 `Point`、100 MW 技术–时长切片；`v18_storage_technology_portfolio.csv` 中安装成本、固定 O&M、RTE、calendar life 等字段与该切片逐项交叉检查。

重要边界：所选非 LFP 技术没有可用的 2035 源点。R1 不伪造 2035；2030 后默认冻结 2030 证据基准。H2 的源年份按 PNNL 数据版本原样保留，且 H2 仅压力测试。

## 4. 中国事实校核

国家能源局公开的 2025 年底新型储能信息用于现实一致性校核，包括全国装机/能量规模、平均时长、4 h 及以上项目占比、技术结构等。该信息支持“未来时长不应被人为固定为 4 h”这一建模方向，但不提供完整的省级 MWh/站址资源账本，因此 V18 不反向构造不存在的省级官方数据。

## 5. Nature Communications 机制证据

- 2023 中国省级电池部署异质性研究：支持空间异质化配置机制；
- 2024 LDES 系统价值研究：支持长时储能价值取决于 VRE、输电、水电/系统条件，而非一个固定全国时长；
- 2025 中国极端天气可再生能源充裕性研究：支持中国省级极端天气可靠性验证；
- 2026 多天气年 Dunkelflaute 研究：支持未来用多天气年 out-of-sample 验证 LDES 与输电互补。

这些论文**不提供 V18 中国容量输入**。它们只决定模型结构与下一阶段验证设计。

## 6. V18 R1 的 headline / pressure-test 防火墙

Headline (`evidence_bounded`)：LFP 4/8/10 h、VRFB 10/24 h、PSH 10/24 h。

Pressure test only：CAES 10/24/100 h、H2 24/100 h。

CAES/H2 不进入 headline 的原因不是技术价值判断，而是 R1 尚无可复现的中国省级盐穴/储氢地质资源供给曲线。允许其在全国所有模型区无限建设会把“缺数据”错误转化成“无限资源”。

## 7. 发布审计状态

截至 2026-08-09：

- `V18_STATIC_SCIENCE_AUDIT_R3`：23/23 PASS；
- V18 legacy immutability cross-check R2：16/16 PASS；
- Julia 语法：26/26 PASS；
- 空集合：8/8 PASS；
- 数值稳定性：25/25 PASS；
- prepared cases：16/16 PASS；
- solver-certified：NOT RUN in current container（无 Julia/Gurobi）。

因此 R1 可以发布为**可在本地继续求解的、源数据与输入准备已审计的独立 04 上游包**，但最终容量数字必须以本地 solver-certified outputs 为准。
