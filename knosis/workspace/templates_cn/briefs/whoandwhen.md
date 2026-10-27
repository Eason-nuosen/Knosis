# Who&When — 多 agent 系统的失败归因（$scenario）

## 数据是什么

每道题是一条**已经失败**的多 agent 系统运行日志（任务来自 GAIA 与 AssistantBench）：`data/traces/<id>.json` 是 ATIF 轨迹，
`data/traces/<id>.md` 便于阅读，`## step <n>` 是步号，步骤标题上是说话的 agent。两类系统：
CaptainAgent 自动生成的专家组（`ag-*`，$n_algorithm 条；`Computer_terminal` 是执行代码的终端，也算一个 agent，
各 agent 的系统提示在 `.json` 的 `extra.knosis.agents`）与人工搭建的 Magentic-One（`hc-*`，$n_hand 条；
Orchestrator 调度 WebSurfer、FileSurfer、Assistant、ComputerTerminal）。
$answer_note

## 下游任务是什么

对每条日志指出**造成失败的 agent** 和**决定性的出错步骤**（关键错误发生的那一步；之后的错误往往是它的后果）。
`tasks/dev.jsonl` 有 $n_dev 条开发日志，测试日志（$n_test 条）在 decide 阶段给出；每条题目有 `question`、`trace`、
`agents`（日志里出现的 agent）与 `n_steps`。

交付 `predictions.jsonl`，每行：

```json
{"id": "hc-12", "answer": {"agent": "WebSurfer", "step": 13, "reason": "点进了无关网页，之后的检索都偏了"}}
```

`step` 是 `.md` 里的步号（从 1 起）。指标：agent 判对的比例、步骤判对的比例（与上游一致，二者分别计）。
步骤级的判断很难（论文里最好的方法约 14%），agent 级约 54%；随机猜的期望准确率见评测报告的参照。

## 知识应该服务什么

让没见过的失败日志也归因得对：各类 agent 典型的出错方式（检索走偏、没核实就下结论、代码没处理边界、过早终止等）、
怎样从后果倒推到第一处关键错误、哪些步骤只是转述或执行而不该被归咎、两类系统各自的日志结构。
知识应当可复用，不应缓存具体日志的答案；dev 反馈里的标注只用来检验和修正这些规律。
