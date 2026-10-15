# V17 求解证书与退化面处理

## 第一阶段：正式经济规划解

主路线为 `Method=2, Crossover=0, LPWarmStart=0, BarConvTol=1e-8`。放行要求：

- MOI `OPTIMAL`；
- primal/dual 均为 `FEASIBLE_POINT`；
- `result_count >= 1` 且存在变量值；
- Gurobi Status=2 与请求算法相符；
- Gurobi ObjVal、JuMP 目标与 `SystemCost / 1e6` 缩放关系一致；
- 模型约束与有量纲物理审计通过。

`ObjBound` 在 Barrier-only LP 中可能不可用，JuMP 重构对偶目标也可能与 Gurobi 内部 Barrier 证书不完全闭合。因此二者只记录为外部诊断，不参与否决求解器原生认证。

## 第二阶段：可选的稀疏最优面诊断

线性规划可能存在大量经济等价的运行点。第二阶段使用聚合投资锁、严格经济带和归一化毛吞吐目标，尝试从该最优面中选择更稀疏的表示。可选路线包括临时 raw Gurobi PStart + primal simplex、deterministic concurrent、Barrier 和 dual simplex。

第二阶段的科学角色仅为**表示选择实验**，不是新的经济优化问题，也不是第一阶段可行性或最优性的证明。其不收敛只说明无法稳定选出该稀疏表示，不能推翻已认证的第一阶段解。

## 解释限制

在高度退化的最优面上，不同算法可能给出不同但经济等价的毛发电、毛充放电、方向性输电和备用转移。因此：

- 投资、容量、成本、政策和年度聚合结论可作为正式规划结果；
- 毛调度流量必须标记为退化敏感；
- 不得基于毛流量声称唯一运行轨迹、循环机理、方向性路由、拥塞因果或备用传递机理；
- 净平衡和约束闭合可用于核算证据，但不等同于运行机理识别。
