# 04_V20_FUTURE_STORAGE — 运行优先最终包

## 1. 科学问题

V20 是独立的加法式 `04` 包，不修改已经冻结的 01/02/03。

已有 V17 主线回答：

> 既有储能空间布局是否形成可量化、可持续的 spatial lock-in？

V20 回答下一层：

> 在既有储能空间遗产不可凭空搬迁的前提下，未来新增储能应在何地、以何种技术/时长、建设多少、何时建设，才能以最低系统成本修复这种历史空间锁定？

## 2. V20 三层 required design

### Layer A — 2033 correction identification：8 cases

4 个严格 Observed–Optimal matched pairs：

- FC01 / FC02 — BASE；
- FC03 / FC04 — ADAPTIVE；
- FC05 / FC06 — ADAPTIVE + TX fixed；
- FC07 / FC08 — expanded geologic pressure test。

这里回答“能修多少、靠储能还是输电、扩大技术集合后结论是否改变”。

### Layer B — 2028–2058 evidence-direct pathway：16 cases

继承冻结的 16 个空间遗产主场景，联合优化：

- 发电扩张；
- 储能功率；
- 离散技术—时长组合；
- 32 个模型区的新增配置；
- 2028/2033/2038/2043/2048/2053/2058 建设年份；
- 跨区输电扩张。

Headline portfolio：LFP 4 h、VRFB 10/24 h、PSH 10/24 h。CAES/H2 只允许 pressure test。

**V20-HF2 temporal identification policy：** Layer B/C 的 headline pathway 不再把 linked-month chronology 与 future-portfolio expansion 同时引入。主运行显式保持 V17 已验证的 `intraday_cyclic` 代表日时序，从而把结构干预严格限定为“未来技术—时长—空间—年份机会集”。因此 Layer B/C 不支持跨月/季节运行价值主张；10/24 h 是离散投资设计标签，运行价值仍在代表日内评估。linked-month 仅通过 `RUN_V20_B2_FEASIBILITY_ISOLATION_DIAGNOSTIC_1x10.bat` 做非出版诊断。

### Layer C — equal-evidence-horizon：2 cases，V20 新增且必须运行

- `V20EH01_OBSERVED`
- `V20EH02_OPTIMAL`

V19 的真实证据边界是：LFP 4 h 有 NLR/NREL 2025 的 2030 后直接年度成本轨迹，而 PNNL v2024 的多技术 BAU 基准对 VRFB/PSH 只支持到 2030。V20 不虚构 VRFB/PSH 的 2058 学习率，而增加一个 matched sensitivity：只把 LFP 在 2033–2058 的未来建设 CAPEX/FOM 固定到 NLR 2030 mid 直接值，其余 scientific inputs 与 SL01/SL02 byte-identical。

因此，长期“技术赢家”只有在 evidence-direct、equal-horizon 和既有 low/high battery-cost sensitivity 下都稳健时，才允许作为 headline claim。

## 3. 权威证据与 V20 的处理

- NLR/NREL 2025 `NREL/TP-6A40-93281`, DOI `10.2172/2583471`：4 h utility-scale lithium-ion 年度 low/mid/high 轨迹。随包 transcription 的关键锚点为：2030 = 207/279/354，2035 = 147/243/339，2050 = 108/178/307，2058 = 97/161/299（2024 USD/kWh）。
- PNNL Energy Storage Cost and Performance Database v2024：统一多技术 benchmark；V20 对 VRFB/PSH 不做 source horizon 之外的外推。
- DOE Storage Innovations 2030 Methodology、Flow Battery、PSH、CAES、Bidirectional Hydrogen assessments 与 2024 LDES summary：用于 RD&D / innovation evidence、地质/基础设施依赖和 claim boundary；**不把 LCOS 或创新降幅直接当成 whole-system CAPEX multiplier**。

详细证据和 SHA256 在 `data/processed/v20_authoritative_evidence_ledger.csv` 与 `docs/V20_EVIDENCE_POLICY_ZH.md`。

## 4. 为什么 V20 比 V19 更严谨

V20 不用“给每种技术都画一条漂亮的 2058 学习曲线”来制造表面对称，而是显式承认证据时间边界不同，并通过 mandatory equal-horizon matched pair 检验长期技术竞争是否被证据边界驱动。

同时保留：

- Layer A target-year Julia core SHA256 = `2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84`；
- Layer B dynamic Julia core 在 HF2 做了**限域科学修复**：保留 V20/HF1 的全部 scientific input CSV，不改变成本、技术集合、政策或目标函数；仅修复 2023 optimized-legacy stock 被“future-build”禁建约束误伤的问题，并使时序 claim 随实际 runtime mode 输出。当前 HF2 core SHA256 由 `CHECK_V20_STATIC.bat` 锁定；父版 HF1 SHA256 = `1469b3168e5040486b091732bc58782d69501f014d5579bc1a638a920ec99eab`；
- PSH 10/24 h 共享既有区域 PSH resource ceiling；
- CAES/H2 province siting claim firewall；
- Layer A 保留 monthly-linked 2033 correction chronology；Layer B/C headline 则显式采用 **V17-native intraday_cyclic representative-day chronology**，以避免把“未来技术组合扩展”和“时序模型改变”同时作为干预；monthly-linked 只作为独立诊断/敏感性，不作为 Layer B/C headline 结果；full-8760 仍由 03 包单独验证。

