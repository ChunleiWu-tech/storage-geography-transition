# V17T2：SL10 homogeneous-barrier no-crossover 专用修复

## 诊断结论

V17T1 的 SL10 第三条路线并非在 barrier 阶段无解。正式日志显示：

- homogeneous barrier 在 171 次迭代、约 2815 秒时已经报告 `Optimal objective`；
- 随后进入 crossover；
- crossover 额外执行约 1.318 million simplex iterations，最终达到 21600 秒上限；
- 因最终状态为 `TIME_LIMIT`，原发布门正确拒绝了该次运行。

因此，V17T2 不修改 SL10 的输入、碳约束、目标函数、物理约束或容差，只将同一条
hard homogeneous-barrier 路线的 `Crossover` 从 1 改为 0，直接返回 barrier 的内部最优
primal/dual solution。最终结果仍必须通过原 V17 的 solver-native `OPTIMAL`、物理审计、
导出审计和解释边界。

## 已完成 15/16 批次后的推荐运行

不要重跑 16 个场景，也不要删除 `outputs`、`batch_logs`、`storage_cases` 或批次摘要。
在现有 V17T1 结果文件夹运行：

```powershell
$env:V17_SOLVER_THREADS = "10"
.\RUN_V17T2_SL10_RESCUE_1x10.bat
```

脚本会：

1. 确认批次正好为 16 行且只有 SL10 失败；
2. 确认旧日志中 barrier 已最优而 crossover 超时；
3. 对其他 15 个 `__main` 输出建立字节级哈希保护；
4. 只运行 SL10 的 no-crossover homogeneous barrier；
5. 只有严格发布门全部通过时才提升为 `SL10...__main`；
6. 原子替换 SL10 摘要行并验证其他 15 个输出完全未变；
7. 执行完整 16 场景后处理预检。

成功标志：

```text
V17T2 SL10 RESCUE PASSED.
V17T2 SL10-only rescue and 16-scenario preflight PASSED.
```

然后运行：

```powershell
.\RUN_V17T2_POSTPROCESS.bat
```

## 从零复现

```powershell
$env:V17_SOLVER_THREADS = "10"
.\RUN_V17T2_UPSTREAM_FULL_16_1x10.bat
.\RUN_V17T2_POSTPROCESS.bat
```

从零路线中，SL10 优先使用 evidence-selected homogeneous barrier without crossover；
SL13 保持 V17T1 已经成功的隔离 hard-LP 路线；其余 14 个场景保持 V17/V17T1 逻辑。
