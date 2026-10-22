# Knosis

> Knosis = know + gnosis。**面向 agent 的知识底座与实验平台。**

Knosis 把多源数据接进来，让 agent（Codex / Claude Code 等）从中构造**可审计、可撤回的显式知识**，
再用这些知识做决策，并评测知识到底有没有用。Knosis 本身不是 agent：它提供数据、知识格式、工具与评测，
agent 负责思考。所有后续工作（新数据、新工具、新的知识构造或使用方法）都可以接到这里来测。

## 四层 + 工作区

| 层 | 模块 | 内容 |
| --- | --- | --- |
| **数据层** | `knosis.data` | 统一入口 `load_dataset`，10 个数据入口返回同一个 `Dataset(tasks, files, schema, units, metrics)` |
| **知识层** | `knosis.knowledge` | 知识单元 κ（`units.jsonl`，带条件、来源、状态）+ **本体子层**（Apache Ossie 三文件 + EOB 扩展，与 ontology-bench 同一格式）+ **反馈子层**（dev 题上的结果，驱动自动 RSI）；结构检查 |
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

list_datasets()          # ngdbench relbench burr newtonbench llm-srbench alphabench kramabench tabarena bibench text traces
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

格式说明见 [docs/knowledge.md](docs/knowledge.md)。知识多了以后用 `knosis knowledge organize` 让 agent 整理成知识体系大纲，
`knosis mcp --ws <dir>` 把知识层与工具以 MCP 暴露给 agent；工具 / skill / MCP 的分工见 [docs/interfaces.md](docs/interfaces.md)。

### 工具层

```bash
knosis tool list
knosis tool card joins
knosis tool run profile -- --tables data/ --out stages/1_explore/profile
knosis tool run joins   -- --tables data/ --out stages/1_explore/joins --ontology stages/1_explore/joins/ontology
knosis tool run sql     -- --tables data/ --query 'SELECT COUNT(*) FROM train' --out stages/1_explore/sql
knosis tool run autoschemakg -- prepare --text data/ --out stages/1_explore/kg   # 文本 → KG，抽取由 agent 自己做
```

工具只产出注解（κ，`inferred` / `observed`），不改数据；神经模型工具（ULTRA、TabPFN）用
`KNOSIS_<NAME>_PYTHON` 指定 GPU 环境的解释器，`--prepare-only` 在本机只检查输入。

### 工作区与决策层

```bash
knosis ws init tabarena houses --out ws/houses                 # 试点 1：单表
knosis ws init ngdbench ngd-fin --out ws/ngd-fin --limit 200   # 试点 2：含噪属性图问答，抽 200 道测试题（另有 50 道 dev 题）

# 嵌入模式：在 Codex / Claude Code 里打开工作区，agent 读 AGENTS.md，自己调 ws next / ws check
knosis install                                                 # 安装 skill，让 agent 知道怎么用 Knosis

# 驱动模式：由 Knosis 启动 agent 跑完各阶段
knosis ws run ws/houses --agent codex --stage explore extract refine decide --rounds 2

# 反馈与自动 RSI：agent 交 dev 题答案换逐题结果；驱动模式下 refine 每轮自动提交一次
knosis feedback submit stages/3_refine/round_1/dev_predictions.jsonl --ws ws/ngd-fin
knosis ws run ws/ngd-fin --agent codex --stage refine --rounds 3

# 对照与评测
knosis ws fork ws/houses --out ws/houses-none --knowledge none  # none / K_0 / K_<n> / K_final
knosis eval ws/houses                                          # 写 .knosis/eval.json
```

阶段：explore 交笔记与可疑项；extract 产出 K_0；refine 每轮产出 K_n、写 changelog，并用 dev 反馈修正知识；
decide 对每道题 / 每个测试行恰好一个预测，可附 `used_units.jsonl` 记录用到的知识。
`ws check` 验收通过才提交并推进阶段。

**GT 软隔离**：GT 永远不导出到工作区（NGD-Fin 只给去掉加噪痕迹的观测图；TabArena 只给训练标签与测试特征；
测试题直到 decide 才生成；反馈只接受 dev 题）。驱动模式下 agent 进程带 `KNOSIS_DEPTH=1`，不能再起 agent，也不能运行 `knosis eval`。
这不是安全边界：同机的 agent 仍可能读到原始数据目录，正式评测请把 `data/` 放在 agent 环境之外。

