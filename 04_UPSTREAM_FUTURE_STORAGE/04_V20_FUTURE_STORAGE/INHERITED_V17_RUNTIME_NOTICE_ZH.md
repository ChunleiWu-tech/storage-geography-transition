# V19 包中的继承命名说明

V19 是新增的 04 科学扩展包。根目录只保留 V19 正式运行入口，以及 V19 实际调用的少量已验证运行依赖：`V17_ENV_DEFAULTS.bat`、`CHECK_V17_RUNTIME.bat` 和 `requirements_v17.txt`。

- `V17_*` 运行环境名保留，是为了复用已经验证过的 Windows + Julia/Gurobi 数值运行链；
- Layer B 的 Julia 核心保留内部 `V18_*` 技术标识，是为了保持冻结核心 SHA 不变；
- Layer A 模块保留内部 `V18R1_ENV_DEFAULTS.bat`，仅作为继承运行环境变量名，不代表科学版本；
- 所有正式科学入口、证据层级、场景契约、审计与输出均由 V19 根目录控制。

`inherited_v17_runtime/`、`inherited_v18_implementation/` 与 Layer A 中的 `inherited_v18r1_*` 目录仅用于来源追溯，不是 V19 正式入口。
