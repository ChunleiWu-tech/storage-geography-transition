# 投稿最终版有效入口

唯一推荐的全新复现入口：

```bat
RUN_SUBMISSION_REPRODUCE_AND_CERTIFY_ALL4_HF18P2_R24P3_2X10.bat
```

该入口依次完成准备、两个 OPTIMAL 来源 case、两个 OBSERVED case，并且只有在 R24P2
返回非零时才尝试 R24P3。R24P3 会拒绝任何不是“唯一绝对互补性尺度门”的失败，因此不会
把不可行、未最优、来源错误或物理审计失败误放行。

如果服务器已保留完整 R24P2 attempt 和另外三个严格成功结果，只做后求解复证可运行：

```bat
RUN_V17T2R6R24P3_HF18P2_POSTSOLVE_RECERTIFY_ONLY.bat
```

其他历史 HF 启动脚本只用于失败路径审计，不属于投稿复现入口。
