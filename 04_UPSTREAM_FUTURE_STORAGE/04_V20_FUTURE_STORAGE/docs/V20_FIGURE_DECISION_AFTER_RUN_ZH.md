# V20 图 6 / 图 7：仅在真实结果后决定

V20 的发布顺序固定为：先通过 26/26 strict solver-native result gate，再决定主图数量。发布包不携带 synthetic scientific figures。

## 优先方案：单独 Fig. 6

若真实数据在 180 mm 宽度、Arial-first、最小出版字号与不重叠约束下可清晰容纳，则 Fig. 6 用 6 个互补 panel 形成“纠偏闭环”：

- a：BASE legacy penalty → ADAPTIVE residual penalty 与 repair fraction；
- b：2033 corrective technology-duration mix；
- c：2033 model-zone × technology corrective allocation；
- d：2028–2058 build timing × technology-duration pathway；
- e：storage–transmission–generation compensation / substitution；
- f：TX-fixed、equal-evidence-horizon、low/high battery cost 与 expanded pressure-test 稳健性。

## 自动升级为 Fig. 6 + Fig. 7 的条件

若真实结果使上述任何一个 panel 必须出现密集标签、过多零值、不可读热图或双重尺度，则不压缩信息：

- Fig. 6：2033 correction identification（修复比例、技术、空间、输电替代）；
- Fig. 7：2028–2058 dynamic pathway + evidence-horizon/cost robustness。

## 禁止事项

- 不为了维持一张图而缩小字号或叠加图例；
- 不用同一指标重复填充多个 panel；
- 不用 CAES/H2 pressure-test 生成 headline province siting map；
- 不把 representative chronology 的路径图称为 full-8760 reliability result；
- 不在 solver-native strict PASS 前生成可用于论文的正式数值图。
