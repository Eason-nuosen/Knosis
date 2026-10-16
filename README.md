# Knosis

> Knosis = know + gnosis。**面向 agent 的知识底座与实验平台。**

Knosis 把多源数据接进来，让 agent（Codex / Claude Code 等）从中构造**可审计、可撤回的显式知识**，
再用这些知识做决策，并评测知识到底有没有用。Knosis 本身不是 agent：它提供数据、知识格式、工具与评测，
agent 负责思考。所有后续工作（新数据、新工具、新的知识构造或使用方法）都可以接到这里来测。

## 四层 + 工作区

| 层 | 模块 | 内容 |
| --- | --- | --- |
| **数据层** | `knosis.data` | 统一入口 `load_dataset`，10 个数据入口返回同一个 `Dataset(tasks, files, schema, units, metrics)` |
| **知识层** | `knosis.knowledge` | 知识单元 κ（`units.jsonl`，带条件、来源、状态）+ **本体子层**（Apache Ossie 三文件 + EOB 扩展，与 ontology-bench 同一格式）；结构检查 |
| **工具层** | `knosis.tools` | 统一的 `TOOL.md + run.py`：SQL、表画像、join 发现（参考 BI-Agent）、ULTRA、TabPFN |
| **决策层** | `knosis.decision` | decide 产物的打分（从原始目录读 GT），与训练先验 / 含噪答案等参照对比，并统计知识被引用的情况 |
| 工作区 | `knosis.workspace` | 把四层串起来：explore → extract → refine（多轮）→ decide，每步验收并提交 git，GT 不进工作区 |

```
数据层 ──导出──▶ 工作区 data/ ──agent + 工具──▶ 知识层 knowledge/{units.jsonl, ontology/} ──▶ 决策层 预测 + 评测
```

## 安装

```bash
conda env create -f environment.yml     # 建 knosis 环境，以 -e .[all] 安装
conda activate knosis
pytest -q
```

或任意 Python 3.10+：`pip install -e '.[all]'`。核心包不依赖 torch；神经模型工具在各自环境里运行。
数据默认在仓库下的 `data/<name>/`，可用 `KNOSIS_DATA_DIR` 指到别处；`knosis download <name>` 取数。

## 快速开始

### 数据层

```python
from knosis import load_dataset, list_datasets, describe

list_datasets()          # ngdbench relbench burr newtonbench llm-srbench alphabench kramabench tabarena bibench text
describe("ngdbench")     # 给 agent 读的说明（来源 / 布局 / 陷阱），不含 GT
ds = load_dataset("ngdbench", "ngd-fin")
ds.tasks[0]              # Task(id, input, answer, split, kind, meta)；answer 是 GT，只在评测时读
g = ds.read("clean")     # 按后缀打开：parquet/csv → DataFrame，gpickle → 图 ...
```

### 知识层

```python
from knosis.knowledge import load_units, check_knowledge, ontology

check_knowledge("ws/x/knowledge")                         # κ 结构 + 本体跨文件引用 + κ.about 引用
model = ontology.from_bibench(load_dataset("bibench", "101248502"))   # Power BI 元数据 → 本体 core 层
ontology.write_ontology("onto/", {"semantic_model": model})
ontology.ontology_units(ontology.load_ontology("onto/"))  # 本体元素展开成 κ（form=schema）
```

```bash
knosis ontology convert relbench rel-f1 --out onto/f1    # manifest 的主外键 → core 层
knosis ontology check onto/f1
```

格式说明见 [docs/knowledge.md](docs/knowledge.md)。

### 工具层

```bash
knosis tool list
knosis tool card joins
knosis tool run profile -- --tables data/ --out stages/1_explore/profile
knosis tool run joins   -- --tables data/ --out stages/1_explore/joins --ontology stages/1_explore/joins/ontology
knosis tool run sql     -- --tables data/ --query 'SELECT COUNT(*) FROM train' --out stages/1_explore/sql
```

工具只产出注解（κ，`inferred` / `observed`），不改数据；神经模型工具（ULTRA、TabPFN）用
`KNOSIS_<NAME>_PYTHON` 指定 GPU 环境的解释器，`--prepare-only` 在本机只检查输入。

### 工作区与决策层

```bash
knosis ws init tabarena houses --out ws/houses                 # 试点 1：单表
knosis ws init ngdbench ngd-fin --out ws/ngd-fin --limit 200   # 试点 2：含噪属性图问答，抽 200 道测试题

# 嵌入模式：在 Codex / Claude Code 里打开工作区，agent 读 AGENTS.md，自己调 ws next / ws check
knosis install                                                 # 安装 skill，让 agent 知道怎么用 Knosis

# 驱动模式：由 Knosis 启动 agent 跑完各阶段
knosis ws run ws/houses --agent codex --stage explore extract refine decide --rounds 2

# 对照与评测
knosis ws fork ws/houses --out ws/houses-none --knowledge none  # none / K_0 / K_<n> / K_final
knosis eval ws/houses                                          # 写 .knosis/eval.json
```

阶段：explore 交笔记与可疑项；extract 产出 K_0；refine 每轮产出 K_n 并写 changelog；
decide 对每道题 / 每个测试行恰好一个预测，可附 `used_units.jsonl` 记录用到的知识。
`ws check` 验收通过才提交并推进阶段。

**GT 软隔离**：GT 永远不导出到工作区（NGD-Fin 只给去掉加噪痕迹的观测图；TabArena 只给训练标签与测试特征；
测试题直到 decide 才生成）。驱动模式下 agent 进程带 `KNOSIS_DEPTH=1`，不能再起 agent，也不能运行 `knosis eval`。
这不是安全边界：同机的 agent 仍可能读到原始数据目录，正式评测请把 `data/` 放在 agent 环境之外。

## 现状（v0.3）

| 部分 | 状态 |
| --- | --- |
| 数据层 10 个入口 | 可用；工作区导出只支持 NGD-Fin、TabArena |
| 知识层 κ + 本体 | 结构检查覆盖必填字段、来源文件、I1 派生引用、I5 撤回传播、本体跨文件引用；I2–I4 未实现 |
| 工具层 | SQL / 表画像 / join 发现可用；ULTRA / TabPFN 接口已适配，真实 GPU 推断待验收 |
| 决策层 | NGD-Fin（答案集合 EM / F1）、TabArena（RMSE / accuracy / AUC / log loss）可用；其余数据集待补 |
| agent 接入 | Codex 驱动模式完成端到端 smoke test；Claude Code 驱动 / 嵌入模式接口相同 |

路线：先补齐其余数据集的导出器与打分器（BI-Bench 优先，配合本体层），再做 refine 的 RSI 与工具进化、
L2 复杂查询、跨模型族的 transmission test。设计背景见 [docs/design.md](docs/design.md)。

## 扩展

新增数据集、工作区导出器、评测或工具，各只需要一个文件或目录，见 [docs/extending.md](docs/extending.md)。
代码风格：短小、直接、不写防御性代码；出错就直接抛出。

## 许可

代码 Apache-2.0。数据集与模型权重各有许可，见 `datacards/` 与各工具的 `TOOL.md`；Knosis 不分发数据或权重。
