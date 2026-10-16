# KramaBench

| 项 | 值 |
| --- | --- |
| 论文 | KramaBench: A Benchmark for AI Systems on Data-to-Insight Pipelines over Data Lakes |
| arXiv | **2506.06541**（2025-06-06）；ICLR 2026 |
| 作者 | Eugenie Lai, Gerardo Vitagliano, Ziyu Zhang … Michael Cafarella, Lei Cao, Samuel Madden, Tim Kraska（MIT CSAIL） |
| 代码 | https://github.com/mitdbg/KramaBench |
| 数据 | https://huggingface.co/datasets/eugenie-y/kramabench （**id 里是小写 b**） |
| 访问 | 公开、无 gated、无需申请 |
| **许可** | **代码未声明** / 数据按 **CC BY-NC-4.0** 对待（见下） |
| 上游版本 | **无 release 标签**；`pyproject.toml` 里是 `1.0.0.dev0`。所见 clone 单 commit `b2e0d77540263f8b6119f977fe79a8c4386b5a02`（`Updates to legal-hard-29`） |

## 许可

**许可混乱，务必注意。**

- GitHub 仓库**没有 LICENSE 文件** —— 已核实 `ls -a | grep -iE "licen|copying"` 无返回
  → **代码许可未声明**。
- HF 卡片的 front-matter 写的是 `license: cc`（**没有版本号、没有变体**）。
- 有一个**未合并**的 HF 社区 PR 提议改成 `cc-by-nc-4.0`，说是反映论文条款。
- 有第三方资料说是「MIT（代码）+ CC-BY-NC-4.0（数据）」，
  但**在仓库里找不到任何 MIT 文本**。

实务判断：**数据按 CC BY-NC-4.0 对待（署名 + 非商用）**，代码视为未授权。
在意的话请直接联系作者确认。

## 获取

```bash
knosis download kramabench              # git clone（--depth 1）上游仓库
```

**数据全在 git 仓库里。** 没有 pip 包、没有 release、没有申请表。
clone 下来就有全部 `workload/*.json`、`solutions/`、数据湖与评测器。

**⚠️ 别用 `datasets.load_dataset("eugenie-y/kramabench")` 一把加载。**
**HF viewer 是坏的** —— 不同域的同名列类型不一致，
Arrow 会报 `float 1.5 truncated to int64`。
必须按域分开读，或干脆用 clone（推荐）。

上游的评测入口：

```bash
python evaluate.py --sut YourSUT --workload legal --verbose
```

`evaluate.py` 产出：

```
results/<SUT>/<workload>_measures_<timestamp>.csv   # 细粒度指标
results/aggregated_results.csv                      # 每域一行的汇总
```

## 体量

**上游 README 口径**（见其 "Breakdown of tasks per domain" 表）：

| 域 | 任务 | 子任务 | % Hard | 文件数 | Raw size |
| --- | ---: | ---: | ---: | ---: | ---: |
| Archaeology | 12 | 71 | 50 % | 5 | 7.5 MB |
| Astronomy | 12 | 68 | 50 % | 1 556 | 486 MB |
| Biomedical | 9 | 38 | 67 % | 7 | 175 MB |
| Environment | 20 | 148 | 70 % | 37 | 31 MB |
| Legal | 30 | 188 | 53 % | 136 | 1.3 MB |
| Wildfire | 21 | 120 | 71 % | 23 | 1 GB |
| **Total** | **104** | **633** | **61 %** | **1 764** | **1.7 GB** |

**实际 checkout 约 640 MB** —— 已核实 `du -sh knosis/data/kramabench/KramaBench/data/*`：

```
7.2M   data/archeology
486M   data/astronomy
86M    data/biomedical
30M    data/environment
1.2M   data/legal
30M    data/wildfire
```

`data/*/raw/` 被 gitignore 掉了，所以**磁盘上的文件数不会等于 1764**。

**⚠️ 子任务数有漂移。** 实测六个 workload 文件：
`71 + 68 + 38 + 148 + 186 + 120 = 631`（README 写 633，Legal 写 188 而实测 **186**）——
README 之后改过 legal（最新 commit 就是 `Updates to legal-hard-29`）。
**别把 1764 / 633 硬编码。**

实测文件数与格式分布（`data/<域>/input/` 递归）：

| 域 | 磁盘文件数 |
| --- | ---: |
| archeology | 5 |
| astronomy | **1 538** |
| biomedical | 8 |
| environment | 37 |
| legal | 132 |
| wildfire | 22 |

扩展名分布（全六域合计）：

