# V20 未来储能 26 case：已验证成功方法

## 状态口径

本包的 required set 为 Layer A 8 + Layer B 16 + Layer C 2，共 26 个 case。用户既有运行已完成全部 required cases；干净交付不复制运行输出。重新运行时，`solve_status.csv` 和 V20 strict progress/audit 才是本次正式证据。

## Layer A：2033 future-correction 8

| case | 成功方法 |
|---|---|
| FC01_BASE_OBSERVED | V18 robust exact route tree；首个通过 native OPTIMAL 与全部 strict gates 的结果保留 |
| FC02_BASE_OPTIMAL | 同上 |
| FC03_ADAPTIVE_OBSERVED | 同上 |
| FC04_ADAPTIVE_OPTIMAL | 同上 |
| FC05_ADAPTIVE_TXFIXED_OBSERVED | 同上 |
| FC06_ADAPTIVE_TXFIXED_OPTIMAL | 同上 |
| FC07_EXPANDED_OBSERVED | 同上 |
| FC08_EXPANDED_OPTIMAL | 原 robust 尝试未严格收敛后，HF5 exact reduced formulation + 一次不中断 scaled Barrier；只在 strict native optimum 后提升 |

## Layer B：主上游映射 16

| case | 成功方法 |
|---|---|
| SL00_OBSERVED_ACTUAL | 原 strict 结果优先保留；缺失时由 HF5 exact reduced serial Barrier 补齐 |
| SL01_OBSERVED_STANDARDIZED | 同上 |
| SL02_OPTIMAL_REALLOCATION | 同上 |
| SL03_NO_LEGACY | 同上 |
| SL04_RULE_LOAD | 同上 |
| SL05_RULE_VRE | 同上 |
| SL06_TX_FIXED_OBSERVED | 同上 |
| SL07_TX_FIXED_OPTIMAL | 同上 |
| SL08_PH_CONSERVATIVE_OBSERVED | 同上 |
| SL09_PH_CONSERVATIVE_OPTIMAL | 同上 |
| SL10_CARBON_TIGHT_OBSERVED | 同上；运行时权威 attempt/profile 写入该 case 的 `solve_status.csv` |
| SL11_CARBON_TIGHT_OPTIMAL | 同上 |
| SL12_COST_LOW_OBSERVED | 同上 |
| SL13_COST_LOW_OPTIMAL | 同上；运行时权威 attempt/profile 写入该 case 的 `solve_status.csv` |
| SL14_COST_HIGH_OBSERVED | 同上 |
| SL15_COST_HIGH_OPTIMAL | 同上 |

## Layer C：equal-evidence-horizon pair 2

| case | 成功方法 |
|---|---|
| V20EH01_OBSERVED | matched/equal evidence horizon runner；严格求解并校验 paired source/chronology/evidence gate |
| V20EH02_OPTIMAL | 同上 |

## HF5 的科学边界

HF5 只投影 legacy energy 与 objective-neutral hourly columns，得到与原问题相同可行域/经济目标的 exact reduced formulation；最终结果仍映射回原输出结构并接受原有审计。它不改变数据、2030 evidence-horizon、2033 storage opportunity set、geography、chronology、carbon/transmission policy、矩阵科学含义、最终经济目标、solver tolerance 或发布门。已有 strict `__main` 结果只校验并保留，缺失 case 才补跑。

具体某次运行实际采用了 robust tree 的第几个 attempt，不由本文臆测；以本次生成的 `solve_status.csv` 和 batch summary 为权威。这使“成功方法已固化”与“运行证据可审计”同时成立。

## 运行

统一入口：

```bat
call RUN_CLEAN_REPRODUCE_SUCCESSFUL_METHODS_26.bat
```

该入口先重建输入并运行原 strict Layer A/B/C；某层未完全关闭时不会丢弃已成功结果，而会继续进入 HF5 resume 补齐缺失 case。只有最终 26/26 strict progress 为 PASS 才构建 V20 结果表并返回 0。
