# AlphaBench

| 项 | 值 |
| --- | --- |
| 论文 | AlphaBench: Benchmarking Large Language Models in Formulaic Alpha Factor Mining |
| 出处 | **ICLR 2026**；**没有 arXiv 预印本**；OpenReview `d97Q8r7ZKZ` |
| 作者 | City University of Hong Kong（CityU-MLO / Chen Liu 组） |
| 代码 | https://github.com/CityU-MLO/AlphaBench |
| 网站 | https://alphabench.cc/ |
| 数据 | **不随仓库提供** —— 行情要自下 Qlib（见下） |
| 访问 | 公开（git clone）；**行情数据另行获取** |
| **许可** | **代码 MIT**（仓库根有 `LICENSE`）/ **行情数据本身的许可上游从未声明** |
| 上游版本 | 未声明版本号；仓库覆盖面已超出 ICLR 论文（多市场、`atomic` 任务、Assay 引擎） |

## 许可

- **代码：MIT。** 仓库根目录有 `LICENSE`。
- **⚠️ 行情数据本身的许可，上游从未声明。** MIT 只覆盖代码与协议，
  **不覆盖你从 Qlib 下下来的行情**。把因子表现对外发布前请自行确认行情来源的条款。

## 获取

```bash
knosis download alphabench     # git clone 上游仓库
```

上游安装方式：

```bash
pip install -e .          # 装出一个 `ppo` 命令
ppo start backend         # 起本地 API，127.0.0.1:19777
```

**⚠️ 本基准不附带行情数据。** 仓库里 `benchmark/data/` 只有 `evaluate/` 与
`generate/` 两个子目录（原始 IC 表、因子池），外加一个 `factor_cache.sqlite`。
**没有 Qlib 格式的 `.bin` 数据包**，也没有 OHLCV 的 CSV。行情要自己下：