| 扩展名 | 数 |
| --- | ---: |
| `.csv` | 1 626 |
| `.sp3` | 37 |
| `.hdr` | 37 |
| `.txt` | 18 |
| `.xlsx` | 10 |
| `.dat` / `.tle` / `.lst` / `.gpkg` | 各 2 |
| `.npz` / `.cdf` / `.text` / `.html` / `.py` / `.json` | 各 1 |

**天文域目录与实测文件数不一致的原因**：上游 baseline（DS-GURU）的
`process_dataset` 用**非递归** `os.listdir`，看不到
`data/astronomy/input/STORM-AI/warmup/v2/GOES/` 里的文件 ——
天文域会从 1538 个文件变成 10 个。**递归是你自己的责任。**

**`answer_type` 分布**（实测，任务级）：

| 域 | answer_type |
| --- | --- |
| archeology | `numeric_exact` ×10、`string_exact` ×2 |
| astronomy | `numeric_exact` ×8、`list_approximate` ×2、`string_approximate` ×1、`list_exact` ×1 |
| biomedical | `numeric_exact` ×6、`list_exact` ×2、`string_exact` ×1 |
| environment | `numeric_exact` ×11、`string_exact` ×4、`list_exact` ×3、`string_approximate` ×2 |
| legal | `numeric_exact` ×15、`string_exact` ×8、`string_approximate` ×3、`list_exact` ×3、`numeric_approximate` ×1 |
| wildfire | `string_exact` ×5、`numeric_approximate` ×5、`numeric_exact` ×4、`string_approximate` ×4、`list_exact` ×3 |

## 布局

```
KramaBench/
├── benchmark/                    # 评测器代码
│   ├── evaluator.py
│   ├── executor.py
│   ├── metrics.py
│   └── fixtures/
│       ├── answer_type_fixtures.json      # answer_type → 指标，写死在这里
│       ├── input_type_fixtures.json
│       ├── output_type_fixtures.json
│       └── task_fixtures.json
├── data/
│   └── <域>/input/<原始文件>       # 数据湖（⚠️ 域目录名是 archeology，见下）
├── dr-input/<域>/<域>-<难度>-<n>/  # 每任务的 oracle 文件子集（truth subset）
├── experts/                      # ⚠️ 上游 README 的结构清单里漏了这个
├── quickstart/
├── scripts/
├── solutions/<域>/<任务 id>.py     # 参考解，全是可运行的 Python
├── systems/                      # 各 baseline 系统
├── tests/                        # ⚠️ README 的结构清单里也漏了
├── utils/
├── workload/
│   ├── archeology.json
│   ├── astronomy.json
│   ├── biomedical.json
│   ├── environment.json
│   ├── environment-tiny.json     # 带 -tiny 的小样，不参与正式评测
│   ├── legal.json
│   ├── legal-tiny.json
│   └── quick-start-questions.json
├── eval.sh
├── evaluate.py
├── pyproject.toml
└── version.bash
```

目录约定（**上游拼法，勿改**）：

```
data/<域>/input/<原始文件>            —— 数据湖
workload/<域>.json                    —— 任务定义
solutions/<域>/<任务 id>.py           —— 参考解
dr-input/<域>/<域>-<难度>-<n>/        —— 每任务的 oracle 文件子集（truth subset）
```

**⚠️ `results/` 不在上面** —— 它被 gitignore 了，是跑评测时才生成的。
上游 README 的结构清单却列了它，同时漏了实际存在的
`dr-input/`、`experts/`、`solutions/`、`tests/`。

**⚠️ `data/*/raw/` 也被 gitignore**，所以 checkout 里看不到 raw 目录。

## 任务结构

`workload/<域>.json` 是一个 JSON 数组，每个元素是
`{id, query, answer, answer_type, runtime, data_sources, subtasks[]}`。
实测 wildfire 的任务键：`answer, answer_type, data_sources, deepresearch_subset, id, query, runtime, subtasks`；
子任务键：`answer, answer_type, data_sources, id, query, step`。

任务 id 形如 `legal-hard-1`，子任务 `legal-hard-1-1`。

**⚠️ id 里的编号不连续。** 实测 legal 的前 12 个：
`legal-hard-1`、`legal-hard-2`、`legal-easy-3`、`legal-easy-4`、`legal-easy-5`、
`legal-hard-6`、`legal-hard-7`、`legal-hard-8`、`legal-easy-9`、`legal-easy-10`、
`legal-easy-11`、`legal-easy-12` —— 难度是**跳变的**，不要假设连续序列。

**⚠️ `data_sources` 类型不稳定。** 实测：任务层 **104 / 104 全是 list**；
子任务层 **557 个 list、71 个是裸字符串、3 个是 `null`**。
裸字符串集中在 archeology。
**严格 schema 会在这里崩。**

**⚠️ `runtime` 全是 `1`**（实测六个域的所有任务）—— 不要把它当成真实时限去用。

