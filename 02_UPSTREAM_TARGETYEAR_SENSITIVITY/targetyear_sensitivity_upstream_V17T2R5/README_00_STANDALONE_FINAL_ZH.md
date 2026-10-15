# 当前最终版：V17T2R5 目标年敏感性 8 场景

本目录是独立、干净、完整的目标年敏感性上游包。科学模型和 8 个场景定义保持冻结；本版将已经跑通/诊断得到的数值经验直接整合进普通运行入口，不再需要手工叠加 rescue 补丁。

## 场景
- TY2028_CHRONO_OBSERVED / OPTIMAL
- TY2033_CHRONO_OBSERVED / OPTIMAL
- TY2033_CHRONO_LDES_OBSERVED / OPTIMAL
- TY2033_CHRONO_1H_OBSERVED / OPTIMAL

## 求解策略
- 6 个 4 h/LDES 场景：保留原受控 exact-LP 自动路线。
- 2033 1 h pair：两个成员获得完全相同的预设求解链；先成功者立即停止：
  1. scaled Barrier, Method=2, Crossover=0, 12 h, BarIterLimit=100000；
  2. Dual Simplex, Method=1, NumericFocus=3, ScaleFlag=2, 24 h；
  3. deterministic concurrent simplex, Method=5, 24 h。
- 任何 TIME_LIMIT、中间可行解或未通过物理/SOC/来源/导出门的结果都不会进入正式输出。

## 推荐命令
从零重建并运行全部 8 个：
```cmd
call RUN_CURRENT_CLEAN_REBUILD_AND_RUN_ALL_8_1x10.bat
```
已有严格成功结果时续跑：
```cmd
call RUN_CURRENT_RESUME_ALL_8_1x10.bat
```
只跑 2033 1 h pair：
```cmd
call RUN_V17T2R5_2033_1H_PAIR_1x10.bat
```

默认 Windows 环境：Python 3.11、Julia、Gurobi；Barrier 路线 solver cap 为 10 线程。Dual Simplex 本身按 Gurobi 算法特性运行，但包仍保留 10-thread 全局上限。

本发行包不携带 sensitivity_outputs、batch_logs、failed_diagnostics、__pycache__ 或 .pyc。
