# V17T2R5R5：2033 1h OPTIMAL 单案例精确续接补丁

这个补丁只处理 `TY2033_CHRONO_1H_OPTIMAL`，不会清理、重跑或覆盖其余七个已经完成的案例。

## 为什么不再继续 09/10

- 09 的对偶单纯形长期保持 `Dual Inf = 0`，但 `Primal Inf` 在很大量级波动，说明它没有获得可用的原始可行基。
- 10 只传入完整 `PStart`；对这个高度退化 LP，PStart 并不等价于一个完整基，因此仍可能回到相同的原始不可行搜索路径。

## R5 做什么

1. 在完整 OPTIMAL 模型内，只临时固定 32 个旧储能分配坐标为配对 OBSERVED 值，并要求严格 Gurobi `OPTIMAL`。
2. 保存完整原始解 `X`、线性约束对偶解 `Pi`、约化成本 `RC` 和原目标系数。
3. 精确恢复 OPTIMAL 的 32 个原始边界。
4. 仅对这 32 个坐标构造临时支持目标 `c_support = c_original - RC`。这使保存的 `(X, Pi)` 在完整边界模型上同时原始、对偶可行。
5. 传入完整 `PStart + DStart`，由 Gurobi crossover 构造严格最优基。
6. 保留该可行基，用原始单纯形逐级恢复原目标；最后 32 个目标系数必须零误差恢复，才允许进入官方最终求解。
7. 最终结果仍须通过原有 solver-native OPTIMAL、物理、时序、目标一致性和导出门；任何中间解都不能发布。

## 科学主线

输入 CSV、约束矩阵、RHS、最终变量边界、最终目标、求解容差及发布门均未改变。临时支持目标只用于数值续接，失败即中止且不会晋升结果。

## 使用

把补丁压缩包放进现有 `targetyear_sensitivity_upstream_V17T2R5` 根目录，解压并覆盖同名代码文件，然后运行：

```bat
cd /d C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\targetyear_sensitivity_upstream_V17T2R5
call RUN_V17T2R5R5_2033_1H_OPTIMAL_ONLY.bat
```

日志位置：

```text
batch_logs\TY2033_CHRONO_1H_OPTIMAL\11_targetyear_r5_primal_dual_supported_objective_continuation.log
```

成功时，最终官方结果会晋升到：

```text
sensitivity_outputs\TY2033_CHRONO_1H_OPTIMAL__main
```

没有任何脚本能够诚实保证大型退化 LP 在有限时限内 100% 收敛；R5 的意义是消除已由 09/10 日志证明的“缺少原始可行基”根因，并以严格门禁验证每一步。
