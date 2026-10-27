# 数据入口

13 个数据入口都能开工作区并评测（`knosis ws init <数据集> <scenario>` → 四阶段 → `knosis eval`）。
数据默认在仓库下的 `data/<name>/`，可用 `KNOSIS_DATA_DIR` 指到别处；`knosis download <name>` 取数。
各数据集的来源、布局与陷阱见 `datacards/`（`knosis describe <name>`）。

| 数据集 | scenario | 交付 | 指标（离线可算的部分） | dev（反馈） | 未做 |
| --- | --- | --- | --- | --- | --- |
| ngdbench | ngd-fin | 答案 JSONL（可加噪声断言） | 答案集合 EM / F1；噪声断言 P/R；参照：照抄含噪图答案 | 50 题；演示题集 10 / 20 | NL 题面大量与 Cypher 不一致，见 [demos](demos.md)；其他 4 个域的导出模板 |
| tabarena | 51 个数据集 | 预测 CSV | RMSE / accuracy / AUC / log loss；参照：训练先验 | 默认 0，`--dev N` 留出训练行 | — |
| relbench | 库名，`-o task=` | 预测 CSV | AUROC / MAE / MAP@k；参照：平凡基线 | val 划分 | — |
| bibench | 用例 id 或 `all` | 表 JSONL | 上游匹配规则的 success；`-o metadata=true` 给初始本体 | all 模式 20 例 | — |
| kramabench | 领域 | 答案 JSONL | 上游 exact / 近似 / 列表 F1 | 约 25% | 需 LLM 判定的口径退化为规范化精确匹配 |
| burr | 真实库 / micro 场景 / `micro/<类别>` | 映射 JSONL | 上游 class / relation / attribute P/R/F1 | 多场景时约 25% | iswc、npd 的 D2RQ GT 打分 |
| llm-srbench | split | 表达式 JSONL | NMSE、Acc₀.₁（含 OOD） | 约 20% | 符号等价（需 LLM） |
| newtonbench | 领域 | 定律函数源码 | 上游 RMSLE；实验用 `newton` 工具 | 按（难度, 版本）整组 | 符号等价（需 LLM） |
| alphabench | evaluate（CSI300） | 因子判断 JSONL | 信号准确率、IC MAE / Spearman、分维度打分 | 50 题 | generate（需 Qlib 现算 IC）、美股 |
| spreadsheetbench | all / cell / sheet | 每条指令 3 个用例的输出 xlsx | 上游单元格值比较（评测前 LibreOffice 重算公式）：soft / hard；参照：原样交回输入 | 按指令切，默认 dev 5 / 测试 15 | .xlsm 默认跳过；需要 LibreOffice |
| text | 语料路径 | 无（只评知识层） | 单元数、来源可定位率、引文核对 | 无 | — |
| traces | 名字，`-o paths=` 轨迹（Codex / Claude Code 含子 agent / 逐步记录 / messages / ATIF），可选 `-o env=` | 无（只评知识层） | 引用步骤有效率、环境复核率、只核对轨迹的比例 | 无 | 迁移收益另做：合进知识库后在新题上对比 |
| whoandwhen | all / algorithm / hand | 每条失败日志的出错 agent 与步骤 JSONL | 上游 agent-level / step-level accuracy；参照：随机猜 | 按日志切，默认 dev 10 / 测试 30 | `-o answer=true` 给出任务标准答案（with ground truth 设置） |

轨迹（`traces`、`whoandwhen`、`kb collect`）统一存成 ATIF v1.7（`<id>.json` + `.md`，格式见 `knosis/data/traces.py`），
引用写 `<目录>/<id>.json#step/<n>`；v0.5 之前的步骤序列用 `knosis migrate` 转换（引用的步号一并改写）。

## Python 接口

```python
from knosis import load_dataset, list_datasets, describe

list_datasets()          # 13 个数据入口
describe("ngdbench")     # 给 agent 读的说明（来源 / 布局 / 陷阱），不含 GT
ds = load_dataset("ngdbench", "ngd-fin")
ds.tasks[0]              # Task(id, input, answer, split, kind, meta)；answer 是 GT，只在评测时读
g = ds.read("clean")     # 按后缀打开：parquet/csv → DataFrame，gpickle → 图 ...
```

```python
from knosis.knowledge import check_knowledge, ontology

check_knowledge("ws/x", root="ws/x")                      # κ 结构 + 证据一致 + 本体引用 + 去重别名与矛盾标记
model = ontology.from_bibench(load_dataset("bibench", "101248502"))   # Power BI 元数据 → 本体 core 层
ontology.write_ontology("onto/", {"semantic_model": model})
ontology.ontology_units(ontology.load_ontology("onto/"))  # 本体元素展开成 κ（form=schema）
```

```bash
knosis ontology convert relbench rel-f1 --out onto/f1    # manifest 的主外键 → core 层
knosis ontology check onto/f1
```
