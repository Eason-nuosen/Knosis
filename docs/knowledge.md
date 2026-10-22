# 知识层格式

知识层 = **κ 单元** + **证据账本** + 可选的**本体**（本体元素也是 κ）+ **反馈记录**。工作区里（独立知识库同布局）：

```
knowledge/
├── units.jsonl                       每行一个 κ
├── evidence.jsonl                    每行一条证据
├── checks/<id>.py                    可选，单元的可执行检查
├── skills/<名字>/SKILL.md            可选，如何运用知识解某类任务（解题集）
├── ontology/                         可选，Apache Ossie 0.2 三文件 + EOB 扩展；多份本体各占一个子目录
│   ├── <name>.semantic_model.yaml    core：表、列、主键、join、度量
│   ├── <name>.ontology.yaml          概念、概念间关系、单位与约束（不提表和列）
│   └── <name>.mapping.yaml           列 → 概念 / 关系
└── feedback/<id>.json                dev 题上的反馈记录
```

范围与定位见 [scope.md](scope.md)。

每次 `ws check` 通过，extract / refine 会把整个知识层快照到 `stages/2_extract/knowledge/`、
`stages/3_refine/round_<n>/knowledge/`，这就是 K_0、K_1 …；从知识库继承的初始知识在 `stages/0_inherit/knowledge/`（K_inherit）；`ws fork --knowledge K_n` 拿到的也是这一整份
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
| `form` | 是 | 表达形式：`finding` / `fact` / `rule` / `formula` / `schema` / `tool` / `method` |
| `scope` | 否 | 粒度：`instance` / `relation` / `dataset` / `method` / `utility`；不写时由 `scope_of` 按 form 与来源推断 |
| `provenance` | 是 | 来源，见下 |
| `status` | 是 | `observed` / `inferred` / `verified` / `contested`（有反驳、未定论）/ `retracted` / `stale` |
| `condition` | 否 | 适用条件与已知例外 |
| `derived_from` | 否 | 父单元 id |
| `support` | 否 | 独立支持数 |
| `about` | 否 | 锚定的对象：本体元素名（有本体时必须能解析）或数据位置 `data/...#...`；`knosis knowledge index` 按对象反查 |
| `check` | 否 | 可执行检查，见「证据」 |
| `meta` | 否 | 任意附加信息 |

来源写法：数据 `data/<文件>#node/<id>`、`#edge/<src>|<label>|<dst>`、`#row/<row_id>`、`#col/<列名>`；
工具 `tool:<name>@<version>(<k=v,...>)`；反馈 `feedback:<记录 id>#item/<题目 id>`；纯派生 `derived`（`derived_from` 必须非空）；多来源用 ` ; ` 连接。

结构检查（`check_units`）：必填字段与取值、重复 id、`data/` 来源文件存在、
`feedback:` 来源指向存在的记录、**I1** 派生引用可解析（含历史版本）、**I5** 父单元撤回 / 失效后后代必须是 `retracted` 或 `stale`。
不判断内容对错；I2（独立来源计数）、I3（类型兼容）、I4（条件不丢）尚未实现。

## 证据

`evidence.jsonl` 每行一次验证：

```json
{"id": "e-0007", "unit": "smoker-rule", "verdict": "support", "method": "check", "source": "check:smoker-rule",
 "note": "rows=[[1]]", "inputs": {"data/train.parquet": "<大小:修改时间>"}, "created": "..."}
```

| 字段 | 取值 |
| --- | --- |
| `verdict` | `support` / `refute` / `undetermined`（条件或测量无法确认）/ `not_applicable`（前提不成立，不算支持也不算反例） |
| `method` | `check`（Knosis 重跑可执行检查）/ `tool` / `data` / `feedback` / `derivation` / `human` |
| `inputs` | 依赖的数据文件指纹；文件变了证据即过期，不再计入 |

可执行检查写在 κ 的 `check`：`{"kind": "sql", "query": ..., "expect": [[...]]}` 在 `data/` 的表上执行
（不给 expect 时第一行全为真即支持），或 `{"kind": "python", "path": "knowledge/checks/<id>.py"}`（退出码 0 支持、1 反驳、其他无法判定）。
`knosis knowledge verify` 重跑并记证据；其他验证用 `knosis knowledge evidence add` / `import`（工具写出的 `evidence.jsonl`）。

**状态与证据一致**（`check_units(..., evidence=...)`）：`verified` 至少一条未过期的支持；最近一条决定性证据是反驳时须为
`contested` / `retracted` / `stale`；**I2** `support: n` 不超过支持证据的独立来源数（按 `#` 之前去重）。
状态仍由 agent 写，Knosis 只检查它与证据是否矛盾。

**证据链**：`knosis knowledge trace <id>` 按派生关系列出每个单元与它的证据，即这条知识的发现途径。
**选取**：`knosis knowledge select [--about ...] [--form ...] [--text ...]` 按任务筛选（含本体元素）并附证据计数。

**效用**：dev 提交旁附 `<文件名>_used_units.jsonl`（每行 `{id, used_units}`）时，`feedback submit` 按题型统计每条知识 / skill
「用到时 / 没用到时」的 dev 正确率，写成 `scope=utility` 的候选 κ（id `utility/<知识>/<题型>`）与 feedback 证据。
utility 只能由 feedback / ablation 证据支持为 verified。测试题上的同类统计只写进评测报告（`eval.json` 的 `utility`），不写回知识层。

## skill（解题集）

`skills/<名字>/SKILL.md`，Codex / Claude Code 的 skill 格式，头部 YAML：

| 字段 | 说明 |
| --- | --- |
| `name` | 与目录名相同 |
| `description` | 一句话 |
| `when` | 适用的题型与条件 |
| `uses` | 引用的知识 id（κ 或本体单元） |
| `derived_from` | 总结自哪些反馈记录（可选） |
| `status` | `active` / `stale` / `retracted` |

检查：`uses` 能解析；所用知识被撤回或失效后 skill 须为 stale / retracted；`derived_from` 指向存在的反馈记录。
效果记为证据（unit 为 `skill:<名字>`）；决策时在 `used_units` 里引用 `skill:<名字>`。skill 不按 agent 分开记录。

## 知识体系大纲

可选的 `outline.yaml` 把 κ 与 skill 组织成层级（场景 → 数据间关系 → 数据本身），只做导航、不新增断言。
`knosis knowledge outline` 渲染，`knosis knowledge organize` 让 agent 整理；格式与检查规则见 [interfaces.md](interfaces.md)。

## 独立知识库

`knosis kb init <dir>` 建库（git 仓库，布局同上）。`knosis ws init ... --kb <dir> [--kb-scope method,skill]` 继承（可只继承某些粒度；
本体随 relation / dataset、skill 随 `skill` 一并继承）；
同一数据集上，知识库反馈记录里出现过的题目不进新工作区的测试集。`knosis kb merge <ws> --kb <dir>` 写回：
κ 按 id 合并、证据追加、反馈记录改名为 `<工作区>.<id>` 并改写引用，写回后整体检查，不通过就拒绝。
`knosis kb import-ontology <标注目录> --kb <dir> [--strip-gt]` 导入已有本体（如 ontology-bench 的标注），
`--strip-gt` 去掉来自 benchmark GT 的部分。

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
