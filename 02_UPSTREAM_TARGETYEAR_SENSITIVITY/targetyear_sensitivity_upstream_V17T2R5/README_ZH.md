# 目标年份敏感性上游：8 个源项锁定的 linked-SOC 场景

数据版本：`NEA_SWITCH_CHINA_SOURCE_UPDATE_20260803_V2`

## 科学问题与边界

本包在 12 个代表月之间连接荷电状态（state of charge, SOC），进行独立的 2028 或 2033 目标年份容量—运行联合再优化。它用于检验既有储能区位惩罚在时间连接、技术特异性长时储能（long-duration energy storage, LDES）和更细代表日时间分辨率下是否仍存在。

这不是完整多期转型路径，也不是 8,760 h 连续时序。2033 场景不继承模型在 2028 年内生选择的新建容量。1 h 场景由当前 4 h 代表日输入进行有界、精确块均值保持的重构，只能解释为时间离散化敏感性。

## 四组严格配对

| 配对 | 参考区位 | 同总量最优区位 | 时间分辨率 | 目的 |
|---|---|---|---:|---|
| `TY2028_CHRONO` | `TY2028_CHRONO_OBSERVED` | `TY2028_CHRONO_OPTIMAL` | 4 h | 2028 区位效应 |
| `TY2033_CHRONO` | `TY2033_CHRONO_OBSERVED` | `TY2033_CHRONO_OPTIMAL` | 4 h | 2033 区位效应 |
| `TY2033_CHRONO_LDES` | `TY2033_CHRONO_LDES_OBSERVED` | `TY2033_CHRONO_LDES_OPTIMAL` | 4 h | 技术特异性 LDES 压力测试 |
| `TY2033_CHRONO_1H` | `TY2033_CHRONO_1H_OBSERVED` | `TY2033_CHRONO_1H_OPTIMAL` | 1 h | 代表日时间离散化敏感性 |

每组配对固定全国既有新型储能为 135,930 MW 和 351,120 MWh，共同时长 `2.583094239682189 h`。参考与最优成员除既有储能空间配置及对应策略文件外，其余物理输入逐文件一致。

LDES 配对显式允许：CAES 10/24/100 h、钒液流 10/24 h、氢储能 100 h、抽水蓄能 10/24 h。各技术使用冻结的 PNNL/DOE v2024 工程参数，抽水蓄能的 10/24 h 选项与原模型抽水蓄能共享省级资源上限。模型仍保留旧 `CAS` 技术行以兼容基础模板，但非 LDES 场景将其禁用，LDES 结论只从新的离散技术集合读取。

4 h 电池成本采用 NLR 2025 轨迹。用户提供的额外 1 h 数据由于负荷块均值、VRE 项目键和容量因子范围不满足当前模型闭合要求，未作为输入。

## 正式运行

```powershell
$env:V17T2R5_JULIA = "C:\你的Julia目录\bin\julia.exe"
$env:V17_SOLVER_THREADS = "10"
.\RUN_V17T2R5_CLEAN_REBUILD_AND_RUN_ALL_8_1x10.bat
```

只准备并验证 8 个输入、不求解：

```powershell
.\RUN_V17T2R5_PREPARE_TARGETYEAR_CASES.bat
```

可使用各配对启动器分批诊断，但只有 8 个场景全部获得求解器原生 `OPTIMAL` 证书、SOC 连接审计、物理审计、配对身份审计和当前源项结果指纹后，结果门与统一后处理才允许发布。`TIME_LIMIT` 中间可行点和诊断清理结果均不得作为正式结果。
