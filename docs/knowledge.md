# 知识层格式

知识层 = **κ 单元** + 可选的**本体子层** + **反馈子层**。工作区里：

```
knowledge/
├── units.jsonl                       每行一个 κ
├── ontology/                         可选，Apache Ossie 0.2 三文件 + EOB 扩展
│   ├── <name>.semantic_model.yaml    core：表、列、主键、join、度量
│   ├── <name>.ontology.yaml          概念、概念间关系、单位与约束（不提表和列）
│   └── <name>.mapping.yaml           列 → 概念 / 关系
└── feedback/<id>.json                dev 题上的反馈记录
```

每次 `ws check` 通过，extract / refine 会把整个知识层快照到 `stages/2_extract/knowledge/`、
`stages/3_refine/round_<n>/knowledge/`，这就是 K_0、K_1 …；`ws fork --knowledge K_n` 拿到的也是这一整份
（fork 出来的对照组关闭反馈，只比较给定的知识）。

## κ 单元

```json
{"id": "income-pattern", "content": "训练数据中的条件规律", "form": "rule",
 "condition": "成立条件与例外", "provenance": "data/train.parquet#col/MedianIncome",
 "status": "verified", "derived_from": [], "about": ["houses.MedianIncome"],
 "meta": {"support_count": 120, "counterexamples": 8}}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 工作区内唯一 |
| `content` | 是 | 知识内容（自然语言 / 公式 / 三元组文本） |
| `form` | 是 | `finding` / `fact` / `rule` / `formula` / `schema` / `tool` |
| `provenance` | 是 | 来源，见下 |
| `status` | 是 | `observed` / `inferred` / `verified` / `retracted` / `stale` |
| `condition` | 否 | 适用条件与已知例外 |
| `derived_from` | 否 | 父单元 id |
| `support` | 否 | 独立支持数 |
| `about` | 否 | 引用的本体元素名（见下），有本体时必须能解析 |
| `meta` | 否 | 任意附加信息 |

来源写法：数据 `data/<文件>#node/<id>`、`#edge/<src>|<label>|<dst>`、`#row/<row_id>`、`#col/<列名>`；
工具 `tool:<name>@<version>(<k=v,...>)`；反馈 `feedback:<记录 id>#item/<题目 id>`；纯派生 `derived`（`derived_from` 必须非空）；多来源用 ` ; ` 连接。

结构检查（`check_units`）：必填字段与取值、重复 id、`data/` 来源文件存在、
`feedback:` 来源指向存在的记录、**I1** 派生引用可解析（含历史版本）、**I5** 父单元撤回 / 失效后后代必须是 `retracted` 或 `stale`。
不判断内容对错；I2（独立来源计数）、I3（类型兼容）、I4（条件不丢）尚未实现。

## 本体子层

与 ontology-bench 的 EOB v0.2 格式一致：底座是 Apache Ossie `0.2.0.dev0`，
benchmark 自定义信息一律写在 `custom_extensions`（`vendor_name: EOB`，`data` 是 JSON 字符串），不改官方 schema。
字段写法见 ontology-bench 的 `docs/ontology-format-ossie.md`；`tests/fixtures/sales_bi/` 是一份完整样例。

**可引用的名字**（`ontology.refs`）：dataset 名、`dataset.field`、core relationship 名、metric 名、
概念名、`概念.关系名`。κ 的 `about` 用这些名字把一条知识挂到本体元素上。

**检查**（`check_ontology`，官方 `validate.py` 不查的部分）：core relationship 的表和列存在、两侧列数相等；
概念的 `extends` 与关系角色指向存在的概念或内置类型；mapping 的 concept 存在、`expression` 是存在的 `dataset.field`、
EOB `annotations` 的 target 存在。官方 JSON Schema 校验请用 Ossie 仓库的 `validate.py`。

**κ 视图**（`ontology_units`）：每个 dataset、core relationship、metric、概念、概念关系展开成一条 `form=schema` 的 κ，
`provenance` 指向本体文件内的位置，`status` 由 EOB `provenance.method` 决定：
`human` → verified，`converted` → observed，`llm` / `tool` → inferred。

**构造**：

| 函数 | 作用 |
| --- | --- |
| `from_tables(name, tables, primary_keys, relationships)` | 由 DataFrame 或 {列: 类型} 构造 core 层 |
| `from_bibench(ds)` | BI-Bench 用例的 Power BI 元数据（`_tables/_columns/_relationships`）→ core 层；去掉自动日期表与 RowNumber 列，计算列保留 DAX，关系方向转成 Ossie 的 many → one，基数 / active / 筛选方向写进 EOB |
| `from_relbench(ds)` | RelBench manifest 的 pkey / fkeys / time_col → core 层 |
| 工具 `joins --ontology DIR` | 从数据里发现的候选主键与 join 写成 core 层草稿（`method: tool`） |

注意：BI-Bench 的 `_relationships` 与 RelBench 的外键在「join 发现 / 本体构造」类评测里是 GT，不应给被测 agent。

## 反馈子层

agent 自己就是 Codex / Claude Code：Knosis 不记录它的轨迹，只给它**结果**，由它把结果变成知识。

- 每个工作区有一个 dev 划分（`tasks/dev.jsonl`，无答案，与测试题不重叠）。agent 按 decide 的交付格式回答一部分或全部 dev 题，
  `knosis feedback submit <文件>` 返回逐题结果，同时写一条 `knowledge/feedback/<id>.json`。
- 模式（`ws init --feedback`）：`answer` 给对错、分数和正确答案；`score` 只给对错与分数；`none` 关闭。`--budget` 限制提交次数。
- 反馈只接受 dev id；GT 从原始数据目录读，打分器与 `knosis eval` 是同一个函数（`decision` 层的 `score(..., ids)`）。
- **自动 RSI**：驱动模式下 `knosis ws run <ws> --stage refine --rounds N`，每轮结束时运行器把本轮的
  `stages/3_refine/round_<n>/dev_<交付文件>` 自动提交一次，结果写进下一轮的提示。
- 提示里只说明数据可能含噪声；哪些是噪声、怎么处理、反馈说明了什么，都由 agent 判断并写成 κ
  （例如「某条边是噪声」是一条 finding，provenance 指向反馈记录与数据位置）。
