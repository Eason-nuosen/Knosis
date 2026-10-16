# RelBench —— 关系数据库上的预测任务（多表 + 时间切分）

## 来源

Stanford STAR / Kumo.AI。**RelBench**（NeurIPS 2024 Datasets & Benchmarks），
arXiv **2407.20060**；**RelBench v2**（ICLR 2026 DATA-FM Workshop），arXiv **2602.12606**。
网站 https://star-project.stanford.edu/relbench ；
代码 https://github.com/stanford-star/relbench ；
数据 https://huggingface.co/datasets/stanford-star/relbench-v1 （v2 新增库在 `relbench-v2-extra`）。
公开、**无 gated**、无需申请。

获取：`knosis download relbench`

**许可分层，别只看一个。**
- 代码 / 工具：**MIT**（仓库根有 LICENSE）。
- HF 数据集集合：**CC BY-SA 4.0**（注意 share-alike）。
- **每个库各自沿用其上游来源的许可** —— 要精确条款请读仓库里的 `STATS/databases.parquet`。

体量：v1 是 7 个库 / 30 个任务；v2 扩到 11 个库 / 66 个任务。
表数差异大：rel-f1 有 9 张表，rel-trial 有 15 张，rel-hm 只有 3 张。

**如果本地装了 `relbench` 包**：v3 会从 HF Hub 自动取数并缓存到
`~/.cache/huggingface/hub`（`$HF_HOME` 可覆盖）。**`RELBENCH_CACHE_DIR` 已失效**，
设了也不会被读。Knosis 不依赖该包，直接读本地目录。

## 说明

RelBench 是关系数据库上的预测学习基准：每个库是一组多表数据 + 若干实体级预测任务，
配一套统一的（时间）切分与评测。

**数据布局**（v3，自描述文件夹）：

```
<db>/
  manifest.yaml             # 表、主键、外键图、时间切分点 —— 唯一的权威来源
  db/<table>.parquet        # 一张表一个 parquet，纯数据，不带任何 relbench 元数据
  tasks/<task>/
    manifest.yaml           # 任务定义（含重新生成标签用的 DuckDB SQL）
    {train,val,test}.parquet
```

**关键：所有键与时间列都在 `manifest.yaml` 里，不在 parquet 的元数据里。**
所以只读 parquet 是拿不到外键关系的，必须解析 manifest。

切分是**按时间**的，不是随机的：`val_timestamp` / `test_timestamp` 给出两个切点。
`get_db()` 的默认行为是把 `test_timestamp` 之后的行藏起来 —— 这是对的，
**用未截断的全库去评测就是泄漏**。

适合：多表 join、实体级分类 / 回归 / 推荐、时间切分下的泛化、关系结构的建模。
不适合：需要跨库迁移的设定；也不适合把不同库的绝对指标直接横比（任务难度差很远）。

陷阱（这几条都是上游明确记录过的，不是猜测）：
- **`rel-f1/driver-dnf` 有一个已知且被刻意保留的标签泄漏**：它的 SQL 缺少
  `date <= t.timestamp` 上界，只在切点之后才有比赛的车手会漏进来。上游为了跟已发表
  数字可比而**故意不修**。Knosis 不修它 —— 修了你的数字就跟榜单对不上。要知道这件事。
- **推荐类任务的 test 表已经被隐藏目标列**（v3 起只留时间与源实体列）。
  照 v2 的写法去 test 表里读目标列表，会静默拿到垃圾。
- 时间标签窗口可能跨过切点。rel-f1 的 val(2005) 与 test(2010) 隔得远，
  但 **rel-hm 的 val→test 只隔 7 天**，而标签窗口是多天的 —— 这里最容易踩。
- 上游**改过已发布的标签**（rel-event/user-repeat 的训练集从 3842 行变 2972 行等）。
  用 `regenerate=True` 可以从 SQL 重算标签来对账，这是现成的自检手段。
- `get_db()` / `get_table()` 在 v3 里**不再缓存**，循环里调用会反复读盘。
- 任务名里下划线不归一：v2 有 `event_interest-interested`、`beer_ratings-total_score`
  这种带下划线的名字，别做字符串清洗。
- v3 的评测器只剩三个：`roc_auc`（二分类）、`map`（推荐）、NMAE（回归）。
  f1 / mae / rmse / r2 / mrr 那一大批已被移除，要用得自己带。
- 裸库名解析不到时会**回退到 relbench-v1**，所以拼错库名得到的是个费解的报错，而不是"未知库"。

任务按类型分 `forecast`（标签由 SQL 算出来，可复现）/ `autocomplete`（预测某个已存在的列）/
`recommendation` / `external`（TGB、4DBInfer，只有数据、没有内置评测器）。
