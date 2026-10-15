# V18R1：既有储能空间锁定的最低成本纠偏规划

## 1. 为什么单独成包

V18R1 **不是替换 V17，也不修改 V17 的诊断性科学模型**。V17 回答“既有储能空间布局是否造成未来系统锁定及其代价”；V18R1 在这一发现之上单独回答：

> 在既有储能资产已经形成的前提下，2033 年未来新增储能应当在哪里配置、配置多少功率/能量、选择什么技术与持续时长，才能以最低系统成本削弱既有储能空间锁定？

把“诊断层”和“纠偏层”拆开，可以避免为获得更好的未来结果而反向改变 V17 的历史反事实定义，从而保持识别边界清楚。

## 2. 冻结科学核心与范围边界

V18R1 直接复用并锁定 V17T2R5 target-year Julia 科学核心：

`base_model_v39/cheer_power_storage_targetyear_v17t2r5.jl`

SHA-256：

`2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84`

V18R1 是**2033 单目标年 capacity + dispatch re-optimization**。模型保留存续历史资产，把既有新型储能地理分布作为受控初始遗产，在 2033 年内生选择未来新增容量与地点。为避免不受证据支持的时间路径外推，R1 **不声称识别 2025–2050 的最优建设年份路径**；也不声称使用 8760 h，时间结构保持冻结的 12 个代表月、72 个 4 h timepoints、monthly-linked SOC。完整 8760 仍由 V17 的独立验证包承担。

> 数据中的 2023 build-year 标签是冻结 SWITCH/V17 建模锚点；本文的 inherited-storage stock 证据基准是模型中已声明的 end-2025 legacy stock。V18R1 不把该标签重新解释为真实 2023 年库存。

## 3. V18R1 的 8 个 case

V18R1 采用 4 个严格 matched pairs。每个 pair 内 observed 与 optimized 成员的非地理科学输入完全一致，只允许既有 Battery geography 处理不同。

| Pair | Observed | Optimized | 作用 |
|---|---|---|---|
| FC_BASE | FC01 | FC02 | 冻结 V17 未来储能机会集，测量基准剩余锁定 |
| FC_ADAPTIVE | FC03 | FC04 | **主纠偏实验**：允许 evidence-bounded 技术/容量/选址/持续时长选择 |
| FC_ADAPTIVE_TXFIXED | FC05 | FC06 | 无新增跨省输电，辨识 storage–transmission substitution |
| FC_EXPANDED_PRESSURE | FC07 | FC08 | 扩展技术集压力测试；不用于省级 CAES/H2 部署预测 |

主论文的定量纠偏结论只由 **FC01–FC04** 支撑。FC05–FC08 只用于稳健性边界。

### Evidence-bounded 主技术机会集

冻结 V17 中已有的 4 h Li-ion 与基础抽蓄仍可内生新增；FC_ADAPTIVE 另外加入由打包 PNNL v2024 数据表得到的 2033 离散候选：

- VRFB 10 h
- VRFB 24 h
- PSH 10 h
- PSH 24 h

VRFB 作为通用电化学候选，不人为施加自然资源上限；PSH 10/24 h 与冻结模型的 `Hydro_Pumped` 共享同一 zone-specific resource ceiling，避免复制抽蓄资源潜力。

扩展压力测试再加入 CAES 10/24/100 h 和 H2 100 h。由于包内没有足够严格的省级 CAES/H2 资源 ledger，这些候选只用于“如果技术机会进一步扩大，核心锁定结论是否改变”的压力测试，**不得解释成省级选址预测**。

## 4. 纠偏指标

令基准未来机会集下的 matched legacy penalty 为：

`L_base = C(FC01_BASE_OBSERVED) - C(FC02_BASE_OPTIMAL)`

允许 evidence-bounded adaptive storage 后的剩余 penalty 为：

`L_adaptive = C(FC03_ADAPTIVE_OBSERVED) - C(FC04_ADAPTIVE_OPTIMAL)`

定义模型内的纠偏价值与修复比例：

`Correction value = L_base - L_adaptive`

