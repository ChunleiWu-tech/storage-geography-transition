# FULL8760 四 case 失败史、原因与修复闭环

## 证据口径

本文汇总既有日志、用户提供的失败输出以及 HF3–HF7 审计。数值以日志中可见的近似值记录，用于诊断算法行为，不替代正式 `solve_status.csv`。旧失败尝试不随干净包复制；路径名称保留，便于与原始归档核对。

## 1. TY2033_FULL8760_OBSERVED

早期 scaled Barrier 路径曾达到时间上限或没有形成可发布结果。后续某次求解器本身已得到严格最优，但在 postsolve/导出阶段因安全结果计数 helper 的作用域/兼容问题（包括 `_safe_result_count` 类未定义故障）中断，因此出现“已经最优却没有导出”。这不是模型不可行，也不是数值最优证书失败，而是求解后的程序错误。

HF2P1/HF3 将 postsolve 读取改成 scope-safe，并采用 exact projected scaled Barrier 路径；该 case 后来已严格提升成功。定稿包仍要求从 HF3 重跑并重新生成本次机器上的完整证据链。

## 2. TY2033_FULL8760_OPTIMAL

原始 Barrier、dual simplex 和 concurrent/simplex 路径多次 TIME_LIMIT，部分尝试没有 result。HF4 后来在 observed-allocation restricted face 上把 seed 解到 native optimal：Barrier 约 175 次迭代，目标约 `7.63838573e5`。最初一次在 seed 后又被 `_safe_result_count` 兼容故障截断；修复后，完整模型上的 Gurobi 10.0.1 crossover 在约 37,009,456 行、21,564,279 列的规模上发生 `EXCEPTION_ACCESS_VIOLATION`。

HF5 为避开 crossover，尝试 crushed complete PStart/DStart + primal simplex，但该基在完整空间中数值失效：约 502,711 次迭代后目标约 `-2.38e30`、primal infeasibility 约 `3.05e2`、dual infeasibility 约 `9.4e34`，未获证书。HF6 的 unpresolved DStart dual-simplex 又因完整空间太大而代价过高。

HF7 的针对性修复是：保留可解的 observed legacy restricted face，在该 face 上用 DStart-only presolved dual simplex 生成显式 basis，再分块释放 legacy 坐标并做目标 continuation，彻底避开已知崩溃的 crossover 和已知失效的 crushed PStart 路径。

## 3. TY2033_FULL8760_LDES_OBSERVED

旧 HF3 full-LDES Barrier 运行到约 129600 秒附近时，日志仍显示 primal objective 约 `1.562e6`、dual objective 约 `7.067e5`，primal residual 约 `8.29e-3`、dual residual 约 `9.98e-6`、complementarity 约 `7.13e-4`。dual residual 很小但 primal/dual objective 仍相差约 `0.8e6`，说明还没有经济最优证书，不能把“另外两个指标下降”当作即将成功。

根因不是 LDES 科学数据错误，而是旧 seed 只处理 legacy geography，仍让新 LDES build 坐标自由，因此 seed 实际上仍在解完整、最困难的 LDES 组合。HF7 先将所有 LDES power/energy build 固定为零；零容量会使对应 hourly dispatch/charging/SOC/reserve 变量失活，presolve 才能真正移除这部分，再严格分块释放。

## 4. TY2033_FULL8760_LDES_OPTIMAL

这是四者中结构最复杂的 case。旧 Barrier screen 运行约 74000 秒时，primal objective 约 `1.521e6`、dual objective 约 `7.071e5`，残差约为 `2.44e-2 / 1.67e-5 / 2.12e-3`，objective gap 长时间很大。旧 seed 仅固定 legacy allocation，却没有关闭 LDES build，所以既没有继承已解决 non-LDES face，也没有有效降低模型。

HF7 同时采用 observed legacy allocation 与 zero-LDES restricted face，先获得严格 seed/basis，再先释放 LDES、后释放 legacy，最后恢复原目标。这是对该结构问题的直接修复，而不是放宽容差或删除科学约束。

## 运行管理问题不是求解失败原因

历史过程中还出现过 scenario lock 等待、旧 coordinator 占锁、多个终端同时启动同一 launcher，以及日志长时间不刷新。PID 的 CPU 增长只能证明进程活着；`active in another coordinator` 表示新协调器在等旧 lease，不表示新 case 已开始。stale lock 可以阻止调度，但不会改变数学模型，也不能解释已进入 Barrier 后的数值停滞。定稿包采用“一 case、一 Julia、一 lease、一 attempt 目录”，同一解压目录禁止重复协调器；三个未完成 case 只由一个 HF7 coordinator 并行调度。

## 严谨结论

OBSERVED 的历史故障已闭环并严格成功。其余三个的失败机理已有针对性 HF7 修复，但在新的本机运行生成 3 个 strict `solve_status.csv` 以前，任何人都不能保证或宣称它们已成功。定稿包的价值是把已证伪的路径排除、把数值修复限制在同一模型内部，并用 fail-closed 门保证“跑完”不等于“发布”。