## 现状（v0.4）

11 个数据入口都能开工作区并评测（`knosis ws init <数据集> <scenario>` → 四阶段 → `knosis eval`）：

| 数据集 | scenario | 交付 | 指标（离线可算的部分） | dev（反馈） | 未做 |
| --- | --- | --- | --- | --- | --- |
| ngdbench | ngd-fin | 答案 JSONL（可加噪声断言） | 答案集合 EM / F1；噪声断言 P/R；参照：照抄含噪图答案 | 50 题；演示题集 10 / 20 | NL 题面大量与 Cypher 不一致，见 [demos](docs/demos.md)；其他 4 个域的导出模板 |
| tabarena | 51 个数据集 | 预测 CSV | RMSE / accuracy / AUC / log loss；参照：训练先验 | 默认 0，`--dev N` 留出训练行 | — |
| relbench | 库名，`-o task=` | 预测 CSV | AUROC / MAE / MAP@k；参照：平凡基线 | val 划分 | — |
| bibench | 用例 id 或 `all` | 表 JSONL | 上游匹配规则的 success；`-o metadata=true` 给初始本体 | all 模式 20 例 | — |
| kramabench | 领域 | 答案 JSONL | 上游 exact / 近似 / 列表 F1 | 约 25% | 需 LLM 判定的口径退化为规范化精确匹配 |
| burr | 真实库 / micro 场景 / `micro/<类别>` | 映射 JSONL | 上游 class / relation / attribute P/R/F1 | 多场景时约 25% | iswc、npd 的 D2RQ GT 打分 |
| llm-srbench | split | 表达式 JSONL | NMSE、Acc₀.₁（含 OOD） | 约 20% | 符号等价（需 LLM） |
| newtonbench | 领域 | 定律函数源码 | 上游 RMSLE；实验用 `newton` 工具 | 按（难度, 版本）整组 | 符号等价（需 LLM） |
| alphabench | evaluate（CSI300） | 因子判断 JSONL | 信号准确率、IC MAE / Spearman、分维度打分 | 50 题 | generate（需 Qlib 现算 IC）、美股 |
| text | 语料路径 | 无（只评知识层） | 单元数、来源可定位率、引文核对 | 无 | — |
| traces | 名字，`-o paths=` 轨迹（Codex / Claude Code / 逐步记录 / messages），可选 `-o env=` | 无（只评知识层） | 引用步骤有效率、环境复核率、只核对轨迹的比例 | 无 | 迁移收益另做：合进知识库后在新题上对比 |

| 部分 | 状态 |
| --- | --- |
| 知识层 | κ（粒度 instance / relation / dataset / method / utility）+ 证据账本 + 可执行检查 + 本体 + skill（解题集）；检查必填字段、来源、I1、I2、I5、状态与证据一致、证据过期、method 脚本可脱离原工作区运行；I3、I4 未实现 |
| 知识库 | 独立知识库：继承（可按粒度）、写回（被引用的轨迹随知识带走）、导入 ontology-bench 标注（可去 GT） |
| 工具层 | sql / profile / joins / fit / newton / tabpfn（含 cv，本机 CPU 推断已验证）/ autoschemakg（文本 → KG，agent 自己抽取或 `--llm` 命令）可用；ULTRA 只适配接口 |
| 知识体系与 MCP | `outline.yaml` 大纲（导航层，`knowledge organize` 由 agent 整理）；`knosis mcp` 手写 stdio 服务，14 个工具，Codex 接入已验证 |
| agent 接入 | Codex 驱动模式在单表、方程、多表、KG 四类场景跑通演示（含 refine 自动反馈），以及从 Codex 自身轨迹与 agent-rsi AppWorld 轨迹提取知识，结果见 [docs/demos.md](docs/demos.md)；Claude Code 接口相同，未做 smoke |

范围与定位见 [docs/scope.md](docs/scope.md)；路线：跨 agent 读者对照、只继承 method / skill 的迁移实验、L2 复杂查询。设计背景见 [docs/design.md](docs/design.md)。

## 扩展

新增数据集、工作区导出器、评测或工具，各只需要一个文件或目录，见 [docs/extending.md](docs/extending.md)。
代码风格：短小、直接、不写防御性代码；出错就直接抛出。

## 许可

代码 Apache-2.0。数据集与模型权重各有许可，见 `datacards/` 与各工具的 `TOOL.md`；Knosis 不分发数据或权重。
