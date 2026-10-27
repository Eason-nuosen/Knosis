# AlphaBench — factor evaluation ($universe)

## What the data is

`data/market.parquet`: a daily market panel of the historical constituents of $universe (columns `datetime`, `instrument` and Qlib fields
such as open / high / low / close / volume / vwap / amount / factor / change), covering only the period **before $start**.
Prices are Qlib adjusted prices. `data/${universe}_members.csv`: the intervals during which each stock entered and left the index (truncated before $start).
The market data may contain noise (trading halts, missing values, outliers, etc.); what counts as noise and how to handle it is up to you.

## What the downstream task is

Each question gives a factor (`factor` name and `expression`, in a Qlib-style DSL) and asks you to predict its performance over **$start to $end**
(market data for that period is not provided). Upstream convention: each day, over the constituent cross-section, the Pearson correlation between the factor value and the next-day return
`Ref($$close, -1)/$$close - 1` is the IC, and the Spearman correlation is the RankIC;
if the mean |IC| over the window is < 0.01 the factor is `Noise`, otherwise it is `Positive` / `Negative` according to the sign of the mean IC.
There are $n_test test questions (given in the decide stage); $n_dev dev questions are in `tasks/dev.jsonl`.

Operators that appear in the expressions: $operators

Fields: $fields

Example expressions not among the questions:

$examples

Deliver `predictions.jsonl`, one line per question:

```json
{"id": "factor/<name>", "answer": {"signal": "Positive", "mean_ic": 0.021, "mean_rankic": 0.03,
 "scores": {"Performance": 4, "Stability": 3, "WinRate": 5, "Skewness": 2}}}
```

`signal` is required; `mean_ic`, `mean_rankic` and `scores` (1–5 quantile scores within the same factor class on four dimensions:
Performance=|ICIR|, Stability=1−IC sign-flip rate, WinRate=fraction of days on which IC has the same sign as its mean, Skewness=IC skewness; all 1 for Noise) are optional and are scored if given.
Evaluation: signal accuracy, MAE and Spearman of mean_ic / mean_rankic, Precision of the top 10% by predicted mean_ic, and per-dimension accuracy.

## What the knowledge should serve

Make estimates accurate for unseen factors as well: patterns of operator and field combinations, historical characteristics of the market, stability of factor performance over time, and so on can all be extracted.
Knowledge should be reusable; it should not cache answers to specific questions.
