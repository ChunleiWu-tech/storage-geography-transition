# V17 发布说明

V17 将求解与解释口径统一为“**第一阶段正式发布，第二阶段仅作非阻断诊断**”。

## 核心科学修正

1. **第一阶段是正式结果。** 第一阶段提供求解器原生认证的经济最优解，并通过模型约束、单位化物理审计、输入边界和导出闭合检查。正式发布目录只接受 `publication_solution_source=stage1_solver_certified_economic_optimum`。
2. **第二阶段不再是发布硬门槛。** 第二阶段只试图在高度退化的最优面中，以经济带和聚合战略锁为约束，寻找更稀疏、毛吞吐更低的等价运行表示。PStart + Primal Simplex、并发、Barrier 和 Dual 路线均保留为显式诊断工具，但不进入正式批处理后备树。
3. **清理不收敛不否决第一阶段。** 多种清理算法未收敛时，只记录 `cleanup_diagnostic_converged=false`；不得覆盖、降级或否决已经认证的第一阶段经济规划结果。
4. **毛调度流量强制披露退化敏感性。** `dispatch.csv`、`DispatchTx.csv` 和 `storage_operation_audit.csv` 均携带结果来源、退化敏感标记、禁止运行机理解释标记和允许用途。毛发电、毛充放电、方向性输电及备用转移不得用于解释唯一的运行路径、循环机理、拥塞成因或方向性路由。
5. **规划结论仍可正式使用。** 投资、容量、退役、成本、政策比较、年度聚合、净平衡与约束闭合均以第一阶段结果为准，并继续接受严格物理与导出审计。

## 工程修正

- 修复 `run_model` 局部作用域 `const` 导致的 Julia include/lowering 失败；顶层声明由全包静态审计阻断回归。
- 保留 Stage-1 Barrier 无 crossover、solver-native 证书、目标缩放一致性和 JSON 非有限值安全写出。
- 正式受控后备仅在第一阶段未获认证时尝试 deterministic concurrent 和 dual simplex，且每次均为全新 Julia 进程。
- 不读取或写入 `VBasis`、`CBasis`、`CrossoverBasis`、`DStart`，不持久化 PStart。
- 新增 `RESULT_INTERPRETATION_POLICY.csv`，并在毛流量文件中逐行保留解释限制。

V17 没有放宽经济最优、模型可行性、物理闭合、no-CDR 边界或数据来源门槛；只纠正了“将退化面清理误作正式最优解必要条件”的发布逻辑。
