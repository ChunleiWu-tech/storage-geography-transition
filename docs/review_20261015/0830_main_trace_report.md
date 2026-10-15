# 0830 至当前图表数据追溯（只读独立核查）

核查日期：2026-10-15。当前目标：EES_投稿更新版_20261015R1/Postprocess/tables。

结论：0830 保存了与当前一致的原始模型代码、准备输入、后处理程序、模型结果汇总表及历史审计记录。本轮未找到逐情景原始求解输出与运行日志，因而不能将本轮检查描述为从 BuildGen/BuildTx 原始输出重新生成全部图表。

## 实际检查

- 遍历0830所有15个ZIP目录；均不含 outputs、sensitivity_outputs、future_correction_outputs、logs、BuildGen.csv、BuildTx.csv、BuildStorageEnergy.csv、storage_batch_run_summary.csv 或求解日志。
- 关键上游ZIP：SUBMISSION_4PACK_FINAL_20260830_130000/01_MAIN_UPSTREAM_V17T4R3_SUBMISSION_FINAL_20260830.zip（1066项，251804686未压缩字节），为源代码、准备输入、静态审计。
- 当前74表对比0830 V31R4：68个逐字节相同；5个只改pair_label/context/scenario_label，全部数值列相同；1个新增展示表figS14_timing_display.csv。主图1–5和补图1–11使用的数值源未改变。
- 调用原始build_spatial_legacy_tables.py的只读build_input_tables，直接读取01_UPSTREAM_MAIN实际输入。32节点、90线路、6情景规格、1浓度统计表全部列与当前图表数据一致。全国135.93GW、351.12GWh、2.583094h、前5区45.282469%、P95储能/同期峰值0.403796413。
- 从省区×技术×时期详细汇总表独立聚合：15个国内容量差/半绝对和比较通过。2033锂电容量净差35669.207MW；2038空间半绝对和5935.217MW；2058为14784.699MW。
- 六情景累计费用与保留的求解器审计stage1_economic_optimum相差0.10–0.27USD（总费用约3.55万亿USD）；状态均OPTIMAL、FEASIBLE_POINT，原生证书字段True。这是与保存的求解摘要比较，并非本轮重新读取日志。
- 主要费用差6281335202.745117USD；初始储能优化价值25641317730.23584USD；价值保留率0.7550307176554244；七时期费用现值差之和闭合误差-0.000183105USD。

## 证据界限

图1及补图1–2是观测输入/模型输入统计，补图4是情景定义；其余核心数值来源为本研究模型的保留结果汇总及后处理。不能把所有绘图数字都统称为求解器输出，也不能因冻结表相同即保证原始运行绝对无误。历史UPSTREAM_RESULT_LINEAGE_AUDIT.json的status为PASS、具体检查均真，但interpretation文字为“Source lineage is not synchronized.”，属于相矛盾的遗留说明，不能充当本轮实时通过证据。原始逐情景结果文件和日志应另行恢复后，方能补齐端到端输出重提取证明。

全部机器可读清单、数值和差异在0830_main_trace.json；可重跑脚本audit_0830_main.py未写入上游与正式包。
