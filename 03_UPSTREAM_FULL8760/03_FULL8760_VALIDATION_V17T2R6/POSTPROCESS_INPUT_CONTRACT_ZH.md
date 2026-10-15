# FULL8760 后处理输入契约

本 ZIP 是干净的代码、冻结输入和复现方法包，不夹带服务器运行输出。后处理必须直接读取
服务器最终目录：

- `robustness_distance_8760_quality_recovery_outputs\V17T2R6R24P3_HF18P2_COMBINED_ALL4_final_summary.json`
- 同目录的 `.csv` 汇总；
- 四个证书记录所指向的 `TY2033_FULL8760_*__main` 目录；
- 如记录引用旧中央目录，还需保留 `robustness_distance_8760_outputs\*__main`。

进入后处理前应再次确认 `status=PASS`、`all_four_certificates_success=true`、恰好四条唯一
scenario，并分别读取可行性与 robustness distance。不得从成功标志推断
`all_four_original_portfolios_feasible=true`。
