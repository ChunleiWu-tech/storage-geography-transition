# V30 上游对齐与单位审计

状态：`PASS（代码/数据契约审计）`。最终运行仍会对另一台结果电脑上的实际 CSV、JSON、指纹和 54 条结果逐条 fail-closed 复核；缺一项即不成图。

## 固定路径

默认桌面根为 `C:\Users\Admin\Desktop`，四个只读上游根为：

1. `C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\main_model_upstream_V17T2`
2. `C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\targetyear_sensitivity_upstream_V17T2R5`
3. `C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\03_FULL8760_VALIDATION_V17T2R6`
4. `C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\04_V20_FUTURE_STORAGE`

运行器要求四根互不相同，并检查各包特有的注册表、R24P3 四证书汇总和 V20 A/B/C 严格汇总，避免误指向同名旧目录。

## 字段和单位

| 后处理量 | 上游字段 | 上游单位 | 报告单位 | 唯一换算 |
|---|---|---:|---:|---:|
| 新建功率 | `BuildGen` | MW | GW | `/1000` 一次 |
| 新建储能能量 | `BuildStorageEnergy_MWh`（兼容同值旧别名） | MWh | GWh | `/1000` 一次 |
| 储能时长 | 上述能量/功率 | MWh/MW | h | 直接相除 |
| 2033 Layer-A 系统成本 | `SystemCost_annualized_usd_per_yr` | USD/yr | million USD/yr | 匹配差后 `/1e6` |
| Layer-B/C 经济目标 | `stage1_economic_objective_usd` | present-value USD | billion USD PV | 匹配差后 `/1e9` |
| FULL8760 稳健性距离 | `total_ideal_flexibility_robustness_distance_mw` | MW | GW（仅图） | `/1000` 一次 |

年度成本与现值目标绝不相加。FULL8760 距离绝不解释成投资、成本或实际技术建设。

## 闭合与来源门

- V20 每条结果重新要求 native `OPTIMAL=2`、原始/对偶可行、官方 Stage-1 放行、物理审计、导出门、纯 LP、无 CDR，并复核 source → case → result SHA256 指纹。
- Layer A 必须为 `monthly_linked` 且跨期 SOC 相连；Layer B/C 必须为 504 点 `intraday_cyclic`，不得声称季节或连续 8760 运行。
- FULL8760 必须满足 R24P3 四证书 PASS；总距离 = firm + absorption = 分区和，并要求 lineage、objective、native-quality、physical-quality 和 pure-LP 门全部显式为真。
- “严格成功但新增储能为零”是合法科学零值，保留为零，不再误判为文件缺失。
- 建设变量若低于 `-1e-6` 原生 MW/MWh 立即失败；仅把该阈值内的负向浮点噪声规范为零。

该审计不替代实际结果机运行；它定义了运行时必须通过的精确契约。
