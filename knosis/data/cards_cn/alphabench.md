# AlphaBench —— 量化因子的生成 / 评估 / 搜索

## 来源

City University of Hong Kong（CityU-MLO / Chen Liu 组）。
**AlphaBench: Benchmarking Large Language Models in Formulaic Alpha Factor Mining**，
ICLR 2026。**没有 arXiv 预印本。** OpenReview `d97Q8r7ZKZ`。
仓库 https://github.com/CityU-MLO/AlphaBench ；网站 https://alphabench.cc/

获取：`knosis download alphabench`（`git clone`）。
安装：仓库内 `pip install -e .`，会装出一个 `ppo` 命令；`ppo start backend` 起本地 API（127.0.0.1:19777）。

**⚠️ 本基准不附带行情数据。** 仓库里 `benchmark/data/` 只有 `evaluate/` 和 `generate/`
两个子目录（原始 IC 表、因子池），外加一个 `factor_cache.sqlite`。
**没有 Qlib 格式的 `.bin` 数据包**，也没有 OHLCV 的 CSV。
行情要你自己下：
```bash
pip install pyqlib
python -m qlib.run.get_data qlib_data --target_dir data/alphabench/qlib_data/cn_data --region cn
```

**许可：代码 MIT**（仓库根有 LICENSE）。
**⚠️ 行情数据本身的许可上游从未声明** —— MIT 只覆盖代码与协议。

体量：任务数与题量在不同二手资料里说法不一（有 687 / 1170 / 27 条指令等口径），
**以仓库 README 为准**。市场覆盖 CSI300 / CSI500 / CSI1000 / SP500（另有 NASDAQ100 走 Assay 引擎）。
日期范围：日频，CSI300 约 2020–2025（论文口径）。

LLM 访问需要 `DEEPSEEK_API_KEY` 和/或 `OPENAI_API_KEY`（环境变量或 `config/api_keys.yaml`）。

## 说明

AlphaBench 考的是：**LLM 能不能做量化因子的挖掘。**

四个任务类型：
- **generation** 因子生成 —— 给市场与一段语义描述，产出因子表达式。
- **evaluation** 因子评估 —— 给一个因子，预测它的表现。
- **search** 因子搜索 —— 迭代地找出一组好因子（多轮）。
- **atomic** 原子评估 —— 对单个算子的效果做原子级评估。**这个是后于论文加的**，
  所以论文的数字与仓库的能力已经不完全对应。

**因子表达式用的是 DSL**，变量形如 `$open` / `$high` / `$low` / `$close` / `$volume`。
（`amount` 字段的存在与否**未能从上游确认**，别假设有。）
预置基线因子在 `factors/lib/alpha158/`（Alpha158，158 个现成因子）与 `factors/registry/`。

**⚠️ 这个基准没有自带数据集。** 它的"数据"是两样东西：
1. 任务定义与因子池（在仓库里）；
2. 行情 —— **要你自己用 Qlib 下载**，Knosis 默认读 `data/alphabench/qlib_data/{cn,us}_data`（`ds.files["qlib"]`）。
所以 Knosis 只读仓库里的任务数据，行情目录通过 `qlib_dir=` 传入。**别指望 `knosis download` 帮你把行情下下来。**

回测引擎可切换：默认 **Qlib**（进程内），设 `FFO_ENGINE=assay` +
`FFO_ASSAY_URL` 可换成 **Assay**（上游宣称 point-in-time 正确）。

指标：IC、RankIC、ICIR、胜率、偏度、年化收益。
评估任务另用 NDCG@K、Precision@K、MAE、RMSE。

适合：因子挖掘、时序/面板数据的知识注入、LLM 的数值直觉评测。
不适合：当作现成的行情数据集 —— 它不提供行情。

陷阱：
- **行情要自己下**，而且 **Qlib 的价格是复权后的**（每只股票首个交易日归一化为 1）。
- **`region cn` 与 `region us` 会静默改变回测口径**：交易单位（100 股 vs 1 股）
  和涨跌停阈值（0.099 vs 无）都不同。这是回测结果出错最常见的来源。
- **停牌 / 涨跌停的处理与前视偏差是 Qlib 固有的风险**，上游 README 里没有讨论。
- 仓库的覆盖面已经超出 ICLR 论文（多了市场、多了 atomic 任务、多了 Assay 引擎），
  所以**论文的数字与仓库跑出来的数字未必对应**。
- 二手资料里的题量数字互相矛盾，**不要引用它们**，以仓库为准。

## Knosis 工作区

只支持 `evaluate` 场景（上游 T2）：`knosis ws init alphabench evaluate [-o start=2021-01-01 -o end=2025-06-30]`。
题目是因子池里的表达式，交付预测的 signal / mean_ic / mean_rankic / 1–5 维度分，GT 由本地 IC / RankIC 真值表按上游口径现算；
工作区只给评估窗口开始之前的行情面板（来自本地 Qlib cn_data）。
`generate`（T1）要用 Qlib 现算新因子的 IC，本地未安装 Qlib，暂不支持；目前只有 CSI300（cn_data）。