## 5. Windows 放置建议

为了避免长路径，解压后的根目录直接保持短名：

```text
<PROJECT_ROOT>\04_V20_FUTURE_STORAGE
```

源文件已经改成短、可读文件名；原始来源信息与 SHA256 由 evidence ledger 保存。

## 6. 最推荐的运行顺序

CMD：

```cmd
cd /d "<PROJECT_ROOT>\04_V20_FUTURE_STORAGE"

set V17_PYTHON=py -3.11
set JULIA_EXE=julia
set V17_SOLVER_THREADS=10

call CHECK_V20_MANIFEST.bat
call CHECK_V20_STATIC.bat
call CHECK_V20_RUNTIME.bat
call PREP_V20.bat
```

V20-HF2 已针对 Layer B 的实际运行反馈做了限域修复：

**如果你已经在 HF1 中得到 Layer A 4/4 strict PASS，而失败发生在 Layer B，HF2 不要求先重跑 Layer A。** 新包通过 manifest/static/runtime gate 后，可先运行 `RUN_V20_HF2_RETEST_B2C2_4_1x10.bat`，只重测 B2+C2 四个关键 case；四个全部 strict PASS 后，再运行标准 Phase 1/Phase 2，resume-safe runner 会跳过当前包中已经存在且 fingerprint 有效的 B/C 结果。不要把 HF1 的旧输出目录手工复制进 HF2。

- `SL02_OPTIMAL_REALLOCATION` 的 2023 legacy Battery 重新配置不再被 `V18_Disable_Legacy_*_Future_Build` 误锁为 0；
- Layer B/C headline runner 显式从 runtime contract 读取 `intraday_cyclic + evidence_bounded`，不依赖隐藏默认值；
- linked-month infeasibility 继续由模型内置 `infeasibility_conflict_constraints.csv` / `infeasibility_context.json` 和可选 diagnostic launcher 追踪，但不阻断 headline 动态规划。

然后采用 **run-first 两阶段顺序**。先只跑最能决定科学方向和数值稳定性的 8 个 case：

```cmd
call RUN_V20_PHASE1_CORE_8_1x10.bat
```

Phase 1 = Layer A 的 BASE/ADAPTIVE 4 个 matched cases + Layer B 的 observed/optimal dynamic core pair + Layer C 的 equal-evidence-horizon pair。只有这 8 个都严格通过，再继续：

```cmd
call RUN_V20_REMAINING_18_1x10.bat
```

第二阶段会自动补齐 Layer A 8/8、Layer B 16/16，并再次核验 Layer C 2/2；已经存在且满足 solver-native strict gate + current result fingerprint 的 Phase-1 结果会跳过，不重复浪费长算时。

也保留分层单独入口：`RUN_V20_A8_1x10.bat`、`RUN_V20_B16_1x10.bat`、`RUN_V20_C2_EQUAL_HORIZON_1x10.bat`。

如果想一次性：

```cmd
call RUN_V20_REQUIRED_26_1x10.bat
```

完整 26-case 运行矩阵见 `docs/V20_REQUIRED_26_CASE_MATRIX.csv`。

26/26 全部严格通过后：

```cmd
call BUILD_V20_RESULTS.bat
```

## 7. 结果接受条件

不接受 time-limit incumbent，不接受近似结果。进入 V20 正式结果表必须满足模型冻结的 strict solver-native gate，包括：

- `OPTIMAL`；
- primal / dual `FEASIBLE_POINT`；
- strict physical audit；
- strict export；
- source → case → result fingerprint chain；
- evidence-bounded storage portfolio；
- Layer A：monthly-linked chronology；Layer B/C：按 `data/processed/v20_layer_b_runtime_contract.csv` 强制 `intraday_cyclic`；
- CDR exclusion gate。

## 8. Fig.6 / Fig.7 暂不锁死

先求解。真实数值出来后再按信息密度决定：

- 若 6 个 panel 足以清楚回答“修复比例—技术—空间—建设时序—输电协同—稳健性”，用一张 Fig.6；
- 若长期 pathway 信息过密，则 Fig.6 放 2033 correction，Fig.7 放 2028–2058 dynamic pathway + evidence-horizon robustness。

不为了少一张主图而牺牲可读性，也不在没有真实结果前预设视觉叙事。

### V20-HF3 current execution note
HF3 supersedes HF2 for Layer B/C. A local HF2 run exposed a structural `Hydro_Pumped` capacity-plan bookkeeping conflict: future legacy PSH build rows were disabled while the inherited PSH planning floor counted only those legacy rows. HF3 maps that floor to the physical PSH family (legacy `Hydro_Pumped` + `V18_PSH_10h` + `V18_PSH_24h`) without changing the shared provincial resource ceiling or any case input CSV. First targeted rerun: `RUN_V20_HF3_RETEST_B2C2_4_1x10.bat`.
