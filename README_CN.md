# Knosis

> Knosis = knowledge + gnosis。**给 agent 用的知识底座：收集、管理、再利用 agent 的知识。**

[English](https://github.com/Eason-nuosen/Knosis/blob/main/README.md) | 中文

**在线演示**：https://eason-nuosen.github.io/Knosis/

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
pip install knosis               # Python 3.10+
pip install 'knosis[all]'        # 加上各数据集需要的依赖（networkx、h5py、openpyxl、下载工具）
```

需要一个编码 agent：[Codex CLI](https://github.com/openai/codex) 或 [Claude Code](https://claude.com/claude-code)，两者都已实测。
从源码安装：`git clone` 后 `pip install -e '.[all]'`，`pytest -q` 跑测试。

给 agent 的提示、任务说明和数据说明默认是英文，agent 写出的知识也会是英文。设置 `KNOSIS_LANG=zh` 改用中文版
（`knosis/workspace/templates_cn/`、`knosis/data/cards_cn/`），例如 `export KNOSIS_LANG=zh`。

## 上手：个人知识库

不需要任何数据集。

```bash
knosis kb init ~/kb                                  # 建库（一个本地 git 仓库）
knosis install --kb ~/kb                             # 让 Codex / Claude Code 能用它，见下一节

# 照常用 agent 干活；新会话里 agent 先看知识体系，再按任务检索

knosis kb collect --kb ~/kb --since 1d --dry-run     # 看会收集哪些会话
knosis kb collect --kb ~/kb --since 1d               # 提取知识 → 验收 → 内化 → 提交一个版本（--source claude 收 Claude Code 会话）

knosis knowledge outline --ws ~/kb                   # 看知识体系
knosis knowledge select  --ws ~/kb --text <关键词>    # 检索
knosis knowledge trace <id> --ws ~/kb                # 一条知识的来源与证据
```

只收集能被环境验证或反驳的知识（项目约定、数据的坑、工具的实际行为、报错与解决办法、可复用的方法），
不收集偏好和闲聊。会话原文会复制进知识库供追溯，所以**知识库不要推到公开远端**。

## 在 Codex 与 Claude Code 中使用

Knosis 通过两样东西接入 agent：**skill**（告诉 agent 有知识库、什么时候查、怎么写回）和 **MCP 服务**
（`knosis mcp`，让 agent 在会话里直接查询、写入知识，16 个工具）。`knosis install --kb ~/kb` 两样都装：

| | Codex | Claude Code |
| --- | --- | --- |
| skill | 复制到 `~/.codex/skills/knosis/`、`~/.agents/skills/knosis/` | 复制到 `~/.claude/skills/knosis/` |
| MCP | 自动写入 `~/.codex/config.toml`（带标记的一段，可重复执行；已放行调用审批） | 打印一条命令，自己运行一次：`claude mcp add -s user knosis -- <python> -m knosis.cli mcp --ws ~/kb` |
| 只装一方 | `knosis install --codex --kb ~/kb` | `knosis install --claude --kb ~/kb` |

装好后在新会话里，agent 会先看知识体系（`knowledge_outline`），再按任务检索（`knowledge_select`）；
也可以直接对它说"查一下知识库里关于 X 的知识""把这个结论记进知识库"。

**收集**不在会话里自动发生，需要定期运行（可放进 cron）：

```bash
knosis kb collect --kb ~/kb --since 1d                                  # 收集 Codex 会话（~/.codex/sessions）
knosis kb collect --kb ~/kb --since 1d --source claude                  # 收集 Claude Code 会话（~/.claude/projects）
knosis kb collect --kb ~/kb --since 1d --agent claude --model <模型>     # 用 Claude Code 来做提取（默认用 Codex）
```

不装到全局、临时试用 MCP：

```bash
codex exec -c 'mcp_servers.knosis.command="knosis"' -c 'mcp_servers.knosis.args=["mcp","--ws","/abs/path/kb"]' \
  -c 'mcp_servers.knosis.default_tools_approval_mode="approve"' "<任务>"
claude -p "<任务>" --mcp-config '{"mcpServers":{"knosis":{"command":"knosis","args":["mcp","--ws","/abs/path/kb"]}}}' \
  --allowedTools mcp__knosis
```

需要 agent 自动跑的命令（`ws run`、`kb collect`、`knowledge consolidate / compact`）都有 `--agent codex|claude`、
`--model`、`--effort` 三个参数。

## 上手：任务工作区

```bash
knosis ws init tabarena houses --out ws/houses       # 从数据集导出一个工作区（数据入口见下）

# 驱动模式：Knosis 启动 agent 跑完各阶段，每阶段验收，不过重试一次
knosis ws run ws/houses --agent codex --stage explore extract refine decide --rounds 2 --consolidate
knosis ws run ws/houses --agent claude --model <模型> --effort medium ...    # 换成 Claude Code

# 嵌入模式：直接在 agent 里打开工作区（Codex 读 AGENTS.md，Claude Code 读 CLAUDE.md），agent 自己推进
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
knosis knowledge view        --ws <dir>                    # 在浏览器里看知识库（agent 生成的网页）
knosis mcp --ws <dir>                                      # 以 MCP 暴露知识层与工具（16 个工具）
```

被合并、被压缩的知识不会删除，而是作为别名指向保留下来的那条；撤回一条知识后，由它推出的知识也必须改为失效（检查会报出）。

## 知识体系：多种形式的存储与可视化

知识不止是一张清单。内化会把同一批知识单元组织成多种形式，各自回答一个问题，都以文件形式存在知识库里，
每个节点、每条边、每个步骤都引用它来自的知识单元（不新增断言，由 Knosis 检查引用）：

| 形式 | 存储 | 回答什么 | 由谁产生 |
| --- | --- | --- | --- |
| 知识体系大纲（树） | `kb/outline.yaml` | 知识分几块、各讲什么：场景 → 数据间关系 → 具体对象 | agent（organize） |
| 知识图谱（KG） | `kb/graph.json` | 环境里有哪些对象（表、列、变量、概念、工具…），它们是什么关系 | agent（structure） |
| 流程图（flow） | `kb/flows/*.json` | 某类任务按什么步骤做、在哪检查、在哪分支、每步用哪条知识或 skill | agent（structure） |
| 派生图 | 由 `derived_from` / `merged_into` / `superseded_by` 计算 | 哪条知识由哪些推出、并入或替换；撤回沿它向下游传播 | Knosis 计算 |
| 规则与公式卡片 | 由 rule / formula 单元计算 | 每个对象上有哪些规则和公式 | Knosis 计算 |
| 本体（OSI 标准） | `kb/knowledge/ontology/` | 数据的结构化语义：实体、属性、关系、主外键 | agent 或从 BI / 数据库元数据导入 |

多个数据集的知识库可以合成一个（`knosis kb merge --namespace`），再内化出跨数据集的共享实体与共通知识。

查看与可视化：

```bash
knosis knowledge outline --ws <dir>                       # 大纲渲染成 markdown
knosis knowledge graph   --ws <dir>                       # 知识图谱与流程图摘要
knosis knowledge graph   --ws <dir> --entity <实体> --depth 2   # 某个实体周围的子图，边上附引用的知识
knosis knowledge graph   --ws <dir> --view flows|derivation|cards
knosis knowledge view    --ws <dir>                       # agent 写一个自包含网页（view/index.html），在浏览器里打开
knosis knowledge view    --ws <dir> --request "只看订单相关的知识"   # 按你的要求重新生成
```

`knowledge view` 让 agent 读知识库，自己写一个离线可用的 HTML（大纲、知识图谱、流程图、派生图，点开每条知识看内容与证据），
Knosis 检查它不从网络加载资源、没有改动知识，再用浏览器打开；之后再运行直接打开，`--refresh` 重新生成。
agent 通过 MCP 的 `knowledge_outline`、`knowledge_graph` 读取同样的内容。
[在线演示](https://eason-nuosen.github.io/Knosis/)把各数据集上的知识图谱、流程图、派生图、卡片和大纲做成了可交互的网页，
还有多个数据集合成后的知识总图。

## 支持的数据

Knosis 面向**异构数据**：同一套知识层（κ + 证据 + 本体）覆盖下面这些数据形态，每类都有可评测的数据入口与对应工具。

| 数据形态 | 数据入口 | agent 从中得到的知识 | 工具 |
| --- | --- | --- | --- |
| 单表 | tabarena（51 个表格数据集的分类 / 回归） | 列含义、分布与异常、特征与目标的关系、建模经验 | profile、sql、fit、tabpfn |
| 电子表格 | spreadsheetbench（真实 xlsx 上的单元格 / 工作表操作） | 表格结构、公式与操作的实际行为 | sheet（查看结构、LibreOffice 重算公式） |
| 多表 / 关系数据库 | relbench（多表 + 时间切分的预测）、bibench（BI 项目问答）、burr（关系库 → 本体映射） | 主外键与 join、粒度、包含依赖、业务口径；可写成 OSI 本体 | joins、sql、profile |
| 数据湖（多源异构文件） | kramabench（多份格式不一的文件上的数值问答） | 文件之间的对应关系、单位与时间对齐、清洗规则 | 通用表格工具（sql、profile） |
| 图 | ngdbench（大规模属性图问答，含注入噪声的版本） | 节点 / 边类型、属性规律、哪些是噪声 | ultra（只适配接口，需另备 checkpoint） |
| 方程与科学数据 | llm-srbench（数值数据 → 符号公式）、newtonbench（在模拟器里做实验发现物理定律） | 公式、成立范围、实验方法 | newton（模拟器实验）、fit |
| 金融时间序列 | alphabench（A 股行情上的因子评估） | 因子的信号与稳定性判断 | 通用表格工具（sql、profile） |
| 文本 | text（任意文档集合，无题目） | 文中的断言与实体关系，可抽成知识图谱 | autoschemakg（文本 → 知识图谱） |
| agent 轨迹 | traces（Codex / Claude Code 会话、ATIF 等格式）、whoandwhen（多 agent 失败日志）；个人会话由 `kb collect` 收集 | 项目约定、工具与命令的实际行为、出错原因与解决办法 | 统一转成 ATIF 轨迹，知识引用到具体步骤 |

各入口的场景、指标、dev 切分与已知限制见 [docs/datasets.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/datasets.md)；
`knosis list` 列出全部入口，`knosis describe <名字>` 看数据说明，`knosis download <名字>` 取数（数据集不随包分发）。
工具（`knosis tool list`、`knosis tool card <名字>`）只产出待验证的知识，不改数据。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/knowledge.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/knowledge.md) | 知识格式、状态与证据、内化与压缩的规则 |
| [docs/interfaces.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/interfaces.md) | 工具、skill、MCP 的分工与接入方式 |
| [docs/datasets.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/datasets.md) | 数据入口、指标、Python 接口 |
| [docs/demos.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/demos.md) | 各数据集上的演示与结果（网页版见[在线演示](https://eason-nuosen.github.io/Knosis/)） |
| [docs/scope.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/scope.md) | 范围与定位 |
| [docs/extending.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/extending.md) | 新增数据集、评测或工具 |
| [docs/architecture.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/architecture.md) | 架构：四层（数据 / 知识 / 工具 / 决策）与工作区 |

## 许可

代码 Apache-2.0。数据集与模型权重各有许可，见 `datacards/` 与各工具的 `TOOL.md`；Knosis 不分发数据或权重。
