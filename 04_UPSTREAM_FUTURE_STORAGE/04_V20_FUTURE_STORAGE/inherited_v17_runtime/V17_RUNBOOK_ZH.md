# V17 运行手册

在 V17 根目录打开 PowerShell：

```powershell
$env:JULIA_EXE = "C:\你的Julia路径\bin\julia.exe"
$env:V17_SOLVER_THREADS = "10"
Remove-Item Env:V17_PYTHON -ErrorAction SilentlyContinue
```

## 1. 发布、源码与运行环境检查

```powershell
.\CHECK_V17_RELEASE.bat
.\CHECK_V17_SOURCE_LOAD.bat
.\CHECK_V17_RUNTIME.bat
```

`CHECK_V17_RUNTIME.bat` 包含生产源码加载和小模型算法/API 探针。诊断清理探针仅证明代码路径可调用，不代表正式大模型必须完成第二阶段清理。

## 2. SL00 正式主路线

```powershell
.\RUN_V17_SL00_PRIMARY_ONLY_1x10.bat
```

该命令使用 Stage-1 scaled Barrier，并直接将认证的第一阶段结果作为正式结果；不会执行第二阶段清理。

## 3. 第一阶段算法受控后备

只有当第一阶段本身未获得求解器认证时，运行：

```powershell
.\RUN_V17_SL00_CONTROLLED_1x10.bat
```

后备顺序为 deterministic concurrent、dual simplex，每次均重建模型并启动全新 Julia 进程。若第一阶段已认证但后续物理审计或导出失败，批处理会停止并要求修复，不能用更换算法掩盖下游问题。

## 4. 全国正式场景

SL00 严格通过后运行：

```powershell
.\RUN_V17_SPATIAL_LEGACY_FULL_1x10.bat
```

正式结果位于 `outputs/<scenario>__main`。

## 5. 可选第二阶段诊断

```powershell
.\RUN_V17_SL00_SPARSE_FACE_DIAGNOSTIC_1x10.bat
```

该命令只尝试在经济最优面内寻找更稀疏的毛流量表示。其结果不晋级、不进入正式后处理，也不得替代第一阶段解。未收敛是允许且必须如实记录的诊断结论。

## 6. 输出解释边界

正式可用于投稿结论：投资、容量、成本、退役、政策比较、年度聚合、净进出口、净储能平衡和约束闭合。

限制使用：`dispatch.csv`、`DispatchTx.csv`、`storage_operation_audit.csv` 中的毛流量只用于核算重构、聚合能量与可复现性；不得解释机组循环、同时充放电机理、唯一输电路径、拥塞因果或备用转移机理。以 `RESULT_INTERPRETATION_POLICY.csv` 为最终解释口径。
