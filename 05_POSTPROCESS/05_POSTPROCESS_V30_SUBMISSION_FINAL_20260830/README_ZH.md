# 投稿统一后处理 V30：16 主场景 + 8 敏感性 + 4 FULL8760 证书 + 26 未来储能

本包是四套最终运行结果的只读统一后处理器。它不修改上游输入、模型或求解结果；任何结果不完整、非严格通过、来源不一致、单位不闭合或证书语义冲突都会在成图前终止。

读取采用项目编号到 `gen_info.csv` 技术/省份的一对一映射；储能建设量只保留声明的 Battery、PSH、VRFB、CAES、H2 技术集合。项目重复映射、缺失映射、非有限数、case 集合不精确、总量与分区/分项不闭合均为硬失败，程序不会猜列、补零或静默跳过。

## 科学递进与图序

1. `Fig.1–5`：既有储能空间遗产、等总量重配置价值、补偿投资与路径依赖（16 个主场景）。
2. `Fig.S12`：目标年 linked chronology、LDES 与 1 h 离散化边界（8 个敏感性场景）。
3. `Fig.6`：2033 年未来储能机会集能修复多少空间锁定，以及靠何种技术、位置和时长修复（V20 Layer A）。
4. `Fig.7`：2028–2058 纠偏路径、成本/证据边界，以及一个不抢主线的 continuous-8760 验证面板（V20 Layer B/C + FULL8760）。
5. `Fig.S13`：FULL8760 四个固定组合的完整 robustness-distance、firm/absorption、分区贡献与证书门。
6. `Fig.S14`：V20 完整边界与技术组合响应；不重复 Fig.6–7 的 headline panel。

最终为 **7 张主图 + 14 张补充图**。每张图同时输出 PDF、SVG 和 600 dpi PNG。

## 关键口径锁

- 主模型多期现值、目标年年度成本和 FULL8760 MW 距离绝不相加。
- FULL8760 正距离表示固定组合到连续全年可行性的技术中性最小理想局部灵活性缺口；它不是实际新增装机、系统成本或原组合可行性 PASS。
- V20 Layer B/C 采用 V17-native intraday-cyclic 代表时序，不产生跨月/季节运行主张。
- CAES/H2 expanded portfolio 只作压力测试，不作 headline 省域选址证据。
- 长期技术结论必须同时通过 evidence-direct、equal-evidence-horizon 和低/高电池成本边界。

## 另一台结果电脑的运行方法

把整个目录复制到结果电脑桌面。若结果仍在标准位置，只需双击或在 CMD 运行：

```cmd
RUN_ON_RESULT_COMPUTER_EDIT_PATHS.bat
```

默认项目根目录是：

```text
C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8
```

默认桌面根为 `C:\Users\Admin\Desktop`。如路径不同，只编辑该 BAT 最上面的路径变量，不要改 Python 代码。

字段来源、单位换算及四包目录契约见 `UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.md`；运行时会重新检查严格求解门与 V20 source/case/result SHA256，而不是只检查文件是否存在。

若结果电脑只负责读取和汇总数据、绘图在另一台电脑完成，运行：

```cmd
call RUN_V30_BUILD_ALL_REAL_TABLES_AND_PACK.bat
```

该入口不启动绘图或求解，也不写四个上游目录。它重新执行数据预检与科学审计，汇总五组表格目录、21 张图的逐图数据映射、来源证据及 SHA256 清单，并在桌面生成 `V30_ALL_REAL_TABLES_AND_AUDITS_20260830.zip`。

也可以显式传入四个根目录：

```cmd
RUN_V30_POSTPROCESS.bat ^
  "C:\path\main_model_upstream_V17T2" ^
  "C:\path\targetyear_sensitivity_upstream_V17T2R5" ^
  "C:\path\03_FULL8760_VALIDATION_V17T2R6" ^
  "C:\path\04_V20_FUTURE_STORAGE"
```

运行前可先执行：

```cmd
CHECK_V30_PACKAGE.bat
```

缺 Python 库时执行 `INSTALL_V30_PYTHON_DEPS.bat`。建议 Python 3.11。

## 结果位置

成功后输出到本包的 `postprocess_outputs`，并显示：

```text
V30 FOUR-ROOT STRICT POSTPROCESSING PASSED
```

权威最终门：`postprocess_outputs\audits\V30_POSTPROCESS_RELEASE_SUMMARY.json` 中 `status=PASS`、`figure_files_found=63`、`exact_figure_file_set=true`。

每次启动都先写到 `postprocess_outputs.__v30_working__`，全部 4+26 扩展结果和既有 16+8 结果通过后才原子替换正式输出；中途失败时保留上一版正式输出，不会产生“半套图”。四个上游目录全程只读。

