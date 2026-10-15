# V17T2R6R7-HF2P2 全国连续 8760 h 验证包（等价后处理加速，须完整重跑）

> HF2P2 状态：HF2P1 的等价后处理加速保持不变；HF2P2 只修正干净重建后的发行清单边界，避免把必然重新生成的 case 文件误判为包损坏，详见 `RELEASE_NOTES_V17T2R6R7_HF2P2.md`。不可变代码、模板和源数据仍受 SHA-256 锁定；重建 case 继续通过时序、来源指纹、配对一致性和运行时门控。科学输入、模型构建、目标函数、约束、求解路线、结果行序和发表门槛均未改变。

## 1. 定位

本包是主上游 16 场景和目标年敏感性 8 场景之后的独立时间分辨率验证层，不替代前两层模型。仅包含 4 个 2033 静态目标年连续 8760 h 线性规划案例：

1. `TY2033_FULL8760_OBSERVED`
2. `TY2033_FULL8760_OPTIMAL`
3. `TY2033_FULL8760_LDES_OBSERVED`
4. `TY2033_FULL8760_LDES_OPTIMAL`

普通储能配对与 LDES 配对中，Observed/Optimal 组内只允许既有 Battery 地理分配控制不同；非地理输入保持 byte-identical。模型仍是单目标年容量+调度重优化，不是完整多期转型路径。

## 2. R7 运行策略与已固化的真实运行经验

R7 不改变科学模型；它保留 R6 已通过实跑暴露并修复的运行问题，同时把 2×10 并行调度固化为新的 canonical 入口：

- **R7 canonical 运行方式改为 pair-preserving 2×10 并行**：同一时刻最多运行 2 个 8760 case，每个 Gurobi 固定 10 线程；Wave 1 同时运行 CORE Observed/Optimal，完成后 Wave 2 同时运行 LDES Observed/Optimal。
- 并行只改变调度，不改变任何 case 的输入、目标函数、约束、求解算法、容差或发表门；Observed/Optimal 仍使用完全相同的预设 solver ladder 和计算预算。
- 共享 summary 只由父进程在每个 wave 完成后统一合并，两个 worker 不并发写共享 summary；日志、attempt、promoted output 与 failure archive 均按 scenario 隔离。
- 修复 8760 求解已获严格 `OPTIMAL` 后，结果表构造误引用未定义全局量 `REPRESENTATIVE_TIMEPOINT_COUNT_EXPECTED` 的后处理崩溃；现在统一使用已在运行期验证的局部量 `representative_timepoint_count_expected`。
- HF2P1 修复四个 case 共用的后处理性能缺陷：832,200 个储能时点键不再通过 Vector 反复线性扫描，而改用等价 `Set` 查询；原有有序 Vector 继续负责遍历，因此不改变输出内容和行序。
- HF2P2 修复完整干净入口的清单误报：发行 SHA-256 清单只锁定不可变材料，重新生成的四个 case 由既有的语义审计和来源链门控验收。

- 正式主路线：`scaled Barrier`，`Method=2`、`Crossover=0`、`NumericFocus=2`；
- 受控 fallback：`homogeneous Barrier`，`Method=2`、`BarHomogeneous=1`、`Crossover=0`、`NumericFocus=3`；
- 主路线默认 `TimeLimit=43200 s`，fallback 默认 `86400 s`；
- 两条路线 `BarIterLimit` 默认均为 `100000`，避免算法仍在正常收敛时被 1500/5000 次人为截断；
- `timeseries.csv` 中 `2035.01` 等标识可被 CSV.jl 推断为 `Float64`，活动模型统一使用通用 `string(x)` 处理排序 tie-break，不再调用 `String(::Float64)`；
- 活动 Julia 时间戳解析器显式支持本包真实格式 `yyyy-mm-dd_HH:MM`；
- Julia 模型构建阶段再次强制检查 8760 个唯一时间戳、严格逐小时连续、完整非闰年 Jan-1 00:00 → Dec-31 23:00、12 个单月 TIMESERIES 完整覆盖；
- `CHECK_V17T2R6_8760_RUNTIME.bat` 不再只做 Gurobi 小 LP，而会用 Julia/CSV.jl 直接读取 4 个正式 case 的 `timeseries.csv`/`timepoints.csv`，提前验证真实标识符类型和下划线时间戳格式；
- pair/all 启动器为 resume-safe：已经提升且仍通过全部严格门的结果会跳过，不会因为重启入口而无意义重跑；
- 若 Julia 在求解前崩溃、没有生成有效 `solve_status.csv`，batch 会停止并保留诊断，不再用第二个 solver profile 重复同一个预处理错误。

这些修改不改变负荷、VRE、水电、既有储能、技术成本、网络、碳政策、目标函数、物理约束、最优性/可行性容差或发表门。

## 3. 数据与时序边界

- 负荷：31 省逐小时重构负荷形状；2024 原 8784 h 去除 2 月 29 日后得到 8760 h，再严格缩放到冻结的 2033 年度电量。
- VRE：已审计的 2024 省级 ERA5 逐小时序列，UTC → 中国标准时间采用固定 `+8 h` 循环平移。
- 水电：保留月度平均/最小流量包络，施加于当月真实小时。
- SOC、机组启停状态和最小开停机窗口跨月连续；12 月 31 日 23:00 与 1 月 1 日 00:00 循环闭合。
- 海上风电逐小时曲线仍未进入本包证据边界，因此本验证不支持海上风电时序结论。

