# RelBench

| 项 | 值 |
| --- | --- |
| 论文 v1 | RelBench: A Benchmark for Deep Learning on Relational Databases |
| arXiv v1 | **2407.20060**（2024-07-29），NeurIPS 2024 Datasets & Benchmarks |
| 论文 v2 | RelBench v2: A Large-Scale Benchmark and Repository for Relational Data |
| arXiv v2 | **2602.12606**（2026-02-13），ICLR 2026 DATA-FM Workshop |
| 立场论文 | Relational Deep Learning，arXiv **2312.04615**，ICML 2024 |
| 代码 | https://github.com/stanford-star/relbench （旧 URL `snap-stanford/relbench` 301 跳到这里） |
| 数据 | https://huggingface.co/datasets/stanford-star/relbench-v1 · `…/relbench-v2-extra` |
| 网站 | https://star-project.stanford.edu/relbench |
| 访问 | 公开、无 gated、无需申请 |
| **许可** | 代码 **MIT**；HF 集合 **CC BY-SA 4.0**；**逐库另有上游条款** |
| 包版本 | `relbench` 当前 **3.0.2**（requires-python ≥3.10） |

## 许可（分层，别只看一个）

- **代码 / 工具：MIT.** 仓库根的 `LICENSE` 写着
  `The MIT License (MIT) / Copyright (c) 2023 RelBench Team`。
  注意 PyPI 的 `info.license` 字段是 `None`，GitHub API 的 license 键也是 null ——
  但徽章与 LICENSE 文件一致说 MIT，跨版本都是。
- **HF 数据集集合：`cc-by-sa-4.0`**（数据卡 YAML 里明确写了，**不是 MIT**）。
  **CC BY-SA 是 share-alike** —— 如果你再分发，这个条款会传染。
- **⚠️ 每个库各自沿用其上游来源的许可。** README 原话：
  *"CC BY-SA 4.0 for the collection. **Each database keeps the license of its source**;
  see `STATS/databases.parquet`."*
  **要精确条款必须去读那个表。**

## ⚠️ v3 的破坏性变更

**RelBench v3（2026-08）把加载器整个换掉了。** 按 `MIGRATION.md`，以下**全部移除**：

- `relbench.datasets.get_dataset` / `get_dataset_names` / `download_dataset`
- `relbench.tasks.get_task` / `get_task_names` / `register_dataset` / `register_task` / `download_task`
- `download=` 参数

现在 `load_task` / `get_task_names` 挂在 **dataset 对象**上：

```python
import relbench
dataset = relbench.load_dataset("rel-f1")        # 裸名，或 "org/repo[/subdir]"，或本地路径
db      = dataset.get_db()
task    = dataset.load_task("driver-position")
train   = task.get_table("train")                # train / val / test
metrics = task.evaluate(test_pred)
```

旧教程（`get_dataset("rel-f1")` 那套）跑不通。需要旧行为就钉 `relbench==2.1.2`
（但它的下载服务器已废弃）。

**`RELBENCH_CACHE_DIR` 已失效** —— 设了会被静默忽略。缓存在 HF 的标准位置
（`~/.cache/huggingface/hub`，用 `$HF_HOME` 或 `$HF_HUB_CACHE` 覆盖）。

**没有固定 revision**：除非显式传 `revision=`，否则用 `main` 的最新版 —— **数据会在你脚下变**。

## 获取

```bash
knosis download relbench                      # 取整个 relbench-v1
knosis download relbench --include 'rel-f1/*'    # 只取一个库
```

Knosis **不依赖 `relbench` 包**，直接读 HF 上的文件。若本地装了 relbench，
也可以用 `root=` 指向它的缓存：`load_dataset("relbench", db="rel-f1", root="~/.cache/huggingface/hub/…")`。

依赖：`pandas`、`huggingface_hub`、`pyyaml`、`pyarrow`、`numpy`、`duckdb`、
`scikit-learn`、`typing-extensions`、`tqdm`。
（Knosis 只用 `pyarrow` 读页脚，其余懒 import。）

## 体量

- v1：**7 个库 / 30 个任务**。库：`rel-amazon`、`rel-avito`、`rel-event`、
  `rel-f1`、`rel-hm`、`rel-stack`、`rel-trial`。
- v2 新增 4 个库（SALT、RateBeer、arXiv、MIMIC-IV）+ 36 个新任务
  （其中 23 个是 Autocomplete 类型）→ 共 **11 库 / 66 任务**。

逐库表数（已核实）：`rel-f1` 9 张、`rel-stack` 7 张、`rel-trial` 15 张、`rel-hm` 3 张。

**⚠️ MIMIC-IV 的访问条款未核实**，且公开的 `relbench-v2-extra` 文件树里
**没有看到 `rel-mimic` 目录** —— 此条目待确认，别按「公开可得」处理。

## 布局（v3）

