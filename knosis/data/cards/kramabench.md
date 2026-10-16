# KramaBench —— 数据湖到洞察的端到端（多源异构）

## 来源

MIT CSAIL。**KramaBench: A Benchmark for AI Systems on Data-to-Insight Pipelines over
Data Lakes**，arXiv **2506.06541**（2025-06-06），ICLR 2026。
作者：Eugenie Lai, Gerardo Vitagliano, Ziyu Zhang … Michael Cafarella, Lei Cao,
Samuel Madden, Tim Kraska。
仓库 https://github.com/mitdbg/KramaBench ；
数据 https://huggingface.co/datasets/eugenie-y/kramabench （id 里是小写 b）。

获取：`knosis download kramabench`（`git clone`，checkout 约 640 MB）。
公开、无 gated、无需申请。**没有 PyPI 包**，只能从 checkout 装。

**许可混乱，务必注意。**
- GitHub 仓库**没有 LICENSE 文件** → 代码许可未声明。
- HF 卡片的 front-matter 写的是 `license: cc`（**没有版本号、没有变体**）。
- 有一个**未合并**的 HF 社区 PR 提议改成 `cc-by-nc-4.0`，说是反映论文条款。
- 有第三方资料说是「MIT（代码）+ CC-BY-NC-4.0（数据）」，但**在仓库里找不到任何 MIT 文本**。

实务判断：**数据按 CC BY-NC-4.0 对待（署名 + 非商用）**，代码视为未授权。
在意的话请直接联系作者确认。

体量（上游 README 口径）：104 个任务、633 个子任务、1764 个文件、约 1.7 GB。
实际 checkout 约 640 MB（`data/*/raw/` 被 gitignore 掉了），所以磁盘上的文件数
**不会等于 1764**。最新 commit 在 README 之后改过 legal，所以子任务数也有小幅漂移
（实际数出 631 而非 633）—— 别把 1764 / 633 硬编码。

## 说明

KramaBench 考的是**从一堆杂乱的原始文件出发，一路做到可验证的结论**。
每个任务是「一个问题 + 一个数据湖目录」，要求 agent 自己找文件、定方案、写代码、
算出答案。所以它同时评两件事：**最终答案**，以及**中间的数据流水线写得对不对**。

6 个领域：考古、天文、生物医学、环境、法律取证、野火。
**上游目录名是 `archeology`（拼错的，少一个 a）** —— 那是路径的一部分，不要改。
同理 `environment` 是「环境」，不是「environmental」。

**⚠️ 这里的描述故意写得很克制。** 本基准考的就是 agent 自己去找文件、自己判断
哪些文件相关、自己设计流水线。**预先给出文件清单、字段表、或推荐用哪几个文件，
等于替它把题做了。** 所以 Knosis 只给出数据湖目录 `ds.files["lake"]`，**不做解析，也不给文件清单**。

任务结构：`workload/<域>.json`，每个任务是
`{id, query, answer, answer_type, runtime, data_sources, subtasks[]}`。
任务 id 形如 `legal-hard-1`，子任务 `legal-hard-1-1`。
**id 里的编号不连续**（`archeology-hard-1`, `archeology-hard-2`, `archeology-easy-3`, …），
不要假设是连续序列。另外 **`data_sources` 在任务层是列表，在某些子任务里却是裸字符串** ——
严格 schema 会在这里崩。

参考解在 `solutions/<域>/<任务 id>.py`，全是可运行的 Python，读 `./data/<域>/input/`。
**没有逐任务的验证脚本** —— 验证是集中的：`answer_type` → 指标的映射写死在
`benchmark/fixtures/answer_type_fixtures.json` 里。答案类型与对应指标：

- `numeric_exact` → `success`（精确）
- `string_exact` → `success`（精确）
- `list_exact` → `f1` / `precision` / `recall`
- `numeric_approximate` → MAE / MSE / RAE
- `string_approximate` → `llm_paraphrase`（**调 LLM，要钱、不确定**）
- `list_approximate` → `f1_approximate`（**逐对调 LLM**）

除答案外，`evaluator.py` 还会调 `llm_code_eval` 给**流水线本身**打分
（`pipeline_evaluation_engine`），最后取平均。所以有两个读数，别只看答案准确率。

上游还提供 `dr-input/<域>/<域>-<难度>-<n>/` —— 每个任务的**oracle 文件子集**
（"truth subset" 检索设定）。`eval.sh --use_truth_subset` 走这条路，
**但这个 flag 在上游 README 的参数表里根本没写**。

适合：多源异构的数据接入、文件格式识别、端到端流水线设计、agent 自主探索。
不适合：用 `datasets.load_dataset()` 一把加载 —— **HF viewer 是坏的**
（不同域的同名列类型不一致，Arrow 报 `float 1.5 truncated to int64`），
必须按域分开读，或干脆用 clone。

陷阱：
- **HF 数据集卡片基本是空的**，内容只有 front-matter 那两行，没有任何说明。
- 上游 baseline（DS-GURU）的 `process_dataset` 用**非递归** `os.listdir`，
  所以它看不到 `data/astronomy/input/STORM-AI/warmup/v2/GOES/` 里的文件 ——
  天文域会从 1538 个文件变成 10 个。**递归是你自己的责任。**
- `evaluate.py` 会往仓库里写 `results/`，只读安装会被污染。
- 上游 README 的结构清单是错的：它列了 `results`（其实被 gitignore），
  却漏了实际存在的 `dr-input/`、`experts/`、`solutions/`、`tests/`。
- 上游 repo 自己的 citation block 引的标题是错的（引成了别的名字），以 arXiv 标题为准。
- 上游 leaderboard 最好成绩约 22%，而论文 55% —— 两者检索/评测配置不同，**不可直接横比**。
