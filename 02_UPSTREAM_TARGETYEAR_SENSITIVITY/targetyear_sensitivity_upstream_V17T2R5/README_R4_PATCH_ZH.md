# V17T2R5R4：2033 1H OPTIMAL 单案例续算补丁

R4 仅运行 `TY2033_CHRONO_1H_OPTIMAL`，不会清理、重算或覆盖其余 7 个案例。

它不修改科学输入、目标函数、约束、时序、求解容差和发布门。第一阶段在同一个 OPTIMAL 模型中，仅把 32 个既有省级电池功率坐标临时固定到配对的 `TY2033_CHRONO_1H_OBSERVED` 配置，并且必须取得 Gurobi 原生 `OPTIMAL`。随后逐项恢复 OPTIMAL 原始上下界，将第一阶段全部变量值设为完整 PStart，最终用原始单纯形求解完整的优化再配置可行域。

第一阶段只是严格可行起点，不是最终结果。只有第二阶段完整模型再次取得原生 `OPTIMAL`，且原始/对偶状态、目标一致性、物理审计、时序审计和发布门全部通过，结果才会晋升到正式输出。

停止旧 09 后，把补丁 ZIP 放进现有敏感性包根目录，原地解压覆盖，然后运行：

```bat
call CHECK_V17T2R5R4_PATCH.bat
call RUN_V17T2R5R4_2033_1H_OPTIMAL_ONLY.bat
```

唯一日志：

`batch_logs\TY2033_CHRONO_1H_OPTIMAL\10_targetyear_r4_observed_seed_primal_continuation.log`

同一日志先出现 `V17T2R5R4 SEED PHASE`，严格通过后再出现 `V17T2R5R4 FINAL FULL OPTIMAL PHASE`。默认第一阶段最长 12 小时、最终阶段最长 24 小时；任何 `TIME_LIMIT` 都不会被当作正式结果。
