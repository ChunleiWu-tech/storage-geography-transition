# V18 中国未来储能多技术–多时长–空间协同规划上游包

版本：`V18_CHINA_FUTURE_STORAGE_PLANNING_TECH_DURATION_SITING_V1`  
基线：冻结的 V17T4R3 中国 32 模型区、多期发电–储能–跨省输电联合优化框架。

## 1. V18 回答的新问题

V17 的核心问题是既有储能空间遗产如何改变后续系统投资。V18 在不改变既有储能事实边界的前提下，把未来新增储能从单一固定时长通道升级为“技术–时长候选集”共同竞争，因此可以在同一个优化问题中内生决定：

- 哪个模型区/省区新增储能；
- 哪个投资期建设；
- 采用哪一类储能技术；
- 建多少功率容量（MW）；
- 建多少能量容量（MWh，候选技术对应可审计时长）；
- 储能与发电扩张、跨省输电扩张之间如何替代或互补。

**重要边界：**V18 当前“选址”是 32 个模型区/省区层级的系统规划选址，不是 GIS 站点级选址；没有可靠省级地质资源账本的 CAES 和氢储能不会进入 headline 结论。

## 2. 默认 headline 技术集

默认 `v18_storage_portfolio_mode=evidence_bounded`：

- LFP：4 h、8 h、10 h；
- VRFB：10 h、24 h；
- PSH：10 h、24 h。

以下只在 `full_pressure_test` 中开放：

- CAES：10 h、24 h、100 h；
- H2：24 h、100 h。

理由不是否定这些技术，而是当前包缺少足够可靠、可审计的中国省级盐穴/储氢地质容量账本。为了避免“无限地质资源”人为改变主结论，V18 默认将它们锁出 headline 优化。

## 3. 数据与证据规则

### 3.1 LFP

4 h 的长期成本轨迹继承 NREL/NLR 2025 `Cost Projections for Utility-Scale Battery Storage: 2025 Update` 的 low/mid/high 轨迹；8 h 和 10 h 不对 4 h 成本做任意线性按小时外推，而使用 PNNL ESGC v2024 在同一 100 MW Point 口径下的时长成本比进行缩放。

### 3.2 VRFB / PSH / CAES / H2

成本、固定运维、效率、寿命等基础性能来自随包冻结的官方 `PNNL Energy Storage Cost and Performance Database v2024`。当前数据库对所选非 LFP 技术没有可用的 2035 候选点，因此：

- 2028：只在数据库实际存在的源年份之间插值；
- 2033 及以后：默认冻结在 2030 证据基准；
- 不暗含 2030→2035 或更远年份的成本下降。

这是有意的保守处理。未来如加入 IEA/DOE/中国官方技术学习曲线，必须作为新证据版本或显式敏感性，不得无来源外推。

### 3.3 中国既有储能

V18 不改写 V17T4R3 已冻结的中国既有储能重建。既有 Battery / Hydro_Pumped / CAS 项目仍是历史存量载体；一旦启用 V18，旧 Battery 与 Hydro_Pumped 的“未来新增建设通道”被关闭，避免旧技术与 V18 新候选重复建设。

## 4. 时间耦合升级

V17 代表日主要承担日内循环。V18 默认 `storage_chronology_mode=monthly_linked`：每个投资期要求 12 个代表日，按代表日对应的年重复天数进行月间 SOC 递推，并检查 365 天/模型年的闭合关系。因此 V18 能识别跨月能量搬移需求，而不是强制每个代表日完全独立循环。

但这仍然不是完整 8760 小时连续运行，也不是多天气年规划。代码中明确：

- `STORAGE_FULL_CHRONOLOGICAL_CLAIM_SUPPORTED = false`
- `STORAGE_MULTIWEATHER_CLAIM_SUPPORTED = false`

原 V17 Full8760 包可作为 V18 的目标年验证模板，但不能把单一 2033/单天气年的验证自动解释为长期多天气可靠性结论。

## 5. 资源与选址边界

- PSH：V18 10 h/24 h PSH 与原 Hydro_Pumped 共享同一模型区资源上限，避免不同“时长标签”重复占用同一抽蓄资源。
- LFP/VRFB：作为非地质型模型区候选，目前不设置人为省级绝对资源上限；其空间选择由系统成本、既有网络、负荷/VRE 与输电共同决定。
- CAES/H2：缺少中国省级可审计资源账本，因此默认锁出 headline，只允许压力测试。
- `data/templates/storage_site_supply_curve_v18_optional_schema.csv` 提供下一阶段真实站址/资源供给曲线接口，但模板为空，不伪造数据。

## 6. 寿命与退化

V18 将 PNNL 的 calendar life 写入候选技术寿命，因此跨期资产退役/存续差异能够进入容量扩张模型。PNNL 的循环寿命信息同时保留在技术证据表中，但 R1 **不默认施加硬年循环次数或额外 throughput degradation cost**，因为现有 NREL/PNNL 固定 O&M/augmentation 与模型中再加退化成本可能发生双重计数。循环退化应作为独立敏感性版本处理。

## 7. 关键入口

Windows / PowerShell（建议 Julia + Gurobi）：

```powershell
cd <V18包根目录>
$env:JULIA_EXE = "C:\你的Julia目录\bin\julia.exe"
$env:V17_SOLVER_THREADS = "10"
.\CHECK_V18_STATIC.bat
.\RUN_V18_PREPARE_ALL_16.bat
.\RUN_V18_UPSTREAM_FULL_16_1x10.bat
```

V18 仍沿用已验证的 V17 环境变量命名，避免为了版本号重命名而破坏 Windows/Gurobi 运行链。

## 8. 当前验证状态

发布前应区分两类通过：

1. **STATIC / PREPARED INPUT PASS**：Python 源数据、候选技术、场景准备、Julia 静态结构与资源约束检查通过；
2. **SOLVER-CERTIFIED PASS**：必须在安装 Julia/Gurobi 的本地环境真正运行 16 场景，并由求解器返回原生 `OPTIMAL` 及物理审计通过。

本包不允许用静态检查代替求解器证书。

