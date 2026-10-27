# AlphaBench

| Item | Value |
| --- | --- |
| Paper | AlphaBench: Benchmarking Large Language Models in Formulaic Alpha Factor Mining |
| Venue | **ICLR 2026**; **no arXiv preprint**; OpenReview `d97Q8r7ZKZ` |
| Authors | City University of Hong Kong (CityU-MLO / Chen Liu's group) |
| Code | https://github.com/CityU-MLO/AlphaBench |
| Website | https://alphabench.cc/ |
| Data | **Not shipped with the repo**: market data must be downloaded via Qlib (see below) |
| Access | Public (git clone); **market data obtained separately** |
| **License** | **Code MIT** (`LICENSE` at the repo root) / **license of the market data itself never stated upstream** |
| Upstream version | No version number; the repo goes beyond the ICLR paper (more markets, the `atomic` task, the Assay engine) |

## License

- **Code: MIT.** There is a `LICENSE` at the repo root.
- **⚠️ The license of the market data itself is never stated upstream.** MIT covers only the code and protocol,
  **not the market data you download from Qlib**. Check the terms of your market data source before publishing factor performance.

## Obtaining

```bash
knosis download alphabench     # git clone the upstream repo
```

Upstream installation:

```bash
pip install -e .          # installs a `ppo` command
ppo start backend         # starts a local API at 127.0.0.1:19777
```

**⚠️ This benchmark ships no market data.** In the repo, `benchmark/data/` has only two subdirectories,
`evaluate/` and `generate/` (raw IC tables, factor pool), plus a `factor_cache.sqlite`.
**There is no Qlib-format `.bin` bundle** and no OHLCV CSV. Download market data yourself:

```bash
pip install pyqlib
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

**`knosis download` does not fetch market data**; it only clones the repo.
Pass the market data directory via `load_dataset("alphabench", qlib_dir=...)`
(Knosis default: `data/alphabench/qlib_data/{region}_data`; Qlib's own default is `~/.qlib/qlib_data/`).

**⚠️ Qlib's official `get_data` data ends in 2020** (cn ends 2020-09-25, us ends 2020-11-10),
so it does not cover AlphaBench's 2020–2025 range, and the cn bundle has no csi1000 constituents. Local data in use:
- `cn_data`: the community dataset [chenditc/investment_data](https://github.com/chenditc/investment_data)
  `qlib_bin.tar.gz` (from 2000-01, updated daily; includes csi300/500/800/1000), extracted with `--strip-components=1`;
- `us_data`: Qlib's official `qlib_data_us_1d_latest.zip` (up to 2020-11, includes sp500 / nasdaq100).

**LLM access needs a key**: `DEEPSEEK_API_KEY` and/or `OPENAI_API_KEY`,
set as environment variables or written to `config/api_keys.yaml`.

## Size

| Item | Value |
| --- | --- |
| Markets | CSI300 / CSI500 / CSI1000 / SP500 (plus NASDAQ100, Assay engine only) |
| Date range | Daily, CSI300 about **2020–2025** (per the paper) |
| Built-in factors | `factors/lib/alpha158/` (Alpha158, **158 ready-made factors**) and `factors/registry/` |
| Market data | **Not in the repo** (see above) |

**⚠️ Do not cite task or question counts from secondary sources.** They disagree with each other
(**687 / 1170 / 27 instructions** and other conflicting figures); **the repo README is authoritative**.

Markets (Knosis `MARKETS`; the region changes the Qlib backtest conventions):

| key | region | Name |
| --- | --- | --- |
| `csi300` | `cn` | CSI 300 |
| `csi500` | `cn` | CSI 500 |
| `csi1000` | `cn` | CSI 1000 |
| `sp500` | `us` | S&P 500 |
| `nasdaq100` | `us` | NASDAQ 100 (**Assay engine only**) |

Upstream task types:

| key | Meaning |
| --- | --- |
| `generation` | Factor generation: given a market and a semantic description, produce a factor expression |
| `evaluation` | Factor evaluation: given a factor, predict its performance (IC etc.) |
| `search` | Factor search: iteratively find a set of good factors |
| `atomic` | Atomic evaluation: atomic-level evaluation of the effect of a single operator (**not in the paper**) |

## Layout

```
AlphaBench/
├── LICENSE
├── benchmark/
│   └── data/
│       ├── evaluate/          # raw IC tables etc.
│       └── generate/          # factor pool / generation tasks
├── factors/
│   ├── lib/
│   │   └── alpha158/          # Alpha158: 158 built-in baseline factors
│   └── registry/              # factor registry
├── config/
│   └── api_keys.yaml          # LLM keys (alternative: environment variables)
└── factor_cache.sqlite        # factor cache
```

**⚠️ The upstream repo has no `qlib_data/`.** Download market data yourself into `data/alphabench/qlib_data/{cn,us}_data`; the repo has neither a `.bin` bundle nor OHLCV CSVs.

Factor DSL variables (upstream):

| Variable | Meaning | Unit |
| --- | --- | --- |
| `$open` | Open price (**adjusted**) | CNY/USD |
| `$high` | High price (**adjusted**) | CNY/USD |
| `$low` | Low price (**adjusted**) | CNY/USD |
| `$close` | Close price (**adjusted**) | CNY/USD |
| `$volume` | Volume | shares |

**⚠️ Whether an `amount` field exists could not be confirmed upstream; do not assume it does.**

## How Knosis uses it

Loader (`knosis/data/loaders/alphabench.py`), scenarios `generate` and `evaluate` (omitted: both):

- `generate`: one task per instruction in `benchmark/data/generate/T*.json`
  (a "difficulty -> instruction list" mapping, or records whose `factor_gt` becomes the answer).
- `evaluate`: one task per entry of `evaluate/pool/factor_pool.json` (factor name -> expression);
  the answer points to that factor's column in `evaluate/raw/{ic,rankic}_table_{market}.csv`
  when the column exists. The truth tables are not in the repo (`raw/download.txt` only gives a Google Drive link)
  and exist only for csi300 / sp500.

Exporter (`knosis/workspace/exporters/alphabench.py`): **only `evaluate` is supported**
(`generate` needs Qlib to compute IC for new factors). Default evaluation window 2021-01-01 to 2025-06-30;
factors are stratified-sampled Positive / Negative / Noise = 4:4:2 (default 50 dev + 250 test).
The agent gets only market data before the window starts (Qlib `.bin` converted to `data/market.parquet`,
plus `data/<market>_members.csv`); the IC / RankIC truth and in-window data never enter the workspace.

Scorer (`knosis/decision/alphabench.py`), following upstream `benchmark/utils/data_builder/base_eval/stats.py`:
GT is computed from the IC / RankIC truth tables over the window (mean IC, mean RankIC, ICIR,
IC sign-flip rate, win rate, skewness; factors with fewer than 20 observed days count as Noise).
|mean IC| < 0.01 is Noise, otherwise Positive / Negative by sign; the four dimensions
Performance (|ICIR|), Stability (1 - flip rate), WinRate and Skewness get 1-5 by quintile within each signal.
Reported metrics: `signal_accuracy`, `mean_ic_mae` / `mean_ic_spearman`, `mean_rankic_mae` / `mean_rankic_spearman`,
`precision_at_10pct` (top 10% by predicted vs. true mean IC), `<dimension>_accuracy` / `<dimension>_mae`, and `missing`.
The reference is "predict Noise and mean IC = 0 for everything".

**Upstream backtest engine is switchable**: Qlib by default (in-process); setting `FFO_ENGINE=assay` +
`FFO_ASSAY_URL` switches to **Assay** (which upstream claims is point-in-time correct). Knosis does not run either engine.

## Known issues

- **Market data must be downloaded yourself**, and **Qlib prices are adjusted** (each stock's first trading day is normalized to 1).
- **⚠️ `region cn` and `region us` silently change backtest conventions**: trading unit
  (**cn = 100 shares / us = 1 share**) and price-limit threshold (**cn = 0.099 / us = none**) both differ.
  **This is the most common source of wrong backtest results.**
- **Handling of suspensions / price limits and look-ahead bias are inherent Qlib risks**, not discussed in the upstream README.
- **The repo goes beyond the ICLR paper** (more markets, the `atomic` task, the Assay engine),
  so **paper numbers and numbers from the repo may not match**.
- **Question counts in secondary sources contradict each other; do not cite them**; the repo is authoritative.
- **The repo actually has only two task directories**: `benchmark/data/generate/` (`T1_*.json`, mostly "difficulty -> instruction list";
  `T1_Text2Alpha_stability.json` carries `factor_gt`) and `benchmark/data/evaluate/`
  (`pool/factor_pool.json` holds 5861 "factor name -> expression" entries; the IC truth tables are not in the repo,
  `raw/download.txt` only gives a Google Drive link).
- The repo has no checksum manifest to verify against: **record the commit hash after downloading**.