详细来源见 `data/source_registry/FULL8760_SOURCE_AND_METHOD_LEDGER.md`。

## 4. 推荐目录

解压后目录应直接是：

```text
%USERPROFILE%\Desktop\01_UPSTREAM_16PLUS8\03_FULL8760_VALIDATION_V17T2R6
```

不要出现双层：

```text
03_FULL8760_VALIDATION_V17T2R6\03_FULL8760_VALIDATION_V17T2R6\...
```

## 5. 本机环境

已按当前 Windows 工作流设置默认值：

```cmd
set V17T2R6_PYTHON=py -3.11
set V17T2R6_JULIA=julia
set V17_SOLVER_THREADS=10
set V17T2R6_MAX_PARALLEL=2
set V17T2R6_8760_PRIMARY_TIME_LIMIT_SECONDS=43200
set V17T2R6_8760_FALLBACK_TIME_LIMIT_SECONDS=86400
set V17T2R6_8760_PRIMARY_BAR_ITER_LIMIT=100000
set V17T2R6_8760_FALLBACK_BAR_ITER_LIMIT=100000
```

R7 canonical 发布模式固定为 **2 个 case 并行 × 每 case 10 个 Gurobi 线程**，即最多 20 个 solver threads 同时工作。该并行模式以资源充足的工作站为前提；若需要低内存诊断，可手工用 `--max-parallel 1` 串行运行，但不要改变每个 case 的科学输入或验收标准。

## 6. 正式开跑前检查

CMD：

```cmd
cd /d "%USERPROFILE%\Desktop\01_UPSTREAM_16PLUS8\03_FULL8760_VALIDATION_V17T2R6"

set V17T2R6_PYTHON=py -3.11
set V17T2R6_JULIA=julia
set V17_SOLVER_THREADS=10
set V17T2R6_MAX_PARALLEL=2

call CHECK_V17T2R6_8760_PREFLIGHT.bat
```

该总预检会依次执行 Julia 静态审计、R7 并行调度器无求解器回归测试、包 QA、Julia/Gurobi 运行时检查和 cases source gate。并行调度测试必须证明“最多 2 个 worker、Wave 2 等待 Wave 1 完成、结果顺序确定”。全部 PASS 后再进入正式求解。运行时部分必须看到：

```text
Gurobi smoke LP: PASS
8760 CSV identifier/timestamp runtime contract: PASS
V17T2R6 full-8760 runtime check: PASS
```

## 7. HF2P2 完整干净重跑

本次更新不要续跑旧 HF2 状态。推荐只用一个 canonical 命令：

```cmd
call RUN_V17T2R6_8760_CLEAN_REBUILD_AND_RUN_ALL_4_2x10.bat
```

该入口只删除本包生成的 cases、结果、日志和失败诊断，再由冻结源项重新生成四个 case；不会删除模板、原始数据或源代码。

它固定采用两波并行：

```text
Wave 1: TY2033_FULL8760_OBSERVED + TY2033_FULL8760_OPTIMAL
        10 threads/case              10 threads/case

Wave 2: TY2033_FULL8760_LDES_OBSERVED + TY2033_FULL8760_LDES_OPTIMAL
        10 threads/case                   10 threads/case
```

每个 worker 内仍按同一预设路线顺序执行：`scaled Barrier/no crossover` 主路线，只有未取得 solver-native `OPTIMAL` 才进入 `homogeneous Barrier/no crossover` fallback。任何已存在且重新通过全部严格门的正式结果会 resume-safe 跳过。

如只需重跑一组，可分别使用：

```cmd
call RUN_V17T2R6_8760_CORE_PAIR_2x10.bat
call RUN_V17T2R6_8760_LDES_PAIR_2x10.bat
```

若已经完成过一次 HF2P2 干净生成，后续仅做 resume-safe 检查时才可运行：

```cmd
call RUN_V17T2R6_8760_ALL_4_2x10.bat
```

## 8. 结果收口

若 CORE 和 LDES 是分别运行的，四个场景全部 PASS 后执行：

```cmd
call FINALIZE_V17T2R6_8760_RESULTS.bat
```

它会依次完成 publication result lineage、results source gate 和 8760 summary。

需要和 4 h 敏感性比较时：

```cmd
call BUILD_V17T2R6_8760_SUMMARY.bat --reference-root "..\targetyear_sensitivity_upstream_V17T2R6"
```

## 9. 正式结果标准

只有同时满足以下条件才提升到 `sensitivity_outputs/<scenario>__main`：

- solver-native `OPTIMAL`；
- primal `FEASIBLE_POINT`；
- dual `FEASIBLE_POINT`；
- no-crossover 正式 solver profile 匹配；
- 严格物理审计通过；
- 8760 SOC/时序连续性审计通过；
- Observed/Optimal identification gate 通过；
- export 完整；
- result fingerprint / source lineage 通过。

`TIME_LIMIT`、`ITERATION_LIMIT`、无 primal/dual 的解不会作为投稿结果。

## 10. 清洁发布纪律

本发布包不含 `__pycache__`、`.pyc/.pyo`、`batch_logs`、`failed_diagnostics`、`sensitivity_outputs` 或历史失败结果。旧 R1–R6 专用/过时 launcher 已删除，避免误用旧路线；顶层只保留当前 R7 的 2×10 canonical 入口与成对重跑入口；旧 1×10 all-four launcher 已移除，避免误用旧调度策略。
