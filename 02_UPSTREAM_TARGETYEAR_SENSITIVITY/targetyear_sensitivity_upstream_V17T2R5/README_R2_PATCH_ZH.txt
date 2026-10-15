V17T2R5R2 单案例等价投影补丁

适用目录：targetyear_sensitivity_upstream_V17T2R5
唯一重跑案例：TY2033_CHRONO_1H_OPTIMAL

本补丁不删除、不重算另外 7 个已完成结果，也不重新准备输入。
请把补丁 ZIP 解压到既有敏感性包根目录并允许覆盖同名文件，然后运行：

RUN_V17T2R5R2_2033_1H_OPTIMAL_ONLY.bat

新日志：
batch_logs\TY2033_CHRONO_1H_OPTIMAL\07_targetyear_projected_scaled_barrier.log

只有 Gurobi 原生 OPTIMAL 且全部发布门禁通过时，结果才会晋升到：
sensitivity_outputs\TY2033_CHRONO_1H_OPTIMAL__main

R2 保持输入、科学可行域、目标函数、时间序列、严格容差、发布门禁、
输出表结构和其他七个结果不变。它只把 32 个满足 E=duration*P 的旧电池
能量坐标从数值 LP 中精确代入消除，并在结果导出时按同一恒等式重建。
