# V17T2R6R24P2-HF18P2：仅补跑两个 OBSERVED case

## 运行范围

本包只新求解以下两条，二者并行、每条 10 个 Gurobi 线程：

- `TY2033_FULL8760_OBSERVED`
- `TY2033_FULL8760_LDES_OBSERVED`

以下两条已成功的 R24P1 结果不会重算或覆盖；协调器只读校验其证书、源数据指纹和结果文件指纹：

- `TY2033_FULL8760_OPTIMAL`
- `TY2033_FULL8760_LDES_OPTIMAL`

## 安装和运行

把 ZIP 放进完整的 `03_FULL8760_VALIDATION_V17T2R6` 文件夹，解压并覆盖同名代码文件。不要解压到上一级，也不要删除原 `03` 包。

在 CMD 中只运行：

```bat
cd /d C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\03_FULL8760_VALIDATION_V17T2R6
call RUN_V17T2R6R24P2_HF18P2_QUALITY_RECOVERY_OBSERVED_2X10.bat
```

启动器会依次完成代码/哈希/科学范围/Gurobi 13.0.2 预检，然后同时启动两条 OBSERVED case。

## 输出位置

- 新日志：`batch_logs_robustness_distance_quality_recovery`
- 新尝试：`robustness_distance_8760_quality_recovery_outputs\_attempts`
- 两条严格晋级结果：`robustness_distance_8760_quality_recovery_outputs\<SCENARIO>__main`
- 两条补跑汇总：`robustness_distance_8760_quality_recovery_outputs\V17T2R6R24P2_HF18P2_QUALITY_RECOVERY_two_case_summary.json`
- 四条最终合并汇总：`robustness_distance_8760_quality_recovery_outputs\V17T2R6R24P2_HF18P2_COMBINED_ALL4_final_summary.json`

## 成功判据

终端最终必须同时出现：

```text
V17T2R6R24P2 HF18P2: BOTH OBSERVED QUALITY-RECOVERY CERTIFICATES COMPLETED
V17T2R6R24P2 HF18P2: COMBINED ALL FOUR CERTIFICATES COMPLETED
```

这里的“证书成功”表示稳健性距离问题获得严格最优解且质量审计通过。若距离为正，科学结论仍然是“固定目标年组合存在可量化的 8760 灵活性缺口”，不能写成原固定组合可行，也不能把理想资源写成实际技术建设。

## 可恢复性

新协调器使用独立输出、日志和锁目录。重复运行时，已经通过 R24P2 全部门控的 OBSERVED 结果会跳过；失败尝试保留，不会晋级为 `__main`。两个已成功的 R24P1 OPTIMAL 结果始终只读。
