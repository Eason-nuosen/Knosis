# BI-Bench —— 真实 BI 项目上的端到端业务问答

## 来源

Hu, He, Zhou, Tok, Kang, Chaudhuri, **BI-Agent and BI-Bench: Towards Automating End-to-End Business Intelligence**，
arXiv **2609.20886**（2026）。仓库 https://github.com/Hu-Chuxuan/bi-agent （数据在 `bi-bench/`）。

获取：`knosis download bibench`（`git clone` 后 `git lfs pull`；表与 GT 都是 LFS 文件，展开后约 4 GB，
需要 git-lfs：`conda install -c conda-forge git-lfs`）。

**许可：未声明。** 仓库里没有 LICENSE 文件，README 也没有许可说明。按「保留所有权利」对待，不要再分发。

## 说明

BI-Bench 考的是：**给一个真实 BI 项目的一堆原始表，回答仪表盘上的一道业务问题。**
100 个用例，每个用例来自一个真实的 Power BI 项目：多张 CSV 表（每例 2–52 张，中位数 8 张，共 1056 张）
加一道从用户仪表盘里抽出来的自然语言问题（如「每个订单年份的单价总和与数量总和是多少？」）。

难点在于端到端：要自己判断该用哪几张表、怎么 join、要不要先做 unpivot 之类的变换，再做聚合。

**每个用例一个 scenario**：`load_dataset("bibench", "<用例id>")`，用例 id 是 `queries.json` 的键，
部分 id 带连字符（如 `111676720-1`）。不给 scenario 时只加载 100 道题目，不登记表文件。

**数据形态：**

- `ds.files` —— 该用例的各张表（键是文件名去掉 `.csv`），以及原 BI 项目的模型元数据：
  `_tables` / `_columns`（表与列的定义）、`_relationships`（项目里定义的表间关系）、
  `_joins`（BI-Agent 工具挖出的候选 join，带置信度 `weight`）。元数据里的表与列用数字 ID 互相引用。
- `ds.tasks` —— 每个用例一题，`input` 是业务问题，`answer` 是 GT 文件路径的列表。

**评测口径（上游）：** 预测结果（一张表或一个标量）与**任一** GT 表匹配即算对。
多个 GT 通常是同一答案的不同格式（如 `8.95%` 与 `8.95`）。
GT 是 1×1 时，只要预测里出现这个值就算对；否则形状必须一致，单元格按多重集合匹配
（数值 `rtol=1e-2, atol=0.5`，不计行列顺序）。

适合：多表理解与 join 推断、表结构知识（哪些表、哪些键、哪些变换）、端到端的数据分析 agent。
不适合：需要外部知识才能回答的问题（答案都在表里）。

陷阱：
- **`task.meta["oracle"]` 是解题提示**（该用哪几张表、需要做哪些变换），来自上游的 `query_metadata.json`，
  评测 agent 时不要给它看。上游 BI-Agent 的工具套件（检索 / 变换）会用到这些信息。
- 上游 `tools/data_management_tools/transformation/` 里是预先变换好的表，同样属于提示。
- 表名可能有拼写错误（如 `Coutnries.csv`），这是原始项目的样子，不要改。
- 表按字符串读更稳（上游用 `dtype=str`），很多列混着数字与文本。
