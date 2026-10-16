# AlphaBench — 因子评估（$universe）

## 数据是什么

`data/market.parquet`：$universe 历史成分股的日频行情面板（列 `datetime`、`instrument` 及 Qlib 字段，
如 open / high / low / close / volume / vwap / amount / factor / change），只到 **$start 之前**。
价格是 Qlib 复权价。`data/${universe}_members.csv`：每只股票进出该指数的区间（截断在 $start 之前）。
行情可能含噪声（停牌、缺失、异常值等）；哪些是噪声、如何处理，由你判断。

## 下游任务是什么

每道题给一个因子（`factor` 名与 `expression`，Qlib 风格 DSL），预测它在 **$start 至 $end**
（不提供该区间的行情）的表现。上游口径：每日在成分股截面上计算因子值与次日收益
`Ref($$close, -1)/$$close - 1` 的 Pearson 相关为 IC、Spearman 相关为 RankIC；
窗口内平均 |IC| < 0.01 为 `Noise`，否则按平均 IC 的符号为 `Positive` / `Negative`。
测试题 $n_test 道（decide 阶段给出），开发题 $n_dev 道在 `tasks/dev.jsonl`。

表达式里出现的算子：$operators

字段：$fields

不在题目里的表达式示例：

$examples

交付 `predictions.jsonl`，每行：

```json
{"id": "factor/<名字>", "answer": {"signal": "Positive", "mean_ic": 0.021, "mean_rankic": 0.03,
 "scores": {"Performance": 4, "Stability": 3, "WinRate": 5, "Skewness": 2}}}
```

`signal` 必填；`mean_ic`、`mean_rankic` 与 `scores`（四个维度在同类因子内的 1–5 分位：
Performance=|ICIR|、Stability=1−IC 符号翻转率、WinRate=IC 与均值同号的天数比例、Skewness=IC 偏度；Noise 全为 1）可选，给了就计分。
评测：signal 准确率、mean_ic / mean_rankic 的 MAE 与 Spearman、按预测 mean_ic 取前 10% 的 Precision、各维度准确率。

## 知识应该服务什么

让未见过的因子也能估得准：算子与字段组合的规律、市场在历史上的特性、因子表现随时间的稳定性等，都可以提取。
知识应当可复用，不应缓存具体题目的答案。
