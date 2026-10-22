# 工具、skill、MCP

Knosis 给 agent 的东西分三层，彼此不重叠：

| 层 | 在哪里 | 是什么 | 谁写 | 评价 |
| --- | --- | --- | --- | --- |
| 工具 | `knosis/tools/<name>/{TOOL.md, run.py}` | 独立进程的程序或模型：读数据，产出 inferred / observed 的 κ 注解，不改数据、不改知识层 | Knosis 开发者 | 工具说明里的参考精度（如 joins 在 BI-Bench 上的 P/R） |
| skill | `knowledge/skills/<name>/SKILL.md` | 知识层的一部分：如何运用知识解某类任务（解题集），引用 κ | agent（RSI 中根据反馈补充） | 有没有效（反馈 / 消融证据），不讲对错 |
| MCP | `knosis/mcp.py`，`knosis mcp --ws <dir>` | 协议适配：把知识层操作与工具调用暴露成 MCP 工具，本身不实现功能 | Knosis 开发者 | 无；只保证写入前检查 |

判别：会读数据、产出新注解的是**工具**；描述「先做什么再做什么、用哪些知识」的是 **skill**；
让 agent 不经 shell 就能查询、写入知识层与调用工具的是 **MCP**。研究模型（TabPFN、ULTRA、
AutoSchemaKG 这类）一律做成工具，MCP 只通过 `tool_run` 启动它们，不在 MCP 里重写。

另有 `knosis/workspace/templates/SKILL.md`：这是 Knosis 自己的 agent skill（`knosis install` 装到
Codex / Claude Code），说明怎么用 Knosis，不是知识层里的 skill。

## MCP 服务

```bash
knosis mcp --ws ws/newton        # 工作区；也可以给知识库目录（没有 data/，verify 与 workspace_next 不可用）
```

| 工具 | 作用 |
| --- | --- |
| `knowledge_select` / `knowledge_skills` / `knowledge_index` | 筛选知识（附证据计数）、列 skill、以对象为键的视图 |
| `knowledge_trace` | 一条知识的派生链与证据 |
| `knowledge_outline` | 知识体系大纲（没有大纲时给草稿），见下 |
| `knowledge_add` / `knowledge_update` | 新增 / 修改 κ；写入前用 `check_units` 检查，引入新问题就拒绝并返回问题 |
| `evidence_add` / `knowledge_verify` | 记证据（返回该单元因此需要处理的问题，如被反驳后要改状态）/ 重跑可执行检查 |
| `knowledge_check` | 整个知识层的检查 |
| `tool_list` / `tool_card` / `tool_run` | 列工具、看说明、在工作区根目录运行工具 |
| `workspace_next` | 当前阶段的目标与验收 |

不暴露 `eval`。实现是手写的 stdio JSON-RPC（不依赖 `mcp` 包），每行一条消息，支持
`initialize`、`ping`、`tools/list`、`tools/call`。

接入 Codex（`exec` 非交互模式下 MCP 调用默认需要审批，要对这个服务放行）：

```bash
codex exec -C ws/newton \
  -c 'mcp_servers.knosis.command="knosis"' -c 'mcp_servers.knosis.args=["mcp","--ws","ws/newton"]' \
  -c 'mcp_servers.knosis.default_tools_approval_mode="approve"' "<任务>"
```

接入 Claude Code（未实测）：`claude -p "<任务>" --mcp-config '{"mcpServers":{"knosis":{"command":"knosis","args":["mcp","--ws","ws/newton"]}}}' --allowedTools 'mcp__knosis'`。

## 知识体系（大纲）

知识多了以后，`knowledge/outline.yaml` 把 κ 与 skill 组织成层级：场景（任务与对它有用的 utility、skill）
→ 数据间关系 → 数据本身（整体规律、具体对象），method 单列或挂在场景下。格式见 `knosis/knowledge/outline.py`。

大纲是导航层：每节的 summary 只概括成员单元已经说了的内容，不新增断言，所以不需要证据；
疑似重复或矛盾的单元写在节的 `notes` 里，由人决定是否合并，大纲本身不改单元。
有大纲时 `check_knowledge` 会检查它：引用的单元存在、节 id 不重复、失效单元只在 `archive: true` 的节里。

```bash
knosis knowledge outline --ws ws/x --draft       # 按粒度与锚定文件生成的草稿
knosis knowledge outline --ws ws/x               # 渲染当前大纲（末尾列出还没归类的活跃单元）
knosis knowledge organize --ws ws/x              # 让 Codex 结合已有知识整理出 outline.yaml，验收不过重试一次
knosis knowledge organize --ws ws/x --prompt-only   # 只打印提示词，本会话的 agent 自己整理
```

知识库与工作区的大纲各自独立：`kb merge` 不合并大纲，合并后在知识库上重新 `organize`。
