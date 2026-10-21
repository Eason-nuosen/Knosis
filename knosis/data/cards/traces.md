# agent 轨迹（Codex / Claude Code / 普通 agent → 可验证知识的来源）

## 来源

无固定出处，由使用者指向自己的轨迹文件：`knosis ws init traces <名字> -o paths=<文件或 glob，逗号分隔> [-o env=<轨迹当时的数据目录>]`。
Knosis 只读不写原文件。

## 说明

支持四种格式（自动识别，见 `knosis.data.traces`）：

- Codex：`~/.codex/sessions/**/rollout-*.jsonl`
- Claude Code：会话 JSONL（`~/.claude/projects/<项目>/<会话>.jsonl`）
- 逐步记录：`{instruction, steps: [{reasoning, response, code, env_feedback}], success}`，如 agent-rsi 的 AppWorld ReAct 轨迹
- OpenAI 风格 messages（JSON 列表、JSONL，或 `{"messages": [...]}`）

统一成步骤序列 `{step, role, kind, name, text}`，写进工作区 `data/traces/<id>.jsonl`（另有 `.md` 便于阅读）。
知识引用轨迹写 `data/traces/<id>.jsonl#step/<n>`。

**关键约定**

- 轨迹里的话是那个 agent 的说法，不等于事实。只引用轨迹的知识保持 inferred；
  给了 `env` 时可以在 `data/env/` 上复核，复核后记证据（`method` 为 data / check / tool）。
- 不把轨迹里具体题目的答案存成知识；可复用的做法分成 method（如何发现 / 验证）和 skill（如何运用知识解题）。

## 评测

没有任务指标；打分器报告：引用了真实存在步骤的知识占比（`cites_trace`），以及有非轨迹证据支持的占比（`env_verified`）。
迁移收益另做：把提取出的知识合进知识库，再在同一环境的新题上对比 none / K_inherit。