```
<db>/
  manifest.yaml              # 表、主键、外键图、时间切分点 —— **唯一的权威来源**
  schema.svg
  db/<table>.parquet         # 一张表一个 parquet，**纯数据，不带 relbench 元数据**
  tasks/<task>/
    manifest.yaml            # 任务定义（含重新生成标签用的 DuckDB SQL）
    {train,val,test}.parquet
  README.md
```

repo 根还有 `regression_stds.json`、`STATS/databases.parquet`、`STATS/tasks.parquet`。

**关键：「db」是目录名，不是 SQLite 文件。** 而且**所有键与时间列都在 manifest 里**，
parquet 里没有 —— 只读 parquet 拿不到外键关系。

`rel-f1/manifest.yaml` 真实内容（片段）：

```yaml
name: rel-f1
manifest_version: 1
val_timestamp: '2005-01-01'
test_timestamp: '2010-01-01'
tables:
  races:
    pkey: raceId
    time_col: date
    fkeys:
      circuitId: circuits
  constructors:
    pkey: constructorId
    time_col: null      # 静态表
    fkeys: {}
```

## 任务名（v1，已核实）

`rel-f1` 3 个（`driver-dnf` / `driver-position` / `driver-top3`）、
`rel-stack` 5 个、`rel-amazon` 7 个、`rel-hm` 3 个、`rel-trial` 5 个、`rel-avito` 4 个、`rel-event` 3 个。

v2-only 的任务在 `relbench-v2-extra` 仓库里（裸名会按顺序在两个 repo 里找）。
**注意 v2 引入了带下划线的任务名**（`event_interest-interested`、
`beer_ratings-total_score`、`studies-has_dmc`、`searchinfo-isuserloggedon`）——
**下划线与连字符不做归一，别做字符串清洗。**

## 时间切分与标签泄漏（最重要的一节）

1. **⚠️ `rel-f1/driver-dnf` 有一个已确认的、被刻意保留的泄漏。**
   发布的任务 manifest SQL 里有这段注释：
   ```
   -- KNOWN ISSUE (…/issues/402): no upper bound `date <= t.timestamp`,
   -- so drivers whose only races are after t.timestamp leak in.
   -- Kept as-is for comparability.
   ```
   这是**真实的未来信息泄漏**，上游为了跟已发表数字可比**故意不修**。
   Knosis **不修它** —— 修了你的数字就跟榜单对不上。但你必须知道这件事。

2. **推荐类任务的 test 表已隐藏目标列。** v3 起 `task.get_table("test")`
   只保留时间与源实体列，不再有目标列表。照 v2 写法去读会静默拿到垃圾。

3. **标签窗口可能跨过切点。** `driver-dnf` 的目标窗口是
   `(t.timestamp, t.timestamp + INTERVAL '30 days']`，而实体过滤往回看 1 年。
   rel-f1 的 val(2005) 与 test(2010) 隔得远，但 **rel-hm 的 val→test 只隔 7 天**
   （2020-09-07 → 2020-09-14），而标签窗口是多天的 —— 这里最容易踩。

4. **`regenerate=True` 是现成的对账手段。** 它能从 manifest SQL 重算标签。
   上游 changelog 记录过**三次**已发布标签的重算（`rel-event/user-repeat`
   训练集 3842 → 2972 行；`rel-stack/post-votes` +117/+14；`rel-stack/user-post-comment` +1）。
   **已发布的标签曾经错过。**

5. **未排序表的 autocomplete 曾错位**（已修但值得知道）：`rel-amazon/review`、
   `rel-avito/SearchStream`、`rel-event/event_interest` 曾无主键且未按时间排序，
   导致标签「按行位置索引」，而全库与截断到 `test_timestamp` 的库行位置不同。
   现在 `AutoCompleteTask` 会拒绝无主键的未排序表。
   **行位置键 + 时间截断是致命的组合。**

6. **`get_db()` / `get_table()` 在 v3 里不再缓存** —— 循环里调用会反复读盘。

7. **DuckDB 版本敏感**：v3.0.1 修过 autocomplete 训练集的起点计算，
   说是「每个 duckdb 版本都包含第一批行」—— 说明标签生成依赖 DuckDB 版本。**钉住你的 duckdb。**

8. **环境变量 `RELBENCH_DUCKDB_MEMORY_LIMIT`** 是 opt-in 的；
   不设的话，跑飞的 task SQL 可能被 OS 直接 OOM kill 而不是抛可捕获的错误。

## 评测器

v3 **只剩三个**：`roc_auc`（二分类）、`map`（推荐）、NMAE（回归）。
**长尾的 f1 / mae / rmse / r2 / mrr / multilabel_* 全部移除** —— 要自己带。
多分类 / 多标签任务能加载，但**没有内置评测器**。
回归的 NMAE 需要 normalizer：用托管的 `regression_stds.json`，
或用 `relbench.train_std(task)` 重算。

任务类型：`forecast`（SQL 派生标签）/ `autocomplete`（预测已存在的列）/
`recommendation`（v3 从 `LINK_PREDICTION` 改名）/ `external`（TGB、4DBInfer，
只有数据，`evaluate()` 不带指标会抛）。