```bash
pip install pyqlib
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

**别指望 `knosis download` 帮你把行情下下来**，它只 clone 仓库。
行情目录通过 `load_dataset("alphabench", qlib_dir=...)` 传入
（Knosis 默认 `data/alphabench/qlib_data/{region}_data`；上游 Qlib 自己的默认是 `~/.qlib/qlib_data/`）。

**⚠️ Qlib 官方的 `get_data` 数据只到 2020 年**（cn 截止 2020-09-25，us 截止 2020-11-10），
覆盖不到 AlphaBench 的 2020–2025 区间，cn 版也没有 csi1000 成分。本地实际用的是：
- `cn_data`：社区数据 [chenditc/investment_data](https://github.com/chenditc/investment_data)
  的 `qlib_bin.tar.gz`（2000-01 起，按日更新；含 csi300/500/800/1000），解压时 `--strip-components=1`；
- `us_data`：Qlib 官方 `qlib_data_us_1d_latest.zip`（到 2020-11，含 sp500 / nasdaq100）。

**LLM 访问需要 key**：`DEEPSEEK_API_KEY` 和/或 `OPENAI_API_KEY`，
放在环境变量里，或写进 `config/api_keys.yaml`。

## 体量

| 项 | 值 |
| --- | --- |
| 市场 | CSI300 / CSI500 / CSI1000 / SP500（另有 NASDAQ100，仅 Assay 引擎） |
| 日期范围 | 日频，CSI300 约 **2020–2025**（论文口径） |
| 预置因子 | `factors/lib/alpha158/`（Alpha158，**158 个现成因子**）与 `factors/registry/` |
| 行情 | **不在仓库里**（见上） |

**⚠️ 任务数与题量不要引用二手资料。** 不同二手来源说法不一
（**687 / 1170 / 27 条指令**等各种口径互相矛盾），**以仓库 README 为准**。

市场表（`MARKETS`，区域参数会改变 Qlib 回测口径）：

| key | region | 名称 |
| --- | --- | --- |
| `csi300` | `cn` | 沪深 300 |
| `csi500` | `cn` | 中证 500 |
| `csi1000` | `cn` | 中证 1000 |
| `sp500` | `us` | 标普 500 |
| `nasdaq100` | `us` | 纳斯达克 100（**仅 Assay 引擎**） |

四个任务类型（`TASKS`）：

| key | 含义 |
| --- | --- |
| `generation` | 因子生成：给市场与语义描述，产出因子表达式 |
| `evaluation` | 因子评估：给一个因子，预测它的表现（IC 等） |
| `search` | 因子搜索：迭代式地找出一组好因子 |
| `atomic` | 原子评估：对单个算子的效果做原子级评估（**后于论文发布**） |

## 布局

```
AlphaBench/
├── LICENSE
├── benchmark/
│   └── data/
│       ├── evaluate/          # 原始 IC 表等
│       └── generate/          # 因子池 / 生成任务
├── factors/
│   ├── lib/
│   │   └── alpha158/          # Alpha158：158 个预置基线因子
│   └── registry/              # 因子登记目录
├── config/
│   └── api_keys.yaml          # LLM key（另一条路是环境变量）
└── factor_cache.sqlite        # 因子缓存
```

**⚠️ 上游仓库里没有 `qlib_data/`。** 行情要自己下到 `data/alphabench/qlib_data/{cn,us}_data`， —— 仓库里既没有 `.bin` 数据包，也没有 OHLCV 的 CSV。

因子 DSL 变量（`schema.data.variables`）：

| 变量 | 含义 | 单位 |
| --- | --- | --- |
| `$open` | 开盘价（**复权**） | CNY/USD |
| `$high` | 最高价（**复权**） | CNY/USD |
| `$low` | 最低价（**复权**） | CNY/USD |
| `$close` | 收盘价（**复权**） | CNY/USD |
| `$volume` | 成交量 | shares |

**⚠️ `amount` 字段是否存在未能从上游确认 —— 不要假设有。**
Knosis 的 `variables` 里故意不列它。

## 指标

`MetricSuite("alphabench")` 注册的读数：

| key | 方向 | 说明 |
| --- | --- | --- |
| `ic` | up | 信息系数：因子值与未来收益的截面相关性（Qlib 回算） |
| `rankic` | up | 排序 IC：用秩相关替代皮尔逊相关，对异常值更稳 |
| `icir` | up | IC 的信息比（IC 均值 / IC 标准差）—— 比单看 IC 均值更能反映稳定性 |
| `annualized_return` | up | 年化收益（按 region 的口径回算） |
| `win_rate` | up | 胜率 |
| `skewness` | none | 因子收益的偏度 |
| `ndcg_at_k` | up | 评估任务的 NDCG@K |
| `precision_at_k` | up | 评估任务的 Precision@K |
| `mae` | down | 评估任务的 MAE |
| `rmse` | down | 评估任务的 RMSE |
| `knowledge_constraint_delta` | up | 加上知识约束前后的因子表现差 —— **本基准在 Knosis 里的核心读数** |

**回测引擎可切换**：默认 **Qlib**（进程内）；设 `FFO_ENGINE=assay` +
`FFO_ASSAY_URL` 可换成 **Assay**（上游宣称 point-in-time 正确）。

GT 是 Qlib 回算出来的 IC / RankIC / ICIR / 年化。
上游商品数据里若已带这些回算结果，就作为 target 引用；没有就只登记任务，
让上层自己去跑 Qlib。

## 已知问题

- **行情要自己下**，而且 **Qlib 的价格是复权后的**（每只股票首个交易日归一化为 1）。
- **⚠️ `region cn` 与 `region us` 会静默改变回测口径**：交易单位
  （**cn = 100 股 / us = 1 股**）和涨跌停阈值（**cn = 0.099 / us = 无**）都不同。
  **这是回测结果出错最常见的来源。**
- **停牌 / 涨跌停的处理与前视偏差是 Qlib 固有的风险**，上游 README 里没有讨论。
- **仓库的覆盖面已经超出 ICLR 论文**（多了市场、多了 `atomic` 任务、多了 Assay 引擎），
  所以**论文的数字与仓库跑出来的数字未必对应**。
- **二手资料里的题量数字互相矛盾，不要引用它们**，以仓库为准。
- **仓库里实际只有两个任务目录**：`benchmark/data/generate/`（`T1_*.json`，多数是「难度 → 指令列表」，
  `T1_Text2Alpha_stability.json` 带 `factor_gt`）与 `benchmark/data/evaluate/`
  （`pool/factor_pool.json` 是 5861 个「因子名 → 表达式」；IC 真值表不在仓库里，
  `raw/download.txt` 只给了一个 Google Drive 链接）。
- 仓库里没有 OCR/校验和清单可对：**取数后建议自己记 commit hash**。
