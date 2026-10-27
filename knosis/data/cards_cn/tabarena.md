# TabArena —— 单表预测的活基准（51 个精选数据集）

## 来源

Erickson et al., **TabArena: A Living Benchmark for Machine Learning on Tabular Data**，
NeurIPS 2025 Datasets & Benchmarks，arXiv **2506.16791**。
代码 https://github.com/autogluon/tabarena ；数据集策展 https://github.com/TabArena/tabarena_dataset_curation ；
数据是 OpenML task suite **457**（别名 `tabarena-v0.1`）https://www.openml.org/search?type=study&study_type=task&id=457 。

获取：`knosis download tabarena`（需要 `openml` 包；把每个 task 导出成 `data/tabarena/<数据集名>/` 下的
`data.parquet` + `splits.parquet` + `meta.json`）。只取部分数据集：`--include <数据集名>`，可重复。

**许可：** 51 个数据集都是公有领域许可，这是 TabArena 策展的入选条件之一。

OpenML 服务器经常很慢（实测逐个请求约 3 分钟一个数据集）。TabArena 维护者提供了 OpenML 缓存的备份（305 MB）：
https://data.lennart-purucker.com/tabarena/openml_dataset_backup/ 。把 zip 里的 `.openml-cache/` 合并到
`data/tabarena/.openml/` 后再跑 `knosis download tabarena`，51 个数据集约 20 秒导出完。

## 说明

TabArena 是 TabPFN-2.5、TabICL、Mitra、LimiX 等表格基础模型与树模型、AutoML 同台比较的主榜单。
51 个数据集是从 1053 个候选里按「真实、独立同分布、有代表性、许可干净」筛出来的，
覆盖二分类、多分类、回归，规模从几百行到约 10 万行、最多约 2000 个特征。

**每个数据集一个 scenario**：`load_dataset("tabarena", "<数据集名>")`。`list_scenarios("tabarena")` 列出本地已导出的。

**数据形态：**
- `ds.read("data")` —— 整张表（DataFrame），**含目标列**，目标列名在 `ds.schema["target"]`。
- `ds.schema` —— `target` / `problem_type`（binary / multiclass / regression）/ `categorical`（类别特征列）/
  `n_rows` / `n_features` / `description`（OpenML 上的数据集说明）。
- `ds.tasks` —— 每个官方 repeat × fold 划分一个任务，`meta["train"]` / `meta["test"]` 是行号，
  `answer` 是测试行的目标值。**评测之外不要读 `answer`，也不要从整表里取测试行的目标列。**

**官方口径：**
- 指标：二分类 ROC-AUC，多分类 log loss，回归 RMSE；跨数据集用 Elo 聚合。
- 必须用官方划分，不要自己重新切。每个 OpenML task 都带 10 个 repeat × 3 个 fold（共 30 个任务）；
  TabArena 正式评测按数据集规模只用其中一部分 repeat，口径以 TabArena 代码为准。
- **TabArena-Lite** 是只用每个数据集第一个划分（repeat 0 / fold 0）的便宜版本，TabPFN-2.5 报告里用过。

适合：单表分类与回归、表格基础模型（TabPFN 一类）的评测、往非语言基础模型里注入显式知识前后的对比。
不适合：多表 / 时序 / 关系结构（那些用 RelBench）。

陷阱：
- `data.parquet` 是整表。拿测试行的特征时，要把目标列丢掉再喂给模型。
- 类别特征以 pandas `category` 类型存储，有的模型需要自己编码。
- 不同论文报的「TabArena 子集」不一样（TabPFNv2 子集、TabICL 子集、Lite），比较数字前先对齐子集。
- 排行榜在持续更新（living benchmark），引用时写明版本 `tabarena-v0.1`。
