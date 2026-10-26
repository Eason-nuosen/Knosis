# 知识层格式

知识层（v0.5）分两大块：**kb/** 放知识本身（结论，永久保存、可继承、可被选取），**evidence/** 放来源与验证的全过程。
工作区与独立知识库同布局：

```
kb/
├── knowledge/
│   ├── units.jsonl               每行一个 κ：对象知识 + 元知识
│   └── ontology/                 可选，结构化知识：OSI 标准（Apache Ossie 0.2）三层 + EOB 扩展；多份本体各占一个子目录
│       ├── <name>.semantic_model.yaml    语义模型：表、列、主键、join、度量
│       ├── <name>.ontology.yaml          概念、概念间关系、单位与约束（不提表和列）
│       └── <name>.mapping.yaml           列 → 概念 / 关系
├── skills/<名字>/SKILL.md        可选，使用流程：如何运用知识解某类任务
└── outline.yaml                  可选，知识体系大纲
evidence/
├── ledger.jsonl                  证据账本，每行一条证据
├── consolidate.jsonl             内化操作记录（去重、矛盾处理、构建知识体系）
├── checks/<id>.py                可选，单元的可执行检查
├── feedback/<id>.json            dev 题上的反馈记录
└── traces/                       来源轨迹（知识库收集来的会话、写回时带上的轨迹）
```

v0.4 的布局（工作区的 `knowledge/`、知识库根目录下的 `units.jsonl`）用 `knosis migrate <目录>` 转换。

范围与定位见 [scope.md](scope.md)。

每次 `ws check` 通过，extract / refine 会把整个知识层（`kb/` 与 `evidence/`）快照到 `stages/2_extract/`、
`stages/3_refine/round_<n>/`，这就是 K_0、K_1 …；从知识库继承的初始知识在 `stages/0_inherit/`（K_inherit）；`ws fork --knowledge K_n` 拿到的也是这一整份
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
| `form` | 是 | 表达形式：`finding` / `fact` / `rule` / `formula` / `schema` / `tool` / `procedure`（步骤型表达） |
| `scope` | 否 | 粒度。对象知识：`instance` / `relation` / `dataset`；元知识：`method`（怎么得到知识）/ `usage`（怎么用好知识）；不写时由 `scope_of` 按 form 与来源推断 |
| `provenance` | 是 | 来源，见下 |
| `status` | 是 | `observed` / `inferred` / `verified` / `contested`（有反驳、未定论，默认不被选取）/ `retracted` / `stale` / `merged`（去重时并入别的单元） |
| `condition` | 否 | 适用条件与已知例外 |
| `derived_from` | 否 | 父单元 id |
| `support` | 否 | 独立支持数 |
| `about` | 否 | 锚定的对象：本体元素名（有本体时必须能解析）或数据位置 `data/...#...`；`knosis knowledge index` 按对象反查 |
| `check` | 否 | 可执行检查，见「证据」 |
| `merged_into` | 否 | 去重：本单元并入的主单元（status 须为 merged）；引用本单元的派生、skill、大纲按别名解析 |
| `superseded_by` | 否 | 版本替换：环境变化后由哪条新单元取代（status 须为 stale / retracted） |
| `conflicts_with` | 否 | 已识别、尚未化解的矛盾；双方都活跃时至少一方须为 contested |
| `meta` | 否 | 任意附加信息 |

来源写法：数据 `data/<文件>#node/<id>`、`#edge/<src>|<label>|<dst>`、`#row/<row_id>`、`#col/<列名>`；
工具 `tool:<name>@<version>(<k=v,...>)`；反馈 `feedback:<记录 id>#item/<题目 id>`；纯派生 `derived`（`derived_from` 必须非空）；多来源用 ` ; ` 连接。

结构检查（`check_units`）：必填字段与取值、重复 id、`data/` 来源文件存在、
`feedback:` 来源指向存在的记录、**I1** 派生引用可解析（含历史版本）、**I5** 父单元撤回 / 失效后后代必须是 `retracted` 或 `stale`。
不判断内容对错；I2（独立来源计数）在给出证据时检查（见下文「状态与证据一致」），I3（类型兼容）、I4（条件不丢）尚未实现。

## 证据

`evidence/ledger.jsonl` 每行一次验证：

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
（不给 expect 时第一行全为真即支持），或 `{"kind": "python", "path": "evidence/checks/<id>.py"}`（退出码 0 支持、1 反驳、其他无法判定）。
`knosis knowledge verify` 重跑并记证据；其他验证用 `knosis knowledge evidence add` / `import`（工具写出的 `evidence.jsonl`）。

**状态与证据一致**（`check_units(..., evidence=...)`）：`verified` 至少一条未过期的支持；最近一条决定性证据是反驳时须为
`contested` / `retracted` / `stale`；**I2** `support: n` 不超过支持证据的独立来源数（按 `#` 之前去重）。
状态仍由 agent 写，Knosis 只检查它与证据是否矛盾。

**证据链**：`knosis knowledge trace <id>` 按派生关系列出每个单元与它的证据，即这条知识的发现途径。
**选取**：`knosis knowledge select [--about ...] [--form ...] [--text ...]` 按任务筛选（含本体元素）并附证据计数。

**使用知识（usage）**：dev 提交旁附 `<文件名>_used_units.jsonl`（每行 `{id, used_units}`）时，`feedback submit` 按题型统计每条知识 / skill
「用到时 / 没用到时」的 dev 正确率，写成 `scope=usage` 的候选 κ（id `usage/<知识>/<题型>`，`meta.of` 指向被评价的对象）与 feedback 证据。
usage 只能由 feedback / ablation 证据支持为 verified。测试题上的同类统计只写进评测报告（`eval.json` 的 `usage_effect`），不写回知识层。

## skill（使用流程）

**usage 管有没有用，skill 管怎么做。** skill 本身不讲对错；它的效果写成 usage 单元（`meta.of: skill:<名字>`），不直接记证据。

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
效果见评价它的 usage 单元（`knosis knowledge skills` 一并列出）；决策时在 `used_units` 里引用 `skill:<名字>`。skill 不按 agent 分开记录。

## 内化：去重、矛盾处理、构建知识体系、结构化

`knosis knowledge consolidate [--steps dedup,conflict,organize,structure]` 依次启动 agent 做四步；`knosis knowledge candidates`
列出疑似重复（内容相似、锚定同一对象）、可能矛盾（锚定同一对象的相关单元）与有争议的单元，只作提示。

| 步骤 | agent 做什么 | Knosis 检查 |
| --- | --- | --- |
| dedup 去重 | 同一件事保留一条（合并来源与条件），另一条改为 `merged` + `merged_into` | 别名指向活跃单元；不删除单元；不新增问题 |
| conflict 矛盾处理 | ① 收窄条件；② 用新证据裁决，一方撤回；③ 环境变了，旧的 stale + `superseded_by`；裁决不了的双方互记 `conflicts_with` 并标 contested | `conflicts_with` 双方都活跃时至少一方 contested；不删除单元 |
| organize 构建知识体系 | 把单跳知识串成「场景 → 数据间关系 → 具体对象」的大纲 `kb/outline.yaml`；可新增归纳单元 | 大纲引用存在、活跃单元都已归类；归纳单元 `provenance: derived` 且 `derived_from` 至少两条 |
| structure 结构化 | 把同一批知识组织成知识图谱 `kb/graph.json` 与流程图 `kb/flows/*.json` | 不改任何单元；每条边、每个流程节点引用活跃单元；图谱引用 ≥ 60% 的活跃对象知识，流程图引用 ≥ 60% 的 procedure / method / skill |

每步验收不过带着问题重试一次，仍不过就把 `kb/` 与 `evidence/` 恢复到这一步之前；通过后对比前后单元，把操作
（merge / supersede / status / conflict / narrow / rewrite / induce）追加到 `evidence/consolidate.jsonl`。
`knosis kb collect` 收集后自动运行；`knosis ws run --consolidate` 在 refine 结束后运行一次，结果快照为新的 refine 版本（K_final）。
大纲格式见 [interfaces.md](interfaces.md)；`knosis knowledge organize` 只做第三步。

### 知识体系的组成形式

同一批知识单元（κ、skill、本体单元）有五种组织方式，都只组织、不新增断言，每个节点、边、步骤都引用它来自的单元：

| 形式 | 文件 | 由谁产生 | 回答什么 |
| --- | --- | --- | --- |
| 知识体系树 | `kb/outline.yaml` | agent（organize） | 这些知识分几块、各讲什么 |
| 知识图谱 | `kb/graph.json` | agent（structure） | 环境里有哪些对象、它们之间是什么关系 |
| 流程图 | `kb/flows/<名字>.json` | agent（structure） | 某类任务按什么步骤做、在哪里检查与分支、每步用哪条知识 |
| 派生图 | 计算（`derived_from` / `merged_into` / `superseded_by` / `conflicts_with`） | Knosis | 哪条知识由哪些推出、并入或替换；撤回沿它传播 |
| 规则 / 公式卡片 | 计算（rule、formula 单元按图谱实体分组） | Knosis | 每个对象上有哪些规则与公式 |

```json
// kb/graph.json
{"entities": [{"id": "table:orders", "type": "table", "label": "orders", "units": ["extract/orders-key"]}],
 "relations": [{"src": "table:orders", "rel": "references", "dst": "table:customers", "label": "cust_id，多对一",
                "units": ["extract/orders-fk"]}]}
// kb/flows/find-grain.json
{"name": "find-grain", "title": "判断表的粒度", "goal": "……",
 "nodes": [{"id": "start", "kind": "start", "text": "拿到一张新表"},
           {"id": "count", "kind": "step", "text": "按候选键分组计数", "units": ["method/grain-check"]},
           {"id": "dup", "kind": "decision", "text": "有重复？", "units": ["extract/orders-key"]},
           {"id": "end", "kind": "end", "text": "记下粒度"}],
 "edges": [{"src": "start", "dst": "count"}, {"src": "count", "dst": "dup"}, {"src": "dup", "dst": "end", "label": "否"}]}
```

实体 `id` 全图唯一（`类型:名字`），`type` 建议取 dataset / table / column / entity_type / variable / concept / metric / tool / task；
每条关系至少引用一条活跃单元，端点必须存在；没有引用的实体必须是某条边的端点。流程图恰有一个 start、至少一个 end、
所有节点从 start 可达，decision 至少两条出边，step / check / decision 至少引用一条活跃单元或 `skill:<名字>`。
这些规则由 `knosis knowledge check` 检查（问题以 `structure` 开头）；引用的单元被撤回、失效或合并后，下次 structure 时更新。
`knosis knowledge graph [--view summary|graph|flows|derivation|cards] [--entity <实体>]` 查看，MCP 工具 `knowledge_graph` 按实体查子图。
知识图谱与流程图只在完整继承知识库时随之复制；只继承部分粒度时由新工作区的 structure 重建。

## 独立知识库

`knosis kb init <dir>` 建库（git 仓库，布局同上）。`knosis ws init ... --kb <dir> [--kb-scope method,usage,skill]` 继承（可只继承某些粒度；
本体随 relation / dataset、skill 随 `skill` 或 `usage` 一并继承）；
同一数据集上，知识库反馈记录里出现过的题目不进新工作区的测试集。`knosis kb merge <ws> --kb <dir>` 写回：
κ 按 id 合并、证据追加、反馈记录改名为 `<工作区>.<id>` 并改写引用，写回后整体检查，不通过就拒绝。
`knosis kb import-ontology <标注目录> --kb <dir> [--strip-gt]` 导入已有本体（到 `kb/knowledge/ontology/<单元名>/`）（如 ontology-bench 的标注），
`--strip-gt` 去掉来自 benchmark GT 的部分。

## 本体（结构化知识）

支持 OSI（Open Semantic Interchange，现 Apache Ossie）标准，用于企业数据的知识总结、收集与本体层对齐。
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

## dev 反馈

agent 自己就是 Codex / Claude Code：Knosis 不记录它的轨迹，只给它**结果**，由它把结果变成知识。

- 每个工作区有一个 dev 划分（`tasks/dev.jsonl`，无答案，与测试题不重叠）。agent 按 decide 的交付格式回答一部分或全部 dev 题，
  `knosis feedback submit <文件>` 返回逐题结果，同时写一条 `evidence/feedback/<id>.json`。
- 模式（`ws init --feedback`）：`answer` 给对错、分数和正确答案；`score` 只给对错与分数；`none` 关闭。`--budget` 限制提交次数。
- 反馈只接受 dev id；GT 从原始数据目录读，打分器与 `knosis eval` 是同一个函数（`decision` 层的 `score(..., ids)`）。
- **自动 RSI**：驱动模式下 `knosis ws run <ws> --stage refine --rounds N`，每轮结束时运行器把本轮的
  `stages/3_refine/round_<n>/dev_<交付文件>` 自动提交一次，结果写进下一轮的提示。
- 提示里只说明数据可能含噪声；哪些是噪声、怎么处理、反馈说明了什么，都由 agent 判断并写成 κ
  （例如「某条边是噪声」是一条 finding，provenance 指向反馈记录与数据位置）。
