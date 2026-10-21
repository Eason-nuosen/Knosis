# Knosis 工作区

先读 `BRIEF.md`。用 `knosis ws next .` 获取当前阶段的目标，
完成交付后运行 `knosis ws check .` 验收并提交知识版本。
命令行不在 PATH 时用 `$python -m knosis ...`。

## 目录与环境

- `data/`：只读的可见数据，不要修改。
- `tasks/dev.jsonl`：开发题（无答案，与测试题不重叠），可用 `knosis feedback submit <文件>` 换取反馈。
- `tasks/tasks.jsonl`：只在 decide 阶段出现的无答案测试题。
- `stages/1_explore/`、`2_extract/`、`3_refine/round_<n>/`、`4_decide/`：
  当前阶段的代码、笔记和交付物。
- `knowledge/units.jsonl`：当前知识层，每行一个 κ。
- `knowledge/evidence.jsonl`：证据账本，每行一次验证结果（用命令写，不要手改）。
- `knowledge/checks/`：单元的可执行检查脚本（可选）。
- `knowledge/skills/<名字>/SKILL.md`：解题集，如何运用知识解某类任务（可选，见下文）。
- `knowledge/ontology/`（可选）：本体，Ossie 三文件格式，见下文。
- `knowledge/feedback/`：dev 反馈记录（只读，由 `knosis feedback submit` 写入）。
- `.knosis/state.json`：阶段状态；历史知识快照在 `stages/`。

数据可能含噪声；哪些是噪声、如何处理，由你判断，判断的依据写进知识。
Python 使用 `$python`；已安装 pandas、pyarrow 等数据依赖。
可用工具及调用方式见 `TOOLS.md`。工具只产出注解，不修改数据。
工具输出的 `inferred` 不等于已验证，采纳前需判断并在数据上验证。

## 知识单元 κ

必填：`id`（唯一字符串）、`content`、`form`、`provenance`、`status`。
`form` 为 finding / fact / rule / formula / schema / tool / method；
`method` 是元知识：「如何发现或验证某类知识」的步骤与适用条件，可以附可执行检查，换一份数据也能照做。
`status` 为 observed / inferred / verified / contested / retracted / stale。
可选：`scope`（粒度，见下）、`condition`（条件与例外）、`derived_from`（父单元 id 列表）、
`support`（独立支持数）、`about`（引用的本体元素或数据位置，如 `data/train.parquet#col/bmi`）、
`check`（可执行检查，见下）、`meta`（分数、反例数等）。

`scope` 说明一条知识在讲什么：`instance` 某个具体对象（行、节点、边）；`relation` 对象之间的结构（join、本体关系）；
`dataset` 这份数据整体的规律、分布、公式；`method` 如何发现或验证某类知识（只写步骤，结论另写成别的粒度）；
`utility` 哪些知识对哪类题有用（Knosis 会根据 dev 反馈自动生成候选）。不写时按 form 与来源自动推断。

来源写法：

- 数据：`data/graph.gpickle#node/<id>`、`data/graph.gpickle#edge/<src>|<label>|<dst>`，
  `data/train.parquet#row/<row_id>` 或 `#col/<列名>`。
- 工具：`tool:<name>@<version>(<k=v,...>)`。
- 反馈：`feedback:<记录 id>#item/<题目 id>`。
- 纯派生：`derived`，此时必须填写 `derived_from`。
- 多来源用 ` ; ` 连接。合并知识保留父单元，撤回后将受影响后代标为 stale 或 retracted。

## 证据与验证

知识要能被证据支持或反驳。每次验证记一条证据，结论为 support / refute / undetermined（条件或测量无法确认）/
not_applicable（前提不成立）：

- 可执行检查：单元带 `check`，由 Knosis 重跑并记证据（`knosis knowledge verify [--unit ID]`）。
  `{"kind": "sql", "query": "SELECT ... FROM train ...", "expect": [[...]]}`（表名为 `data/` 下文件名；不给 expect 时第一行全为真即支持），
  或 `{"kind": "python", "path": "knowledge/checks/<id>.py"}`（在工作区根目录运行；退出码 0 支持，1 反驳，其他无法判定）。
  检查脚本只能读 `data/`、只能导入 `knowledge/checks/` 里的代码：知识会被别的工作区继承，那里没有你的 `stages/`。
  `form=method` 的检查在 extract / refine 验收时会放到只含 `data/` 与 `knowledge/` 的临时目录里试跑。
- 其他验证：`knosis knowledge evidence add --unit ID --verdict support --method tool|data|feedback|derivation|human --source <来源> --note "<数字>" [--inputs data/...]`；
  工具写出的 `evidence.jsonl` 用 `knosis knowledge evidence import <文件>` 导入。

状态规则（`ws check` 会检查）：`verified` 至少有一条未过期的支持证据；最近一条决定性证据是反驳时，
状态须为 contested、retracted 或 stale（收窄条件后可再验证）；`support: n` 不超过独立来源数。
证据记录了所依赖数据的指纹，数据变了证据就过期。`knosis knowledge trace ID` 输出一条知识的证据链。

## 选取知识

知识正确不等于对当前任务有用。`knosis knowledge select [--about 本体元素] [--form F] [--text 关键词]`
列出候选（含本体元素）与证据计数，`--scope` 按粒度筛选；`knosis knowledge index --prefix data/...`
按对象反查相关知识。用哪些由你决定，并在 decide 时记录 `used_units`。
如果工作区从知识库继承了知识（`stages/0_inherit/knowledge` 存在），它们同样要按任务判断是否适用，
可以修正、收窄或撤回。

## skill：如何运用知识（解题集）

知识是对环境的理解，与谁来用无关；skill 是用法：遇到某类题，按什么步骤、调用哪些知识去解。
skill 不讲对错，只讲有没有效；回看反馈时，答对的题可以总结出有效的解法，答错的题可以总结出要避开的做法。
写在 `knowledge/skills/<名字>/SKILL.md`，头部 YAML：`name`（与目录名相同）、`description`（一句话）、
`when`（适用的题型与条件）、`uses`（引用的知识 id）、`derived_from`（总结自哪些反馈记录，可选）、
`status`（active / stale / retracted）；正文写步骤。引用的知识被撤回后，skill 须改为 stale 或 retracted。
`knosis knowledge skills` 列出已有 skill；decide 时用到的 skill 在 `used_units` 里写成 `skill:<名字>`。

## 本体（可选）

结构性知识（表 / 列 / 主键 / join / 度量，概念与概念间关系，列到概念的映射）可以写成本体，
放在 `knowledge/ontology/<name>.{semantic_model,ontology,mapping}.yaml`（多份本体各占一个子目录 `knowledge/ontology/<name>/`）（Apache Ossie 0.2 + EOB 扩展，
EOB 信息写在 `custom_extensions`，`vendor_name: EOB`，`data` 为 JSON 字符串）。
本体元素本身也是知识（`form=schema`，id 形如 `ontology/[<子目录>/]join/<名字>`），可以对它记证据、派生或撤回；
κ 用 `about: ["Product", "Sale.product", "sales.Amount"]` 引用本体元素；`ws check` 会检查引用能否解析，
以及 mapping 的 `expression` 是否是存在的 `dataset.field`。
`python -c "from knosis.knowledge import ontology; help(ontology)"` 有格式说明与构造函数。

## 边界

不要寻找、读取或推测测试 GT 的存放位置；不要运行 `knosis eval`。工作区外的文件与本任务无关。
Knosis 是知识层，不是新的 agent；在本会话完成阶段，不要嵌套启动 agent。