`deepresearch_subset` 字段在**全部 104 个任务**上都存在（实测 12/12、12/12、9/9、
20/20、30/30、21/21）。上游用它标出「深研子集」的题，做分层评测时用得上。

## 指标

`answer_type` → 指标的映射**写死在 `benchmark/fixtures/answer_type_fixtures.json`** 里
（实测就是下面六条，`metrics` 是列表）：

| answer_type | 指标 | 说明 |
| --- | --- | --- |
| `numeric_exact` | `success` | 数值精确：**相对误差 1e-6 或绝对 1e-4** 以内算对 |
| `string_exact` | `success` | 字符串精确（**大小写不敏感**） |
| `numeric_approximate` | `mean_absolute_error` / `mean_squared_error` / `rae_score` | 数值近似 |
| `string_approximate` | `llm_paraphrase` | 字符串近似：**调 LLM 判断是否同义（要钱、不确定）** |
| `list_exact` | `f1` / `precision` / `recall` | 列表精确：集合 F1 |
| `list_approximate` | `f1_approximate` | 列表近似：**逐对调 LLM 判断** |

**除答案外，`evaluator.py` 还会调 `llm_code_eval` 给流水线本身打分**
（`pipeline_evaluation_engine`），最后取平均。
所以**有两个读数，别只看答案准确率**。

Knosis 侧注册的读数：

| key | 说明 |
| --- | --- |
| `answer_*` | 按上表逐条展开（`answer_success`、`answer_f1`、`answer_mean_absolute_error` …） |
| `pipeline_design` | 流水线设计分（`llm_code_eval`）—— 与答案对错独立的一路读数 |
| `pipeline_implementation` | 流水线实现分（`llm_code_eval` 的可执行性/正确性） |
| `overall` | 答案分与流水线分的聚合（上游 `evaluate.py::aggregate_results`） |

上游 README 另提到 **BLEU / ROUGE**（字符串）与 **bootstrapped rubric**（给部分分），
以及 `benchmark/fixtures/task_fixtures.json` 里的任务类型
（`extraction` / `calculation` / `prediction` / `summarization` / `complex_qa` / `explanation`）。
注意 `--skip_subtasks` 可以只评最终答案（快，但信息少）。

**⚠️ `eval.sh --use_truth_subset` 走 `dr-input/` 那条路，
但这个 flag 在上游 README 的参数表里根本没写。**
`eval.sh` 里还硬编码了 conda 环境名 `smol311` 与一个 SUT 名，用前必须改。

## 已知问题

- **上游目录名是 `archeology`（拼错的，少一个 a）** —— 已核实
  `data/`、`solutions/`、`dr-input/`、`workload/` 四处都用这个拼法。
  **那是路径的一部分，不要改。**
- 同理 `environment` 是「环境」，不是 `environmental`。
- **HF 数据集卡片基本是空的**，内容只有 front-matter 那两行，没有任何说明。
- **上游 baseline（DS-GURU）的 `process_dataset` 用非递归 `os.listdir`**
  —— 见「体量」一节，天文域会从 1538 个文件变成 10 个。**递归是你自己的责任。**
- **`evaluate.py` 会往仓库里写 `results/`，只读安装会被污染。**
- **上游 README 的结构清单是错的**：它列了 `results`（其实被 gitignore），
  却漏了实际存在的 `dr-input/`、`experts/`、`solutions/`、`tests/`。
- **上游 repo 自己的 citation block 引的标题是错的**（引成了别的名字），
  以 arXiv 标题为准。
- **上游 leaderboard 最好成绩约 22%，而论文 55%** ——
  两者检索/评测配置不同，**不可直接横比**。
  （README 里的 leaderboard 表硬编码了 GPT-o3 / GPT-4o / Claude-3.5 /
  Llama-3 Instruct / DeepSeek-R1 / Qwen-2 Coder 的分数，`DS-GURU (self-correcting)`
  的 GPT-o3 那行最高，**整体 22.08 %**。）
- **没有 PyPI 包**，只能从 checkout 装（`pip install .` / `pip install ".[baselines]"`）。
  `pyproject.toml` 里 `version = "1.0.0.dev0"`，依赖 `requires-python = ">=3.10"`。
- **`workload/*obscured*` 与 `data/*obscured*` 被 gitignore** ——
  上游有「遮蔽版」workload 与数据集，本地不会看到。
- **数据湖里混着可执行脚本**（实测 wildfire 下有 `load_data.py`、`.html`），
  扫文件时注意别把上游的辅助脚本当成数据文件。
- **`.sp3` / `.hdr` / `.tle` / `.gpkg` / `.cdf` / `.npz` 这些格式占了天文域的大头**
  —— 光靠 pandas 读不动，预案里要留出解析时间。
