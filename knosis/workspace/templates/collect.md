# 从最近的 agent 会话收集知识

知识库：`$kb`（当前目录，git 仓库；现有 $n_units 条 κ；知识体系大纲：$outline）。
下面 $n 个会话的轨迹已统一成步骤序列，放在 `evidence/traces/`（`.md` 便于阅读，`.jsonl` 每行一步，`step` 是步号）：

$listing

## 任务

从这些会话里提取**以后的 agent 会用得上、并且能被环境证据反驳的知识**，写进本知识库：

- 关于环境的结论：项目 / 仓库的结构与约定、数据的特点与坑、工具和命令的实际行为、服务器与环境配置、报错的原因与解决办法；
- `scope=method`（元知识）：如何发现或验证某类知识的步骤；
- skill（`kb/skills/<名字>/SKILL.md`，格式见已有 skill 或 `knosis` 的说明）：遇到某类任务怎样用这些知识去解，只在有清楚的可复用流程时写。

不要记：用户偏好与对话记忆（这不是知识，不能被环境反驳）、一次性的具体任务答案、闲聊、密钥与口令。
会话里 agent 说的话是它的说法，不等于事实；轨迹里有命令输出能直接支持的，记一条证据，否则保持 `inferred`。
会话之间没有东西值得记时，可以一条都不加。

## 写法

1. 先看已有知识，避免重复：`knosis knowledge outline --ws .`、`knosis knowledge select --ws . --text <关键词>`。
   - 与已有单元说的是同一件事：不新增，给它记一条支持证据；
   - 与已有单元矛盾：记一条反驳证据，把它改为 `contested`（或在确定时 `retracted`），新知识照常写并在 `condition` 里说明。
2. 新单元写进 `kb/knowledge/units.jsonl`（每行一个 JSON）：`id`（形如 `collect/<主题>-<短描述>`，全库唯一）、`content`、
   `form`（finding / fact / rule / formula / schema / tool / procedure）、`status`（observed / inferred / verified）、
   `scope`（对象知识 instance / relation / dataset，元知识 method / usage）、`provenance`、`condition`（适用范围：哪个项目、目录、工具版本等）。
   `provenance` 写到轨迹步骤：`evidence/traces/<会话 id>.jsonl#step/<n>`，多处用 ` ; ` 连接。
3. 证据：`knosis knowledge evidence add --ws . --unit <id> --verdict support|refute --method data --source evidence/traces/<会话 id>.jsonl#step/<n> --note "<依据>"`。
   `verified` 至少要有一条支持证据。
4. 只改 `kb/knowledge/units.jsonl`、`evidence/ledger.jsonl`（用命令写）、`kb/skills/`；不改 `evidence/traces/`、`collected.jsonl`、`kb/outline.yaml`（之后由内化步骤统一去重、处理矛盾、整理大纲）。

## 验收

`knosis knowledge check --ws .` 不新增问题；每条新单元的 `provenance` 引用了本次 `evidence/traces/` 里的会话。
最后用两三句话说明记了什么、跳过了什么。
