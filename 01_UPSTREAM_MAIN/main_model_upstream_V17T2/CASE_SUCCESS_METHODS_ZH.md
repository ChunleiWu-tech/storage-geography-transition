# 主上游 16 case：已验证成功方法

## 状态口径

本包对应主上游空间—遗留储能 16 个正式 case。用户既有运行已完成 16/16；为保持交付包干净，既有 `outputs`、`batch_logs` 等运行产物不随压缩包复制。重新运行后，以每个 case 的 `solve_status.csv`、总汇总中的 `publication_strict_success=true`、结果谱系和物理审计为正式证据，不以终端中某一个残差或临时可行解作为成功判据。

## 成功求解政策

统一入口为 `RUN_CLEAN_REPRODUCE_SUCCESSFUL_METHODS_16.bat`。它先校验干净包的 SHA-256 清单，再调用已经实证通过的 V17T4R3 串行 1×10 线程流程：重建冻结输入、检查来源指纹、准备 16 个 case、逐 case 独立启动 Julia、严格求解、生成结果谱系并关闭发布门。

| case | 成功方法 |
|---|---|
| SL00_OBSERVED_ACTUAL | V17T4R3 常规精确 LP 路径：scaled Barrier 主路径；只有未获严格证书时才进入受控后备路径 |
| SL01_OBSERVED_STANDARDIZED | 同上 |
| SL02_OPTIMAL_REALLOCATION | 同上 |
| SL03_NO_LEGACY | 同上 |
| SL04_RULE_LOAD | 同上 |
| SL05_RULE_VRE | 同上 |
| SL06_TX_FIXED_OBSERVED | 同上 |
| SL07_TX_FIXED_OPTIMAL | 同上 |
| SL08_PH_CONSERVATIVE_OBSERVED | 同上 |
| SL09_PH_CONSERVATIVE_OPTIMAL | 同上 |
| SL10_CARBON_TIGHT_OBSERVED | 实证困难 case：标准 scaled Barrier，`Method=2`、`Crossover=0`、`NumericFocus=2`、`ScaleFlag=-1`，硬路径预算 21600 秒 |
| SL11_CARBON_TIGHT_OPTIMAL | V17T4R3 常规精确 LP 路径 |
| SL12_COST_LOW_OBSERVED | V17T4R3 常规精确 LP 路径 |
| SL13_COST_LOW_OPTIMAL | 实证困难 case：与 SL10 相同的标准 scaled Barrier 无 crossover 路径，硬路径预算 21600 秒 |
| SL14_COST_HIGH_OBSERVED | V17T4R3 常规精确 LP 路径 |
| SL15_COST_HIGH_OPTIMAL | V17T4R3 常规精确 LP 路径 |

## 不变的科学与发布条件

所有路径只改变求解算法与启动方式，不改变输入数据、case 定义、矩阵、RHS、变量最终边界、经济目标、容差或物理/发布阈值。仅原生 `OPTIMAL`、可用 primal/dual、目标证书一致、物理审计通过的结果允许进入 `outputs\<scenario>__main`。TIME_LIMIT、中间 incumbent 和失败诊断均不得发布。

成功证据在重新运行后由以下文件闭合：

- `storage_runner\storage_batch_run_summary.csv`
- `outputs\<scenario>__main\solve_status.csv`
- `audits\PUBLICATION_RESULT_LINEAGE.json`
- `CHECK_PUBLICATION_SOURCE_GATE.bat --stage results`

## 运行

在本包根目录执行：

```bat
call RUN_CLEAN_REPRODUCE_SUCCESSFUL_METHODS_16.bat
```

中断后保留严格成功结果并继续时，可使用原有 `RUN_V17T4R3_STANDALONE_RESUME_ALL_16_1x10.bat`。
