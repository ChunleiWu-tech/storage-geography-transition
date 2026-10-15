# V20 先运行、后定图

V20 的优先级是获得 solver-native、严格可审计的数值结果；不在求解前锁死 Fig. 6 / Fig. 7 的最终信息密度。

Required runs 共 26 个：

1. Layer A：8 个 2033 matched correction cases；
2. Layer B：16 个 2028–2058 evidence-direct dynamic pathway cases；
3. Layer C：2 个 equal-evidence-horizon core matched cases。

只有 required 26/26 均通过 strict solver-native gate，才允许生成正式集成结果表。

图稿决策在数值结果之后：
- 如果一张 6-panel Fig. 6 能清楚回答“能修多少—建什么—建哪里—何时建—与输电如何协同—成本边界是否稳健”，则只保留 Fig. 6；
- 如果长期 2028–2058 pathway 与 2033 correction 信息量过高，则拆为 Fig. 6（2033 correction）+ Fig. 7（dynamic pathway & robustness），不为了限制主图数量牺牲可读性。


## V20-HF2 时序识别与可行性修复

Layer B/C 的 required headline runs 固定使用 `intraday_cyclic`，原因不是为了“绕过”不可行性，而是为了保持 V17 已验证的代表日时序不变，使 V20 动态层的唯一结构干预保持为 future storage technology-duration-location-year opportunity set。

这避免了把两个变化同时塞进同一个差分：

1. storage opportunity set 改变；
2. chronology formulation 改变。

因此：Layer B/C 可以支持容量、技术、区域、建设期与输电协同的规划结论，但不支持跨月/季节 operational shifting 结论。Layer A 的 2033 correction 继续使用其独立的 monthly-linked matched design。03 包继续承担 full-8760 验证。

可选 `RUN_V20_B2_FEASIBILITY_ISOLATION_DIAGNOSTIC_1x10.bat` 只用于隔离 V17-native baseline、linked-month chronology 与 future-portfolio 三类作用，并保留 solver conflict evidence；不产生 publication-eligible canonical result。
