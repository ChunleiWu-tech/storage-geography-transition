# V19 与 01–03 主线的融合关系

## 与 01_MAIN_UPSTREAM
Layer B 直接继承 01 的 16 个正式空间遗产场景、相同 legacy allocation 定义、发电/输电/碳约束框架。构建审计直接从用户上传的 01 zip 读取 `gen_info.csv`、`gen_build_costs.csv`、`gen_build_predetermined.csv`，剔除 V19 新增候选后逐场景比较，16/16 一致。

因此 V19 不重写主线，而是在同一主线坐标系中回答“未来新增储能能否纠偏、如何纠偏”。

## 与 02_TARGETYEAR_SENSITIVITY
Layer A 使用的 `cheer_power_storage_targetyear_v17t2r5.jl` 与用户上传 02 包内同名核心做 SHA256/字节级校验，完全相同。V19 只修正未来候选输入证据与实验组织，不暗改 target-year 科学核心。

## 与 03_FULL8760_VALIDATION
03 继续独立冻结。V19 不能把代表日规划结果冒充完整 8760 可靠性。V19 提供 `build_v19_8760_validation_handoff.py`，将已求解的 2033 新增技术/MW/MWh/区域输出成显式 handoff，供后续兼容 03 的 full-8760 replay 使用。

在 replay 完成前：
- 可以发表容量扩张/技术竞争/空间机制结论；
- 不能声称 24 h+ 容量已通过完整 8760 或多天气可靠性认证。
