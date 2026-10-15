# 04_FUTURE_STORAGE_PLANNING_V18 — 中国未来储能优化配置上游包

发布日期：2026-08-09  
科学版本：`V18_CHINA_FUTURE_STORAGE_PLANNING_TECH_DURATION_SITING_V1`

## 0. 与 01–03 的关系

本包是**新增的 04**，不是 01/02/03 的覆盖升级。

- `01_MAIN_UPSTREAM_V17T4R3`：冻结，不修改；
- `02_TARGETYEAR_SENSITIVITY_V17T2R5`：冻结，不修改；
- `03_FULL8760_VALIDATION_V17T2R6R7`：冻结，不修改；
- `04_FUTURE_STORAGE_PLANNING_V18`：在冻结 V17 科学基线上新增“未来储能类型–时长–容量–空间–年份”规划。

随包 `audits/FROZEN_01_02_03_PARENT_PACKAGES_SHA256.json` 记录三套父包的 SHA256；`audits/V18_V17_LEGACY_IMMUTABILITY_AUDIT.json` 对 16 个正式场景逐一证明 V18 注入前后所有非 `V18_*` 的 `gen_info`、`gen_build_costs` 与既有 predetermined MW/MWh 未被改写。

## 1. 04 新回答什么

V18 在 32 个中国模型区、多投资期发电–储能–跨区输电联合规划框架中，新增可审计的技术–时长候选。模型可内生决定：

1. **Where**：在哪个模型区/省区建设；
2. **When**：在哪个投资期建设；
3. **What**：采用 LFP、VRFB、PSH 等哪种技术；
4. **Power**：建设多少 MW；
5. **Energy/Duration**：建设多少 MWh，以及技术–时长组合；
6. **Network interaction**：储能与发电扩张、跨区输电扩张之间的替代/互补。

R1 不宣称 GIS 站点级选址。没有可靠省级地质资源账本的 CAES/H2 仅进入压力测试，不进入 headline 结论。

## 2. Headline 技术组合

默认：`v18_storage_portfolio_mode=evidence_bounded`

- LFP：4 h / 8 h / 10 h；
- VRFB：10 h / 24 h；
- PSH：10 h / 24 h。

压力测试：

- CAES：10 h / 24 h / 100 h；
- H2：24 h / 100 h。

V18 不使用“任意连续时长 + 无来源成本插值”。每个技术–时长候选均对应可追溯的成本/效率/寿命证据；总 MW、总 MWh、平均等效时长及技术份额由候选竞争内生形成。

## 3. 数据证据

- LFP 4 h 未来成本轨迹：NLR/NREL 2025 官方 `Cost Projections for Utility-Scale Battery Storage: 2025 Update`；
- LFP 8/10 h：NLR/NREL 2025 的年度 4 h 轨迹 × PNNL v2024 同口径时长成本比；
- VRFB / PSH / CAES / H2：PNNL ESGC `Energy Storage Cost and Performance Database v2024`；
- 中国现状与技术结构边界：国家能源局公开数据；
- Nature Communications 文章仅用于支持“空间异质性、长时储能机制、多天气/极端天气验证设计”，**不把国外容量结果当作中国参数**。

详细来源、用途与结论防火墙见 `docs/V18_SOURCE_LEDGER.csv` 与 `docs/V18_EVIDENCE_VERIFICATION_20260809_ZH.md`。

## 4. 时间与长时储能结论边界

默认：`storage_chronology_mode=monthly_linked`。

每个投资期使用 12 个代表日，并按各代表日的年重复天数链接月际 SOC；必须满足 365 天/模型年闭合，并检查重复序列末态 SOC 与备用可交付性。因此：

- **允许**：讨论“月际联结代表时间框架下”的中长时储能规划、技术–时长竞争和跨月能量搬移机制；
- **禁止**：把它称为完整连续 8760、多天气年可靠性证明，或据此宣称精确的季节储能容量。

求解状态证书必须同时满足：

- `storage_chronology_mode = monthly_linked`；
- `v18_storage_portfolio_mode = evidence_bounded`；
- `storage_intermonth_soc_linked = true`；
- `storage_long_duration_claim_supported = true`（仅代表时间规划语义）；
- `storage_full_chronological_claim_supported = false`；
- `storage_multiweather_claim_supported = false`。

## 5. Windows 本地运行

PowerShell：

```powershell
cd <04_FUTURE_STORAGE_PLANNING_V18 包根目录>
$env:JULIA_EXE = "C:\你的Julia目录\bin\julia.exe"
$env:V17_SOLVER_THREADS = "10"

.\CHECK_V18_STATIC.bat
.\RUN_V18_PREPARE_ALL_16.bat
.\RUN_V18_UPSTREAM_FULL_16_1x10.bat
```

如果只做一个 CAES/H2 压力测试：

```powershell
.\RUN_V18_ONE_PRESSURE_TEST.bat SL00_OBSERVED_ACTUAL
```

其结果带 `__v18_pressure_test` 后缀，并明确不进入 headline V18 16 场景严格证书。

> `V17_ENV_DEFAULTS.bat`、`CHECK_V17_RUNTIME.bat` 以及部分内部脚本仍保留 V17 命名，是因为它们属于已经验证过的 Windows/Gurobi 数值运行链；04 没有因此修改 01–03。

## 6. 当前发布门状态

当前容器已完成：

- V18 静态科学审计 R3：**23/23 PASS**（含 16 个正式 prepared cases）；
- Julia 静态语法审计：**26/26 PASS**；
- 空集合安全审计：**8/8 PASS**；
- 数值稳定性静态审计：**25/25 PASS**；
- V17 legacy 输入不可变性交叉检查 R2：**16/16 PASS**；
- 16 个正式场景 prepared input：**16/16 PASS**。

当前容器**没有 Julia/Gurobi 求解运行时**，因此本发布包不声称 `SOLVER-CERTIFIED 16/16 PASS`。这一门只能由你本地运行 `RUN_V18_UPSTREAM_FULL_16_1x10.bat` 后获得。

## 7. 首选阅读顺序

1. 本文件；
2. `README_V18_UPGRADE_ZH.md`；
3. `docs/V18_MODEL_SPEC_ZH.md`；
4. `docs/V18_VALIDATION_AND_CLAIM_BOUNDARY_ZH.md`；
5. `docs/V18_EVIDENCE_VERIFICATION_20260809_ZH.md`；
6. `data/processed/v18_storage_technology_portfolio.csv`；
7. `audits/V18_STATIC_AUDIT.json`。
