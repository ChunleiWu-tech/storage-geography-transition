# 当前后处理 20261015R2

render_ees.py 从74份锁定表绘制7幅主图和14幅补图。图件包含模型输入统计、保留的模型结果汇总及派生指标，不宜全部称为求解器原始输出。本轮74表的值与哈希未变，21图的PNG/PDF/SVG全部重新生成。layout_final_science.py修正36处棒棒糖标签，并添加Fig. 2e和Fig. 7b标注。

先运行verify_tables.py、verify_scientific_quantities.py、test_manifest_paths.py，再运行render_ees.py all。重绘后需同步Word嵌图、重新导出PDF及重建整包。0830包的代码、输入、汇总表追溯见../核查记录/0830数据追溯。完整原始求解输出和日志仍未在本地找到；本轮没有重新求解模型。
