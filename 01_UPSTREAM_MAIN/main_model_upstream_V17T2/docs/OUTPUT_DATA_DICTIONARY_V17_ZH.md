# V17 关键输出与解释字段

## `solve_status.csv`：正式第一阶段字段

- `publication_solution_source=stage1_solver_certified_economic_optimum`：正式结果来源。
- `stage1_official_release_selected=true`：本次运行选择第一阶段正式发布。
- `stage1_official_release_pass=true`：第一阶段求解器证书、状态与可行性门槛通过。
- `solver_profile`：主路线为 `scaled_barrier`；受控后备只允许 `deterministic_concurrent` 或 `dual_simplex`。
- `stage1_native_solver_certificate_pass`：求解器原生经济最优证书。
- `stage1_economic_optimality_proof_source`：Barrier、零迭代 presolve、并发或 dual-simplex 的认证来源。
- `stage1_external_diagnostic_*`：ObjBound/重构对偶目标等非阻断诊断。
- `audit_export_result_tier=official_stage1_economic_optimum`：最终正式结果等级。

## 第二阶段诊断字段

- `requested_cleanup_profile=stage1_official_release`：正式运行不请求清理。
- `successful_cleanup_route=stage1_official_release`：正式结果直接采用第一阶段。
- `cleanup_diagnostic_attempted=false`：正式批处理未执行第二阶段。
- `cleanup_diagnostic_nonblocking=true`：第二阶段状态永不作为正式发布硬门槛。
- `cleanup_diagnostic_converged`：仅在显式诊断运行中报告稀疏表示是否成功找到。
- `sparse_face_diagnostic_recommended`：第一阶段毛流量是否超过诊断阈值；只表示建议尝试稀疏表示，不是发布失败。
- `selected_route_completion_pass`：所选正式或诊断路线是否完成；正式放行仍单独由 `stage1_official_release_pass` 决定。
- 旧的 PStart、投资锁、经济带和清理目标字段保留用于显式诊断的可追溯性，不代表正式结果依赖这些字段。

## 退化敏感字段

- `gross_dispatch_degeneracy_sensitive=true`。
- `gross_dispatch_operational_interpretation_allowed=false`。
- `gross_dispatch_allowed_use=accounting_reconstruction_and_aggregate_balance_only`。
- `diagnostic_degeneracy_review_pass` 是披露型诊断，不参与否决第一阶段正式结果。

## `RESULT_INTERPRETATION_POLICY.csv`

该文件按输出族定义：正式状态、退化敏感性、是否允许运行机理解释、允许用途和禁止用途。后处理 preflight 必须核查该文件。

## 毛流量文件中的逐行标签

`dispatch.csv`、`DispatchTx.csv` 和 `storage_operation_audit.csv` 均包含：

- `ResultSource`；
- `DegeneracySensitive`；
- `OperationalMechanismInterpretationAllowed`；
- `AllowedUse`。

这些标签必须随文件进入任何下游分析，不能在整理数据时删除。