`Repair fraction = (L_base - L_adaptive) / L_base`

该 repair fraction 是**严格 matched model difference-in-differences 指标**，用于刻画扩大未来储能机会集后剩余空间锁定代价减少了多少；它不是现实历史的统计因果估计。代码不会把该比例强制裁剪到 0–100%，若出现负值或大于 1，应作为模型结果解释而不是隐藏。

## 5. 独立主图 Fig. 6

V18R1 输出一张独立的 6-panel 主图：`Fig6_future_correction_of_storage_spatial_lockin`。其逻辑是“锁定代价 → 修复程度 → 建什么 → 建在哪里 → 持续多久 → 由储能还是输电完成补偿”。

- **a**：Baseline vs Adaptive residual legacy penalty + repair fraction（dumbbell/direct labels）
- **b**：Adaptive technology mix，Observed vs Optimized inheritance（紧凑技术组合）
- **c**：Observed inheritance 下的 province × technology 新增功率矩阵（高信息密度 heatmap）
- **d**：各省 power-weighted storage duration + 新增规模（lollipop + marker size）
- **e**：Adaptive minus Baseline 的补偿性投资变化（diverging comparison）
- **f**：TX-fixed 与 expanded-portfolio 的 residual-lock-in robustness（主结论实心、压力测试空心）

图形沿用现有高端 Nature-family 规范：180 mm、Arial-first、a–f 左上角面板标、顶部/直接图例、低对比网格、无巨型总标题、PDF/SVG/600-dpi PNG 三格式。零值或无信息类别不会为了填满版面而强行展示。

## 6. Windows 推荐运行顺序

首次环境安装（已有环境可跳过）：

```cmd
call INSTALL_V18R1_PYTHON_DEPS.bat
call INSTALL_V18R1_JULIA_DEPS.bat
```

先验证包和 Gurobi runtime：

```cmd
call CHECK_V18R1_PACKAGE.bat
call CHECK_V18R1_RUNTIME.bat
```

准备全部 8 个受控输入：

```cmd
call RUN_V18R1_PREPARE_ALL_8.bat
```

推荐先只跑决定主结论的 4 个 case：

```cmd
call RUN_V18R1_PRIMARY_4_1x10.bat
```

主 4 个严格通过后，再跑 4 个稳健性/压力测试：

```cmd
call RUN_V18R1_ROBUSTNESS_4_1x10.bat
```

或从已准备输入顺序运行全部 8 个：

```cmd
call RUN_V18R1_ALL_8_1x10.bat
```

全部 8 个只有在 solver-native `OPTIMAL`、primal/dual `FEASIBLE_POINT`、物理/时序/export/result-lineage gate 全部通过后，才允许生成最终表和 Fig. 6：

```cmd
call RUN_V18R1_BUILD_SUMMARY_AND_FIG6.bat
```

完全从零重建并运行：

```cmd
call RUN_V18R1_CLEAN_REBUILD_AND_RUN_ALL_8_1x10.bat
```

## 7. 求解器发布规则

所有成员共享同一预先声明的 exact-LP 求解 ladder，并在获得第一个严格 solver-native OPTIMAL 时停止：deterministic concurrent → homogeneous barrier/crossover cleanup → scaled barrier/no crossover → direct dual simplex → deterministic concurrent simplex。算法选择只影响数值求解，不改变科学输入。

`TIME_LIMIT`、`ITERATION_LIMIT`、`NO_SOLUTION`、未通过物理审计或 export gate 的结果均不得提升为正式结果，也不得进入 Fig. 6。

## 8. 最终科学解释边界

V18R1 可以回答：**2033 年在既有空间遗产约束下，未来新增储能的容量、模型省/区选址、声明技术与离散持续时长如何共同优化，以及这些选择可减少多少 residual legacy lock-in。**

V18R1 不能单独回答：2025–2050 每一年何时建设、真实项目级站址、未建资源 ledger 的 CAES/H2 省级部署、或全年 8760 h 运行细节。上述边界在 scenario metadata、case validator、summary builder 与图表解释中均 fail-closed 锁定。
