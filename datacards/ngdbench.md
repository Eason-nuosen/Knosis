# NGDBench

| 项 | 值 |
| --- | --- |
| 论文 | NGDBench: Towards Neural Graph Data Management |
| arXiv | **2603.05529**（v1 2026-02-27；v2 2026-05-29） |
| 作者 | Yufei Li, Yisen Gao, Jiaxuan Xiong, Jiaxin Bai, Shijie Zhong, Haoyu Huang, Zhongwei Xie, Hong Ting Tsang, Yangqiu Song（HKUST-KnowComp） |
| 代码 | https://github.com/HKUST-KnowComp/NGDBench |
| 数据 | https://huggingface.co/datasets/FeifeiCS/NGDBench |
| 访问 | 公开、无 gated、无需申请 |
| **许可** | **未声明**（见下） |
| 上游版本 | `NGDBenchV1` 与 `NGDBenchV1_1`；**默认用 V1.1** |
| HF 最后更新 | 2026-08-27 |

## 许可

**没有找到任何许可声明。** 已核实：

- HF 数据卡的 YAML front-matter 只有 `tags: [NeuralDatabase]` 与
  `size_categories: [100M<n<1B]`，**没有 `license:` 字段**；
  HF API 的 `cardData` 里也没有 license 键。
- GitHub 仓库根目录没有 `LICENSE` / `LICENSE.md` / `LICENSE.txt` / `COPYING`
  —— 全部 404；About 面板也没有许可徽章。

**按「保留所有权利」对待 —— 不要打包进任何再分发的产物。**
上游数据本身另有条款（NGD-BI 源自 LDBC SNB BI，NGD-Prime 源自 PrimeKG）。

## 获取

```bash
knosis download ngdbench --include 'NGDBenchV1_1/NGDFin/*'   # 只取一个域
knosis download ngdbench --include 'NGDBenchV1_1/*'          # 取整个 V1.1
```

**别整个 repo 拉。** HF 的 size category 是 `100M<n<1B`，NGD-BI 单域就几 GB。
`--scenario` 用小写匹配（磁盘目录名大小写不一致）。

**不要用 `load_dataset("FeifeiCS/NGDBench")`。** 该 repo 的数据卡里没有
`config_name` / `data_files`，HF 的 `datasets` 自动加载器会失败或做错事。
它就是个纯文件转储。

**⚠️ 用 `huggingface-cli` 或 `hf_hub_download`，不要用裸 `curl`。**
repo 里有 LFS 配置，`curl` 大 `.gpickle` 可能只返回 LFS 指针文本而不是数据。
`knosis download` 走 `huggingface_hub.snapshot_download`，会拿到真数据。

## 体量

| 类别 | NGD-BI | NGD-Fin | NGD-Prime | NGD-MCP | NGD-Econ |
| --- | --- | --- | --- | --- | --- |
| 节点（真图） | 2,997,352 | 10,865 | 129,312 | 181,689 | 33,164 |
| 边（真图） | 17,196,776 | 57,818 | 8,100,498 | 351,263 | 63,757 |
| 边（加噪） | 17,971,365 | 60,476 | 8,465,124 | 351,263 | 63,757 |

查询数：非聚合分析 **58,321**、聚合分析 **25,703**、管理类 **6,110**。

**注意节点数的不对称**：加噪图与真图**节点数完全相同**，只有边数变多（BI / Fin / Prime）。
噪声主要作用在边级（以及属性级），不是插入新节点。

## 布局

```
NGDBenchV1_1/
├── NGDBi/                       # ⚠️ V1.1 里是小写 i（V1 是 NGDBI）
│   ├── graph/{ldbc_snb_bi.gpickle, ldbc_snb_bi_noise_20260128_015455.gpickle}
│   ├── noise_info/*_{noisy_edges,noisy_nodes,records}.json
│   └── query/{complex_query_agg, complex_query_noagg,
│              management_query_agg, management_query_noagg}.json
├── NGDFin/    graph/…  noise_info/…  query/（同上四个）
├── NGDPrime/  graph/…  noise_info/…  query/{management_query_agg, management_query_noagg,
│                                             query_results_agg, query_results_noagg}
├── NGDMcp/    graph/mcp_tragectory_40pct_without_concept.graphml   # ⚠️ graphml，不是 gpickle
│              kg_extraction/qwen2.5-14b-instruct_…json
│              query/complex_query_{agg,noagg}_judged_finalkeep[_with_nlp].json
└── NGDEcon/   graph/multiEcon.gpickle
               kg_extraction/qwen2.5-14b-instruct_multi_financial.json
               query/{complex_query_agg, complex_query_noagg}.json
```

格式：`.gpickle`（pickled NetworkX，主导）、`.graphml`（仅 MCP）、`.json`。
**没有 parquet / CSV / SQLite。**

**⚠️ `.gpickle` 反序列化即执行任意代码**，而且各域是在特定 NetworkX / Python
版本下 pickle 的，跨版本加载常失败。`ds.read("clean")` 会直接 unpickle，只对信任的文件这么做。

## 记录结构（已核实，NGD-BI V1.1 非聚合题）

```json
{
  "template_type": "pipelined",
  "query": "MATCH (a:Organisation {id: 367})-[:Organisation_isLocatedIn_Place]->(b:Place) …",
  "clean_answer": [{"b.url": "…", "c.id": 1455}],
  "noise_answer": [{"b.url": "…", "c.id": 1455}],
  "same_as_cleangraph": true,
  "nlp": "Find an organisation located in a place with id 367, …",
  "template_id": "pipelined_T001"
}
```

**`clean_answer` 与 `noise_answer` 都是预先算好并随包发布的** ——
评分不需要跑 Neo4j，直接拿模型输出跟两者对比即可。
`same_as_cleangraph` 是预先算好的布尔，告诉你噪声是否改变了答案（现成的难度过滤器）。
答案是**以 Cypher 返回别名为键的 list-of-dict**，比较要按集合语义、忽略顺序。

## 已知问题

- **域目录名与论文名不一致**：论文写 `NGD-BI`，磁盘上是 `NGDBi`（V1.1）/ `NGDBI`（V1）。
  MCP 是 `NGDMcp`。加载器必须处理这个映射，Knosis 用小写匹配。
- **加噪文件名里的时间戳不稳定**：`20260126`、`20260128_015455`、`20260127_113349`
  各不相同 —— **必须 glob `*_noise_*.gpickle`，不要硬编码**。
- **答案字段名随域而变**：结构化域用 `clean_answer` / `noise_answer`，
  非结构化域用 `gnd` / `answer`；而且 **MCP 的 `gnd` 是一个字符串**
  （如 `"varied keyword search"`），不是结果集。
- **`gnd` 不存在于 V1.1 的结构化文件里**，尽管 HF 卡片让你去用它。
- **V1 与 V1.1 的布局与查询文件名差异很大**（V1 有 `judge_query*.json` 这个
  Boolean 桶、`management_mix.json`、`complex_query_agg_pair.json` 等）。
  **必须显式指定版本目录。**
- 发布里混着开发残留：`NGDFin/query/__pycache__/query.cpython-313.pyc`、
  拼错的 `mcp_tragectory`、大小写不一致的 `Primekg`。
- 上游 README 说「每个**结构化**数据集都提供 clean 与 perturbed 配对」——
  这句话是准确的：**MCP 与 Econ 没有配对**，只有一个图。
