# Who&When —— 多 agent 系统的失败归因（哪个 agent、哪一步）

## 来源

Zhang et al.，**Which Agent Causes Task Failures and When? On Automated Failure Attribution of LLM Multi-Agent Systems**，
arXiv **2505.00212**，ICML 2025。代码 https://github.com/mingyin1/Agents_Failure_Attribution ；
数据 https://huggingface.co/datasets/Kevin355/Who_and_When （Knosis 用的版本 `59b9fcba1aaed7bbf206b5f4d3c68b8face2f49c`，2026-10-26 下载）。
许可：数据卡未声明（用户 2026-10-26 确认可用）。

获取：`knosis download whoandwhen`（按上面的版本取到 `data/whoandwhen/`），
得到 `data/whoandwhen/Who&When/{Algorithm-Generated,Hand-Crafted}/<n>.json`（约 9 MB；同目录另有两个 parquet，Knosis 不读）。

## 说明

- 184 条失败日志：Algorithm-Generated 126 条（CaptainAgent 自动生成的专家组，AG2 群聊，含各 agent 的系统提示），
  Hand-Crafted 58 条（Magentic-One：Orchestrator、WebSurfer、FileSurfer、Assistant、ComputerTerminal）。任务来自 GAIA 与 AssistantBench。
- 标注（论文作者按标注指南完成）：`mistake_agent`（造成失败的 agent）、`mistake_step`（决定性出错步骤，history 下标，从 0 起）、
  `mistake_reason`（自然语言原因）；另有 `ground_truth` / `groundtruth`（任务标准答案）、`is_correct` / `is_corrected`（全为 false）。
- 轨迹转成 ATIF 时 history 一条一步，步号 = 下标 + 1；Hand-Crafted 的 `human` 是用户步，agent 名取 `role` 去掉括号
  （`Orchestrator (-> WebSurfer)` 记为 Orchestrator，原 role 留在 `extra.knosis.speaker`）；Algorithm-Generated 取 `name`，
  `Computer_terminal` 是执行代码的终端，单独算一个 agent。题目放在 `extra.knosis.task`，不占步号。
- 上述标注与标准答案都不进工作区；`-o answer=true` 时题目里给出标准答案（论文的 with ground truth 设置）。
- 指标：agent-level accuracy、step-level accuracy（分别计）。论文里最好的方法 agent 53.5%、step 14.2%，o1 与 R1 也达不到可用水平。
- scenario：`all`、`algorithm`、`hand`；导出器按日志切分，默认 dev 10 / 测试 30。

## 陷阱

- 2 条 Hand-Crafted 日志的 `mistake_agent` 大小写与日志里的 agent 名不一致：打分忽略大小写。
- 6 条日志的出错步骤上说话的不是标注的 agent。上游原样保留，agent 与步骤分别打分。
  （具体是哪几条、标注规律如何，不写在这里：数据卡 agent 也能读到。）
- 「决定性出错步骤」本身有主观性（论文讨论了标注者分歧，细节待核实），step 级准确率是有噪声的指标。
- 日志里的 agent 有时会说出或猜到正确答案，那是日志内容，不是泄漏。
