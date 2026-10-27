# AlphaBench — generating / evaluating / searching quantitative factors

## Source

City University of Hong Kong (CityU-MLO / Chen Liu's group).
**AlphaBench: Benchmarking Large Language Models in Formulaic Alpha Factor Mining**,
ICLR 2026. **There is no arXiv preprint.** OpenReview `d97Q8r7ZKZ`.
Repository https://github.com/CityU-MLO/AlphaBench ; website https://alphabench.cc/

Get it: `knosis download alphabench` (`git clone`).
Install: `pip install -e .` inside the repository, which installs a `ppo` command; `ppo start backend` starts the local API (127.0.0.1:19777).

**⚠️ This benchmark ships without market data.** The repository's `benchmark/data/` has only two subdirectories, `evaluate/` and `generate/`
(raw IC tables, factor pools), plus a `factor_cache.sqlite`.
**There is no Qlib-format `.bin` data package**, and no OHLCV CSV either.
You have to download market data yourself:
```bash
pip install pyqlib
python -m qlib.run.get_data qlib_data --target_dir data/alphabench/qlib_data/cn_data --region cn
```

**License: code is MIT** (LICENSE at the repository root).
**⚠️ Upstream has never declared a license for the market data itself**: MIT covers only the code and the protocol.

Size: the number of tasks and questions differs across secondary sources (687 / 1170 / 27 instructions and other counts);
**the repository README is authoritative**. Market coverage: CSI300 / CSI500 / CSI1000 / SP500 (plus NASDAQ100 via the Assay engine).
Date range: daily, CSI300 roughly 2020–2025 (per the paper).

LLM access needs `DEEPSEEK_API_KEY` and/or `OPENAI_API_KEY` (environment variables or `config/api_keys.yaml`).

## Description

What AlphaBench tests: **whether an LLM can mine quantitative factors.**

Four task types:
- **generation** factor generation: given a market and a semantic description, produce a factor expression.
- **evaluation** factor evaluation: given a factor, predict its performance.
- **search** factor search: iteratively find a set of good factors (multi-round).
- **atomic** atomic evaluation: atomic-level evaluation of the effect of a single operator. **This was added after the paper**,
  so the paper's numbers no longer fully match the repository's capabilities.

**Factor expressions use a DSL**, with variables such as `$open` / `$high` / `$low` / `$close` / `$volume`.
(Whether an `amount` field exists **could not be confirmed from upstream**; do not assume it does.)
Preset baseline factors are in `factors/lib/alpha158/` (Alpha158, 158 ready-made factors) and `factors/registry/`.

**⚠️ This benchmark has no bundled dataset.** Its "data" is two things:
1. task definitions and factor pools (in the repository);
2. market data, **which you must download yourself with Qlib**; Knosis reads `data/alphabench/qlib_data/{cn,us}_data` by default (`ds.files["qlib"]`).
So Knosis reads only the task data in the repository, and the market data directory is passed in via `qlib_dir=`. **Do not expect `knosis download` to download market data for you.**

The backtest engine is switchable: **Qlib** by default (in-process); set `FFO_ENGINE=assay` +
`FFO_ASSAY_URL` to switch to **Assay** (which upstream claims is point-in-time correct).

Metrics: IC, RankIC, ICIR, win rate, skewness, annualized return.
The evaluation task additionally uses NDCG@K, Precision@K, MAE, RMSE.

Good for: factor mining, knowledge injection for time-series / panel data, evaluating LLMs' numeric intuition.
Not good for: use as a ready-made market dataset; it does not provide market data.

Pitfalls:
- **Market data must be downloaded yourself**, and **Qlib prices are adjusted** (each stock's first trading day is normalized to 1).
- **`region cn` and `region us` silently change the backtest conventions**: the trading unit (100 shares vs 1 share)
  and the price-limit threshold (0.099 vs none) both differ. This is the most common source of wrong backtest results.
- **Handling of trading halts / price limits and look-ahead bias are risks inherent to Qlib**, not discussed in the upstream README.
- The repository's coverage already goes beyond the ICLR paper (more markets, the atomic task, the Assay engine),
  so **the paper's numbers do not necessarily match numbers produced by the repository**.
- Question counts in secondary sources contradict each other; **do not cite them**; the repository is authoritative.

## Knosis workspace

Only the `evaluate` scenario (upstream T2) is supported: `knosis ws init alphabench evaluate [-o start=2021-01-01 -o end=2025-06-30]`.
Questions are expressions from the factor pool; you deliver predicted signal / mean_ic / mean_rankic / 1–5 dimension scores, and the GT is computed on the fly from the local IC / RankIC ground-truth tables following the upstream convention;
the workspace provides only the market panel before the start of the evaluation window (from the local Qlib cn_data).
`generate` (T1) needs Qlib to compute the IC of new factors on the fly; Qlib is not installed locally, so it is not supported for now; currently only CSI300 (cn_data) is available.
