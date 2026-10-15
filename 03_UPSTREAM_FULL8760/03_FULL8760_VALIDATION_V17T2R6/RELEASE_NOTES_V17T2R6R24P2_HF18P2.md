# V17T2R6R24P2-HF18P2 release notes

- 仅补跑 `TY2033_FULL8760_OBSERVED` 与 `TY2033_FULL8760_LDES_OBSERVED`。
- 两条 case 并行，每条严格 10 线程，总计 20 solver threads。
- 只读复用并校验 R24P1 已成功的两个 OPTIMAL 证书。
- 增加连续 LP 完整质量属性归因、缩放残差门控和 8 项原单位物理审计。
- 新输出、日志、尝试和锁均使用独立目录；不覆盖旧成功结果。
- 不包含任何 `sensitivity_cases` 输入，不改变科学数据、约束、RHS、目标或 8760 chronology。
- 最终生成两条补跑汇总和四条合并证书汇总。
