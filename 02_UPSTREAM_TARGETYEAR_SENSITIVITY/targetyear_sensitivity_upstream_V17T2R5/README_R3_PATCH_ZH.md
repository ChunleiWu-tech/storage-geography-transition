# V17T2R5R3 单案例精确结构降维补丁

适用目录：`targetyear_sensitivity_upstream_V17T2R5`

唯一重跑案例：`TY2033_CHRONO_1H_OPTIMAL`

R3 不修改任何科学输入、目标函数、时间序列、约束容差、求解合格标准或发布门禁，也不删除、不重算其余 7 个已完成结果。它只在该案例建模时，精确消去 316,800 个恒为零或不影响目标与科学可行域投影的小时坐标；导出时按原定义补回零值，因此输出表结构保持不变。

运行前，只需在旧 `07_targetyear_projected_scaled_barrier` 所在终端按一次 `Ctrl+C`，等命令提示符返回。不要结束 V20 或 8760 的其他 Julia 进程。

把补丁 ZIP 放入既有敏感性包根目录，原地解压并允许覆盖后运行：

```bat
call RUN_V17T2R5R3_2033_1H_OPTIMAL_ONLY.bat
```

运行顺序：

1. 静态等价与输入规模门禁；
2. `08_targetyear_r3_hourly_reduced_scaled_barrier.log`；
3. 仅当第 2 步未严格成功时，自动运行 `09_targetyear_r3_hourly_reduced_dual_simplex.log`。

只有 Gurobi 原生 `OPTIMAL`、原始与对偶状态均为 `FEASIBLE_POINT`，且全部物理、时序、识别和发布门禁通过，结果才会晋升到：

`sensitivity_outputs\TY2033_CHRONO_1H_OPTIMAL__main`

R3 提高的是数值求解机会，不承诺必然收敛，也不接受 `TIME_LIMIT` 中间点作为正式结果。
