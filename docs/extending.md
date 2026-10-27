# 扩展 Knosis

每类扩展只碰一个文件或目录，并补一个用 `tmp_path` 造最小数据的测试。需要真实数据的测试在数据不存在时 `pytest.skip`。

## 新增数据集（数据层）

1. `knosis/data/loaders/<name>.py`：一个 `load(scenario, root=None, **kw) -> Dataset`，用 `@register("<name>", scenarios=...)` 注册，
   并在 `knosis/data/loaders/__init__.py` 的 import 列表里加上模块名。
2. `knosis/data/cards/<name>.md`：给 agent 读的说明（来源、布局、陷阱），**不得包含 GT**。
3. 可选：`knosis/data/download.py` 的 `SOURCES` 加一行；`datacards/<name>.md` 写上游来源与许可（给人看）。

`Task.answer` 放 GT（值或文件路径），`Task.input` 放题面；GT 不进 `meta`，除非字段名说明它是提示（如 BI-Bench 的 `oracle`）。

## 让数据集能开工作区

写 `knosis/workspace/exporters/<name>.py`，用 `@register("<name>")` 装饰 `export(ds, ws, write_data=True, **opts) -> dict`，
并加进 `exporters/__init__.py` 末尾的 import 列表：

| 返回键 | 内容 |
| --- | --- |
| `brief` | BRIEF.md 正文（模板放 `workspace/templates/briefs/`，事实先从数据算出来再写；只说数据可能含噪声，不教怎么处理） |
| `tasks` | 测试题（无答案），每项至少有 `id`；decide 阶段才写到 `tasks/tasks.jsonl` |
| `dev` | 开发题（无答案，与测试题不重叠），用于反馈；可为空 |
| `holdout` | 写进 BRIEF 当示例、不参与测试的题目 id |
| `output` | decide 交付文件名：`predictions.jsonl`（每行 `{id, answer}`）或 `predictions.csv`（`row_id`, `prediction`, …）；没有下游预测时为 None |
| `modalities` | 用于挑选 TOOLS.md 里的工具，如 `["graph"]`、`["table"]`、`["tables"]` |

`write_data=False` 时只返回上述内容不写数据（decide 阶段重新生成题目时用），同样的 `opts` 必须给出同样的划分（`split()` 按 seed 切分）。
原始文件用 `place()` 放进工作区（硬链接，跨盘时复制）；不要用软链接，它会暴露原始目录与旁边的 GT。
命令行的 `ws init` 用 `--dev` / `--limit` / `--seed` / `-o key=value` 把参数传给导出器。

## 新增评测（决策层）

在 `knosis/decision/<name>.py` 写打分器并注册，加进 `decision/__init__.py` 末尾的 import 列表：

```python
from . import register

@register("<name>")
def score(ws, state, ds, path, ids) -> dict:
    # path：交付文件；ids：要打分的题目 id（测试题或 dev 题）；ds：从原始目录重新加载的 Dataset（含 GT）
    return {"metrics": {...},                       # 汇总指标
            "items": [{"id": ..., "ok": ..., "gold": ...}, ...],   # 逐题结果，反馈会原样返回给 agent（score 模式去掉 gold）
            "reference": {...}}                     # 可选：平凡基线
```

同一个函数既用于 `knosis eval`（测试题），也用于 `knosis feedback submit`（dev 题）。

## 新增工具（工具层）

建目录 `knosis/tools/<name>/`：

- `TOOL.md`：YAML 头 `name / version / kind(program|model) / modality / stage / license`，正文写用途、命令示例、输出、限制。
  正文会被拼进工作区的 TOOLS.md，agent 靠它决定要不要用。
- `run.py`：命令行入口，`--out DIR` 输出目录；结束时调用 `knosis.tools.write_result(out, name, params, units, started)`，
  写 `units.jsonl`（κ，`inferred` 或 `observed`，provenance 以 `tool:<name>@<version>(...)` 开头）和 `run.json`。
- `__init__.py`（空），便于测试直接 import。

工具不改数据。依赖重的工具只在真实推断路径里 import，并提供 `--prepare-only`；
运行时用 `KNOSIS_<NAME>_PYTHON` 指定解释器，核心包不装这些依赖。
表格工具可用 `knosis.tools.read_tables(paths)` 统一读取 CSV / parquet。

## 新增知识格式（知识层）

κ 的字段集合与检查只在 `knosis/knowledge/units.py`；本体的读写、引用、检查与转换只在 `knosis/knowledge/ontology.py`。
新增一种数据源 → 本体的转换，写一个 `from_<name>(ds) -> dict`（返回 core 层文档），复用 `from_tables` / `relationship` / `eob`，
并在 `cli.py` 的 `ontology convert` 里登记。

代码风格：短小、直接、不写防御性代码；出错就直接抛出。
