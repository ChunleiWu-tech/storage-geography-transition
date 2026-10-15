# Storage V17 主上游 16 场景：独立、干净、完整运行版

本目录可以独立运行主上游 16 个正式场景，不依赖目标年敏感性包或 8760 验证包；当前发行版已把 source gate 所需的官方/冻结源快照直接收进本目录，因此不再依赖父目录中的 shared_source_snapshots。

## 本独立版吸收的已验证运行经验

1. 科学模型、冻结数据源、16 个场景定义、目标函数、物理约束和发布门均保持不变。
2. 已合入最终结果 lineage 文件名修复：正式 lineage 使用当前 `audits/V17_SPATIAL_LEGACY_POLICY_AUDIT.json`，不再引用旧文件名。
3. 14 个常规场景保持原有严格求解策略：标准 scaled Barrier 为主路线，只有主路线未获得严格证书时才进入既有受控 fallback。
4. `SL10_CARBON_TIGHT_OBSERVED` 与 `SL13_COST_LOW_OPTIMAL` 直接采用实际完成 16/16 时成功的标准 scaled Barrier：`Method=2, Crossover=0, NumericFocus=2, ScaleFlag=-1`，每个困难场景最多 21600 s，串行 10 线程。
5. `TIME_LIMIT`、中间可行点、未通过 primal/dual/physical/export gate 的结果均不能进入正式结果。
6. 所有场景均在独立 Julia 进程中求解；主启动器固定串行 1×10，避免多个大型 LP 同时抢内存。

## 推荐入口

从零重建数据、案例并重跑全部 16 个：

```cmd
call RUN_V17T4R3_STANDALONE_CLEAN_REBUILD_AND_RUN_ALL_16_1x10.bat
```

已有部分严格结果时续跑，只计算缺失或失败场景：

```cmd
call RUN_V17T4R3_STANDALONE_RESUME_ALL_16_1x10.bat
```

PowerShell 中在文件名前加 `./` 或 `.\`。

## Windows 环境

默认自动探测 Python 3.10+，Julia 使用 `julia`，Gurobi 线程默认 10。也可在运行前显式设置：

```cmd
set V17_PYTHON=py -3.11
set JULIA_EXE=julia
set V17_SOLVER_THREADS=10
```

## 成功判据

最终必须同时满足：16/16 场景存在正式结果；Stage 1 为求解器原生 `OPTIMAL`；primal 和 dual 均为 `FEASIBLE_POINT`；严格物理审计、导出门、结果指纹和 publication result-source gate 全部通过。

## 干净发行说明

本 ZIP 是代码、冻结源数据、模型、案例构建器、审计和启动器的干净可复现发行版，不预装本机已经求得的 `outputs/`、`batch_logs/` 或 `failed_diagnostics/`。这样不会把旧机器的绝对路径、失败尝试或缓存混入新的复现运行。

科学设定未因本独立版而改变；变化仅限求解器路由编排、最终 lineage 文件名修复、独立源快照封装与运行卫生。
