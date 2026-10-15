# 先运行这个

1. 把本目录完整复制到存放四套成功结果的电脑。
2. 确认结果位于 `C:\Users\Admin\Desktop\01_UPSTREAM_16PLUS8`；默认 `DESKTOP_ROOT=C:\Users\Admin\Desktop`，若不同只编辑 `RUN_ON_RESULT_COMPUTER_EDIT_PATHS.bat` 顶部路径变量。
3. 先运行 `CHECK_V30_PACKAGE.bat`。
4. 若只需带回全部真实绘图表格和审计证据，运行 `call RUN_V30_BUILD_ALL_REAL_TABLES_AND_PACK.bat`。成功后桌面生成 `V30_ALL_REAL_TABLES_AND_AUDITS_20260830.zip`；该入口不绘图、不求解、不写上游结果。
5. 若在结果电脑直接完成全部绘图，则运行 `RUN_ON_RESULT_COMPUTER_EDIT_PATHS.bat`。
6. 只有看到 `V30 FOUR-ROOT STRICT POSTPROCESSING PASSED` 才进入论文使用。

本包不会重新求解，也不会改动四套上游；它只读取已经成功的 16 + 8 + 4 + 26 套证据并生成统一表格、图片和手稿文字草稿。

若任一目录、case、原生 OPTIMAL 状态、来源指纹、物理审计、单位或闭合关系不一致，程序会在成图前停止；不要手工补表或跳过失败门。

字段来源、单位和四包目录契约见 `UPSTREAM_ALIGNMENT_AND_UNIT_AUDIT_V30.md`。实际运行会再次核验四根路径、54 条结果和 V20 source/case/result SHA256。
