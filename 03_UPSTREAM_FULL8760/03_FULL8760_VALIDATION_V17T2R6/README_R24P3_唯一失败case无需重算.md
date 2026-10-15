# R24P3：唯一失败 case 的可追溯后处理复证

正确日志来自最新 R24P2：Gurobi 原生 `OPTIMAL`，primal/dual 均有解，scaled primal/dual residual、来源门以及 8 项原始单位物理审计均通过。唯一旧门失败是：

- `ComplVio = 1.5551060672476587e-4`
- 旧绝对阈值：`1.0e-4`
- robustness objective：约 `105450.4184 MW`
- 尺度化互补性：约 `1.4747e-9`
- 求解时 `BarConvTol = 1.0e-8`

Gurobi 官方将 `ComplVio` 定义为变量值与 reduced cost 乘积的最大值，并说明 barrier 内点解中它不一定严格为零；`BarConvTol` 则综合相对 primal/dual objective、相对可行性和 complementarity 判定 `OPTIMAL`。因此 R24P3 保留全部原始数值，只把唯一的“绝对互补性”门改成与既定 `BarConvTol` 一致的尺度化门。

官方依据：

- https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/quality.html
- https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-BarConvTol

运行：

```bat
cd /d C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8\03_FULL8760_VALIDATION_V17T2R6
call RUN_V17T2R6R24P3_HF18P2_POSTSOLVE_RECERTIFY_ONLY.bat
```

该命令不会调用 Gurobi、不会重新构建或求解模型，通常数秒内完成。它会自动寻找 `TY2033_FULL8760_OBSERVED` 最新且“仅因旧 ComplVio 绝对门失败”的 R24P2 attempt；任何其他门失败都会拒绝复证。

成功标志：

- `POSTSOLVE COMPLEMENTARITY RECOVERY PASS`
- `COMBINED ALL FOUR CERTIFICATES COMPLETED`

三个成功结果在处理前后均做目录树哈希，不覆盖、不移动、不重算。原 R24P2 失败版 `solve_status`、certificate 和 quality attribution 会原样另存，完整保留审计链。

