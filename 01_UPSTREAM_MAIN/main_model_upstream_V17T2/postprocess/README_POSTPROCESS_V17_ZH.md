# V17 后处理说明

后处理只接受晋级到 `outputs/<scenario>__main` 的正式第一阶段结果。preflight 核查：

- solver-certified Stage-1 经济最优证书与可行状态；
- `publication_solution_source=stage1_solver_certified_economic_optimum`；
- `stage1_official_release_pass=true`；
- 正式运行未执行第二阶段清理，且清理字段为非阻断；
- 物理审计、no-CDR 边界、legacy allocation 和导出闭合；
- `RESULT_INTERPRETATION_POLICY.csv` 完整；
- 三个毛流量文件逐行带有退化敏感和禁止运行机理解释标签。

`diagnostic_degeneracy_review_pass` 不再是硬门槛。即使毛流量存在明显退化，规划投资、容量、成本、年度聚合和净平衡仍可在其他严格审计通过后发布；毛流量本身只可用于核算重构和可复现性。

运行：

```powershell
.\RUN_V17_POSTPROCESS.bat
```
