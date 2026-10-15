V20 HF4 等价投影续跑补丁
==========================

用途：保留既有严格成功的 __main 结果，只续跑未完成案例。
当前已知进度为 Layer A 7/8、Layer B 2/16、Layer C 2/2，共 11/26。

科学边界：
1. 不修改任何输入、case、原模型或既有结果。
2. 仅对尚未完成的 optimized_reallocation case 消去 32 个被统一时长精确决定的
   2023 Battery 能量坐标；目标函数、可行域、全国总量、分区上限和输出表结构等价。
3. 输入中的 national_energy = duration * national_power 在建模前硬校验；不满足即停止。
4. 新结果继续写入原 __main 目录，并增加 HF4_PROJECTED_MODEL_RESULT_LINEAGE.json。

使用前：如果旧的 FC08 Julia 仍在运行，请在那个运行窗口按 Ctrl+C，等命令提示符返回。
不要删除 04_V20_FUTURE_STORAGE，不要运行 clean，也不要重新 prepare。

运行：
  cd /d C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\04_V20_FUTURE_STORAGE
  call RUN_V20_HF4_RESUME_REMAINING_15_1x10.bat

日志：
  Layer A FC08: modules\correction2033\future_correction_batch_logs\FC08_EXPANDED_OPTIMAL
  Layer B:      batch_logs
  总进度:       audits\v20\V20_HF4_REQUIRED_26_PROGRESS.json
