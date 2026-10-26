# agent 轨迹（Codex / Claude Code / 普通 agent → 可验证知识的来源）

## 来源

无固定出处，由使用者指向自己的轨迹文件：`knosis ws init traces <名字> -o paths=<文件或 glob，逗号分隔> [-o env=<轨迹当时的数据目录>]`。
Knosis 只读不写原文件。

## 说明

支持的格式（自动识别，见 `knosis.data.traces`）：

- Codex：`~/.codex/sessions/**/rollout-*.jsonl`（已测 CLI 0.147 / 0.149 / 0.160 / 0.163）
- Claude Code：会话 JSONL（`~/.claude/projects/<项目>/<会话>.jsonl`，已测 2.1.x），同名目录下 `subagents/agent-*.jsonl` 作为子 agent
- 逐步记录：`{instruction, steps: [{reasoning, response, code, env_feedback}], success}`，如 agent-rsi 的 AppWorld ReAct 轨迹
- OpenAI 风格 messages（JSON 列表、JSONL，或 `{"messages": [...]}`）
- Who&When 的一条日志（GT 字段不进轨迹）；已经是 ATIF v1.7 的轨迹

统一成 **ATIF v1.7**（Harbor 的 Agent Trajectory Interchange Format），写进工作区 `data/traces/<id>.json`（另有 `.md` 便于阅读）：
一步是一条用户 / 系统消息，或 agent 的一次输出（文本、思考、工具调用），调用结果挂在发出调用的那一步；
Knosis 的补充信息在 `extra.knosis`：来源格式与版本（`tested` 为 false 表示该版本没测过）、每类来源记录映射或跳过的计数、
截断（单段文本超过 4000 字符）、按位置推断的配对（`paired_by`）、多 agent 轨迹里说话的 agent。
知识引用轨迹写 `data/traces/<id>.json#step/<n>`，子 agent 的步骤写 `#agent/<子 agent id>/step/<n>`。
v0.5 之前的步骤序列（`<id>.jsonl`）用 `knosis migrate` 转换，引用的步号一并改写。

**关键约定**

- 轨迹里的话是那个 agent 的说法，不等于事实。只引用轨迹的知识保持 inferred；
  给了 `env` 时可以在 `data/env/` 上复核，复核后记证据（`method` 为 data / check / tool）。
- 不把轨迹里具体题目的答案存成知识；可复用的做法分成 method（如何发现 / 验证）和 skill（如何运用知识解题）。

## 评测

没有任务指标；打分器报告：引用了真实存在步骤的知识占比（`cites_trace`），以及有非轨迹证据支持的占比（`env_verified`）。
迁移收益另做：把提取出的知识合进知识库，再在同一环境的新题上对比 none / K_inherit。
