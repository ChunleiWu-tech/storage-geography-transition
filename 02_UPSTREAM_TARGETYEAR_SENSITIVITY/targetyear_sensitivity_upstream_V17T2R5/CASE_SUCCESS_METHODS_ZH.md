# 目标年敏感性 8 case：已验证成功方法

## 状态口径

本包对应 2028/2033、常规 chronology/LDES/1 h 的 8 个敏感性 case。用户既有运行已完成 8/8；干净交付不携带旧 `sensitivity_outputs`、`batch_logs` 和失败尝试。重新运行以 `V17T2R5_run_summary.csv`、各 case 的 `solve_status.csv`、结果谱系及发布源门为正式成功证据。

## case 与成功路径

| case | 写入包内的成功方法 |
|---|---|
| TY2028_CHRONO_OBSERVED | 普通 exact-LP `auto` 路径：target-year deterministic concurrent 主路径，必要时 homogeneous dual-crossover 后备 |
| TY2028_CHRONO_OPTIMAL | 同上 |
| TY2033_CHRONO_OBSERVED | 同上 |
| TY2033_CHRONO_OPTIMAL | 同上 |
| TY2033_CHRONO_LDES_OBSERVED | 同上 |
| TY2033_CHRONO_LDES_OPTIMAL | 同上 |
| TY2033_CHRONO_1H_OBSERVED | 预先规定的 `one_hour_robust` 精确 LP 梯级；在首个严格原生最优结果处停止 |
| TY2033_CHRONO_1H_OPTIMAL | R5 `primal_dual_supported_objective_continuation`：严格 observed seed、32 个遗留坐标、完整 X/Pi/RC、支持目标、PStart+DStart/crossover basis、8 级原目标 continuation、精确恢复并关闭严格门 |

1 h observed 的梯级依次为 scaled Barrier、dual simplex、hard deterministic concurrent simplex；文档不把某个历史日志标签硬编码为永久科学结论，运行产生的 `solve_status.csv` 才是本次机器/版本下的权威成功路径记录。1 h optimal 不再重复已知长期不收敛的旧三路梯级，而直接调用已验证成功的 R5。

## 科学不变性

R5 的 seed、支持目标和 continuation 都是同一目标模型内部的数值求解阶段。最终发布前必须逐系数恢复原目标和原边界；输入、chronology、储能集合、约束矩阵/RHS、最终经济目标、FeasibilityTol、OptimalityTol、物理审计及发布阈值均不改变。任何 TIME_LIMIT、无 primal/dual、目标不一致或未通过 strict gate 的尝试只保存在诊断区，不能替代正式结果。

## 运行

统一干净复现入口：

```bat
call RUN_CLEAN_REPRODUCE_SUCCESSFUL_METHODS_8.bat
```

该入口按顺序重建 case，运行 6 个普通 case、1 h observed、R5 1 h optimal，最后写入结果谱系并生成 8-case 汇总。默认单 case 10 线程；case 之间串行，避免同一输出目录和许可证争用。
