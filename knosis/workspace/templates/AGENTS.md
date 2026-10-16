# Knosis 工作区

先读 `BRIEF.md`。用 `knosis ws next .` 获取当前阶段的目标，
完成交付后运行 `knosis ws check .` 验收并提交知识版本。
命令行不在 PATH 时用 `$python -m knosis ...`。

## 目录与环境

- `data/`：只读的可见数据，不要修改。
- `tasks/tasks.jsonl`：只在 decide 阶段出现的无答案题目。
- `stages/1_explore/`、`2_extract/`、`3_refine/round_<n>/`、`4_decide/`：
  当前阶段的代码、笔记和交付物。
- `knowledge/units.jsonl`：当前知识层，每行一个 κ。
- `knowledge/ontology/`（可选）：本体，Ossie 三文件格式，见下文。
- `.knosis/state.json`：阶段状态；历史知识快照在 `stages/`。

Python 使用 `$python`；已安装 pandas、pyarrow 等数据依赖。
可用工具及调用方式见 `TOOLS.md`。工具只产出注解，不修改数据。
工具输出的 `inferred` 不等于已验证，采纳前需判断并在数据上验证。

## 知识单元 κ

必填：`id`（唯一字符串）、`content`、`form`、`provenance`、`status`。
`form` 为 finding / fact / rule / formula / schema / tool；
`status` 为 observed / inferred / verified / retracted / stale。
可选：`condition`（条件与例外）、`derived_from`（父单元 id 列表）、
`support`（独立支持数）、`about`（引用的本体元素）、`meta`（验证支持数、反例数、分数等）。

来源写法：

- 数据：`data/graph.gpickle#node/<id>`、`data/graph.gpickle#edge/<src>|<label>|<dst>`，
  `data/train.parquet#row/<row_id>` 或 `#col/<列名>`。
- 工具：`tool:<name>@<version>(<k=v,...>)`。
- 纯派生：`derived`，此时必须填写 `derived_from`。
- 多来源用 ` ; ` 连接。合并知识保留父单元，撤回后将受影响后代标为 stale 或 retracted。

## 本体（可选）

结构性知识（表 / 列 / 主键 / join / 度量，概念与概念间关系，列到概念的映射）可以写成本体，
放在 `knowledge/ontology/<name>.{semantic_model,ontology,mapping}.yaml`（Apache Ossie 0.2 + EOB 扩展，
EOB 信息写在 `custom_extensions`，`vendor_name: EOB`，`data` 为 JSON 字符串）。
κ 用 `about: ["Product", "Sale.product", "sales.Amount"]` 引用本体元素；`ws check` 会检查引用能否解析，
以及 mapping 的 `expression` 是否是存在的 `dataset.field`。
`python -c "from knosis.knowledge import ontology; help(ontology)"` 有格式说明与构造函数。

## 边界

不要寻找、读取或推测测试 GT 的存放位置；不要运行 `knosis eval`。工作区外的文件与本任务无关。
Knosis 是知识层，不是新的 agent；在本会话完成阶段，不要嵌套启动 agent。
