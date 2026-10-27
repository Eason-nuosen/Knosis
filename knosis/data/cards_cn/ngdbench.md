# NGDBench —— 大规模属性图上的问答（clean / perturbed 配对）

## 来源

HKUST-KnowComp, **NGDBench: Towards Neural Graph Data Management**, arXiv **2603.05529**（2026）。
代码 https://github.com/HKUST-KnowComp/NGDBench ；
数据 https://huggingface.co/datasets/FeifeiCS/NGDBench —— 公开、**无 gated**、无需申请。

获取：`knosis download ngdbench`
（用 `--include 'NGDBenchV1_1/NGDFin/*'` 只取一个域，别整个 repo 拉。）

**许可：未声明。** HuggingFace 卡片没有 `license` 字段，GitHub 仓库里没有 LICENSE / COPYING
文件。按「保留所有权利」对待 —— 不要打包进任何再分发的产物，引用请标注上游。
上游数据本身另有条款（NGD-BI 源自 LDBC SNB BI，NGD-Prime 源自 PrimeKG）。

体量：约 336 万节点 / 2640 万边 / 90134 条查询。各域差异极大 ——
NGD-BI 单域 300 万节点 / 1720 万边，NGD-Fin 只有 1 万节点。磁盘先预留。
HF 仓库有两个版本目录 `NGDBenchV1/` 与 `NGDBenchV1_1/`，**默认用 V1.1**。

## 说明

NGDBench 是大规模属性图上的问答基准，覆盖 5 个域：

| 域（论文名） | 磁盘目录名 | 内容 |
| --- | --- | --- |
| NGD-BI | `NGDBi`（V1 里是 `NGDBI`） | 社会 / LDBC SNB BI |
| NGD-Fin | `NGDFin` | 金融 |
| NGD-Prime | `NGDPrime` | 生物医学 / PrimeKG |
| NGD-MCP | `NGDMcp` | 工具调用轨迹 |
| NGD-Econ | `NGDEcon` | 企业报告 |

**加载时用小写匹配域名的写法（`scenario="NGD-Fin"`），磁盘上的大小写不一致是上游的坑。**

查询分四类，V1.1 下每类一个文件：非聚合分析题、聚合分析题、管理类非聚合、管理类聚合。
每题都带 **NL 问题（字段 `nlp`）与对应 Cypher（字段 `query`）**。管理类题是**多步序列**
（字段 `steps`），每步有 `operate_query` 改状态、`valid_query` 断言结果 —— 必须按序在一个
可变图上执行，不能当成单条查询。

**关键结构：结构化域有 clean 与 perturbed 两版配对图。** clean 是 latent 真图，perturbed
是加噪后的可观测图，两者放在**同一个 `graph/` 目录里**，只靠文件名后缀区分：clean 是无后缀的
那个，perturbed 带 `_noise_<时间戳>`。**那个时间戳跨域、跨版本都不稳定，必须 glob
`*_noise_*.gpickle`，不要硬编码文件名。** NGD-MCP 与 NGD-Econ **没有配对**，只有一个图。

**答案预先算好了，不需要跑 Neo4j。** 每条查询记录同时带 `clean_answer` 与 `noise_answer`，
还有一个预先算好的布尔 `same_as_cleangraph` 告诉你噪声是否改变了答案 —— 这是个现成的
难度/鲁棒性过滤器，直接用。**两版之间的分差是「噪声敏感度」指标，不是误差** ——
不要当 bug 去修，也不要直接用 clean 图评测（那就绕开了本基准的核心设定）。

⚠️ 图是 `.gpickle`（pickled NetworkX）。**反序列化等于执行任意代码**，而仓库里没有任何
可供校验的哈希。`ds.read("clean")` / `ds.read("perturbed")` 会直接 unpickle，只对你信任的文件这么做。

适合：多跳查询、聚合计数、Boolean 校验、图上的管理类操作、噪声鲁棒性。
不适合：需要外部世界知识才能回答的问题（图中没有的信息，答不出来是对的）。

陷阱：
- **perturbed 图里带着加噪痕迹，等于泄漏答案**：边属性 `is_noise` / `noise_similarity` / `relation`，
  节点属性 `noise_similarity` / `original_name`（NGD-Fin 已核实）。clean 图的边只有 `label`。
  做去噪或鲁棒性实验前，先把 perturbed 图里 clean 图没有的属性键全部删掉。
- 域目录名与论文名不一致；V1 与 V1.1 的布局、查询文件名都不同。**版本目录要显式指定。**
- 答案字段名随域而变：结构化域用 `clean_answer` / `noise_answer`，非结构化域用 `gnd` / `answer`；
  而且 **MCP 的 `gnd` 是一个字符串**（比如 "varied keyword search"），不是结果集，语义完全不同。
- 答案是**以 Cypher 返回别名为键的 list-of-dict**，比较要按集合语义、忽略顺序，不能直接比列表。
- 聚合题 GT 是集合或数值，注意去重与排序规则，以官方口径为准。
- MCP / Econ 两域的关系短语是开放词汇，不要假设有固定关系词表；BI / Fin / Prime 三域则有明确 schema。
- 上游发布里混着开发残留：`__pycache__/*.pyc`、`mcp_tragectory`（拼错）、`Primekg`（大小写）。

建议从 **NGD-Fin 或 NGD-Prime** 入手（schema 明确，规模相对可控）；NGD-BI 是最大的那个。
术语：图查询语境下 "hop" 指关系跳数，"aggregation" 指 count / sum / avg 类算子。
