# Knosis

> Knosis = knowledge + gnosis。**给 agent 用的知识底座：收集、管理、再利用 agent 的知识。**

Knosis 本身不是 agent。它让 Codex / Claude Code 这类编码 agent 把做事过程中学到的东西写成**显式知识**：
每条知识都有来源、成立条件和证据，可以检查、追溯、撤回；下次做事时再按需取用。

两类场景，同一套知识层：

- **个人 agent**：从你日常的 Codex / Claude Code 会话里收集知识，整理成个人知识库，新会话通过 MCP 取用。
- **任务 / 企业数据**：在具体任务上（benchmark、业务数据）让 agent 边探索边累积知识，经证据验证后写回知识库，
  可继承到同类新任务。

## 核心概念

- **知识单元 κ**：一条知识 = 内容、形式（fact / rule / formula / procedure …）、成立条件、来源、状态
  （observed → inferred → verified，或 contested / retracted / stale / merged）。存在 `kb/knowledge/units.jsonl`。
- **证据**：支持或反驳某条知识的记录（可执行检查、工具输出、dev 反馈、轨迹步骤），存在 `evidence/`。状态必须与证据一致。
- **内化**：知识多了以后由 agent 去重、处理矛盾、整理成知识体系（大纲、知识图谱、流程图），太多时再压缩；
  每一步 Knosis 都检查、不通过就回滚，并留下操作记录。
- **工作区**：一个任务的完整流程 explore → extract → refine（用 dev 反馈修正）→ decide，每阶段验收并提交 git；
  标准答案不进工作区。

知识库与工作区用同一个布局（`kb/` + `evidence/`），都是本地 git 仓库，每次写回一个版本，可回退。

## 安装

```bash
pip install -e '.[all]'          # Python 3.10+；或 conda env create -f environment.yml
pytest -q
```

需要一个编码 agent：[Codex CLI](https://github.com/openai/codex) 或 [Claude Code](https://claude.com/claude-code)，两者都已实测。

## 上手：个人知识库

不需要任何数据集。

```bash
knosis kb init ~/kb                                  # 建库
knosis install --kb ~/kb                             # 把 skill 与 MCP 服务装进 Codex；Claude Code 会打印一条 claude mcp add 命令

# 照常用 agent 干活；新会话里 agent 先看知识体系，再按任务检索

knosis kb collect --kb ~/kb --since 1d --dry-run     # 看会收集哪些会话
knosis kb collect --kb ~/kb --since 1d               # 提取知识 → 验收 → 内化 → 提交一个版本（--source claude 收 Claude Code 会话）

knosis knowledge outline --ws ~/kb                   # 看知识体系
knosis knowledge select  --ws ~/kb --text <关键词>    # 检索
knosis knowledge trace <id> --ws ~/kb                # 一条知识的来源与证据
```

只收集能被环境验证或反驳的知识（项目约定、数据的坑、工具的实际行为、报错与解决办法、可复用的方法），
不收集偏好和闲聊。会话原文会复制进知识库供追溯，所以**知识库不要推到公开远端**。

## 上手：任务工作区

```bash
knosis ws init tabarena houses --out ws/houses       # 从数据集导出一个工作区（数据入口见下）

# 驱动模式：Knosis 启动 agent 跑完各阶段，每阶段验收，不过重试一次
knosis ws run ws/houses --agent codex --stage explore extract refine decide --rounds 2 --consolidate
knosis ws run ws/houses --agent claude --model <模型> --effort medium ...    # 换成 Claude Code

# 嵌入模式：直接在 agent 里打开工作区，agent 读 AGENTS.md 自己推进
knosis install

knosis eval ws/houses                                # 评测，写 .knosis/eval.json
knosis ws fork ws/houses --out ws/houses-none --knowledge none   # 对照：不给知识 / K_0 / K_final
```

标准答案只在评测时读取，测试题直到 decide 才生成，反馈只接受 dev 题。这是软隔离，不是安全边界：
正式评测请把原始数据目录放在 agent 环境之外。

## 管理知识

```bash
knosis knowledge check       --ws <dir>                    # 结构、来源、状态与证据一致性
knosis knowledge consolidate --ws <dir>                    # 去重 → 矛盾处理 → 构建知识体系 → 结构化
knosis knowledge compact     --ws <dir> [--topic <主题>]    # 知识太多时压缩：agent 自己判断，或只压缩某个主题
knosis mcp --ws <dir>                                      # 以 MCP 暴露知识层与工具（16 个工具）
```

被合并、被压缩的知识不会删除，而是作为别名指向保留下来的那条；撤回一条知识后，由它推出的知识也必须改为失效（检查会报出）。

## 数据入口与工具

13 个数据入口：ngdbench、tabarena、relbench、bibench、kramabench、burr、llm-srbench、newtonbench、alphabench、
spreadsheetbench、whoandwhen，以及不带题目的 text（文档语料）与 traces（agent 轨迹）。
场景、指标与已知限制见 [docs/datasets.md](docs/datasets.md)。

工具（`knosis tool list`）：sql、profile、joins、fit、sheet、newton、tabpfn、autoschemakg（文本 → 知识图谱）、ultra。
工具只产出待验证的知识，不改数据。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/knowledge.md](docs/knowledge.md) | 知识格式、状态与证据、内化与压缩的规则 |
| [docs/interfaces.md](docs/interfaces.md) | 工具、skill、MCP 的分工与接入方式 |
| [docs/datasets.md](docs/datasets.md) | 数据入口、指标、Python 接口 |
| [docs/demos.md](docs/demos.md) | 各数据集上的演示与结果 |
| [docs/scope.md](docs/scope.md) | 范围与定位 |
| [docs/extending.md](docs/extending.md) | 新增数据集、评测或工具 |
| [docs/design.md](docs/design.md) | 设计背景（四层架构：数据 / 知识 / 工具 / 决策） |

## 许可

代码 Apache-2.0。数据集与模型权重各有许可，见 `datacards/` 与各工具的 `TOOL.md`；Knosis 不分发数据或权重。