相对差值只在优化端分母非零时定义；若优化值严格为零，CSV 中保留 `NA` 表示数学上不适用。发布门仍要求观测值、优化值和绝对差值全部为有限数，并禁止在非零分母下出现 `NA/Inf`，不会把未定义比例伪造为零。

六组稳健性配对中的电池功率/能量建设量采用带符号的“观测布局减优化布局”差值；负值是允许且必须如实呈现的方向变化，不会被强制改成正值。发布门核验六组完整、数值有限且具有变化；系统成本惩罚的正方向门继续保留。气泡大小使用功率差值的绝对幅度，横纵坐标仍保留真实符号。

目标年上游在未启用 LDES 时会把零行零列的 `ldes_proxy_build.csv` 写成 0 字节文件；后处理仅对六个注册表明确标记为非 LDES 的场景将其解释为“不适用/0 MW”。两个 LDES 场景仍必须提供完整表头和候选技术行；任何其他必需 CSV 无表头仍为硬失败。

V20 Layer-A 的 batch summary 仅作为可重建索引，不覆盖逐 case 正式证据。若单 case 补跑造成 summary 漏行，后处理只允许从该 case 的正式 `future_correction_outputs/<case>__main` 重建索引行，并重新核验严格求解门、场景注册表及 source/case/result SHA256；从不读取 `_attempts`。FC08 若采用 HF5 exact reduced formulation，还必须通过等价投影字段、能量恒等式、模型与 runner 哈希及 HF5 lineage 审计。

Gurobi 原生状态兼容冻结结果的两种列名：Layer A 的 `stage1_gurobi_status` 与后续结果的 `gurobi_status`。无论使用哪个列名，数值都必须严格等于原生 OPTIMAL 状态 2；若两列同时存在则必须同时为 2，并且 `stage1_gurobi_status_gate_pass`、`stage1_gurobi_objval_gate_pass`、`stage1_objective_scale_gate_pass` 仍全部为真。

FULL8760 最终 R24P3 combined set 是混合版本的正式证书集合：两个受保护的 R24P1 成功证书与后续 R24P2/R24P3 质量恢复证书共同构成四 case。四者均强制核验共同原生门、证书 JSON、固定组合 lineage、结果文件指纹、分项及分区闭合；R24P2/R24P3 另外强制其新增的 componentwise、MaxVio decomposition、scaled residual 和 core physical gates。不会错误要求 R24P1 必须拥有尚未定义的后版本字段。

FULL8760 存在两个不同科学体系，后处理禁止混用。早期“8760 经济再优化”结果不进入本模块；本模块只读取 `V17T2R6R24P3_HF18P2_COMBINED_ALL4` 指定的四个固定组合稳健性证书，并要求 `robustness_distance_only` lineage、科学模型/8760 chronology/source portfolios 均未改变、正式 `__main` 输出及结果 SHA256 全部闭合。报告的 MW 是最小理想本地灵活性距离，不是经济成本、实际技术建设量或经济再优化结果；任何 `_attempts` 历史目录都不参与制表。

数值质量字段按证书版本分层。R24P1 已定义的 objective readback、primal-dual gap、ConstrVio、BoundVio、DualVio、ComplVio 必须为有限数；R24P2/R24P3 另外必须具有全部 componentwise、unscaled/scaled residual、MaxVio decomposition 和核心物理诊断。R24P1 当时尚未定义的 scaled-residual 字段在表中明确留空并标记 `available=false`，不会伪造为 0，也不会被错误用于跨版本数值比较。

目标年 8 个 case 只从 `sensitivity_outputs/<scenario>__main` 读取，并重新核验原生 Gurobi 状态、求解证书及 publication gates。`V17T2R5_run_summary.csv` 和 `PUBLICATION_RESULT_LINEAGE.json` 是可重建索引：完整且与正式结果一致时复核其 SHA256；因补跑/resume 出现乱序、漏行或旧哈希时，只在审计中披露，并直接从八个注册 case 的 source fingerprint、case metadata 和正式 `solve_status.csv` 现场重建硬谱系，再逐 case 运行全部求解、物理、时序及闭合门。三个准备阶段 case 审计 JSON 若仍在则附加核验 SHA256；若结果电脑未保留则记录缺失，但不代替或放宽正式结果硬门。历史 `_attempts` 从不参与制表。

## 成图格式

`postprocess/ne_style.py` 与 0809 参考包逐字节一致。版宽、字体、字号、配色、面板标签、留白、PDF/SVG/PNG 输出规则全部沿用；新图只扩展科学内容，不更换视觉体系。

新增 Fig.6、Fig.7、Fig.S13、Fig.S14 已做独立合成版式 QA；合成数据和合成图片不包含在交付包，也不能用于论文数值。另一台电脑上的真实结果必须重新通过所有数据门后才会生成正式图片。
