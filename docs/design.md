> 设计背景文档（v0.2 时期的项目计划，原 `Knosis-plan.md`）。当前实现与用法以仓库 README 和 `docs/knowledge.md` 为准；
> 四层的命名在 v0.3 调整为：数据层 / 知识层（含本体子层）/ 工具层 / 决策层。

# Knosis — 开源项目计划

> Knosis = know + gnosis。**面向智能体的知识底座**：把多源数据构造成显式知识（L1），对知识做内化与复杂查询（L2），再把内化后的知识接进 agent 的决策（L3）。
> 对应 position paper 的 knowledge-centric loop：**D（发现）→ T+R（内化）→ U（使用）**。

---

## 0. 现状

| 版本 | 内容 | 状态 |
| --- | --- | --- |
| v0.1 | 统一数据入口 `knosis.load_dataset`：8 个基准 + 文本入口，本地数据齐备 | **已完成** |
| v0.2 | 工作区 + 四阶段编排 + 知识单元格式 + 工具中心框架（ULTRA、TabPFN）；NGD-Fin 与 TabArena 试点 | **已完成** |
| v0.3 | 按四层重组；本体子层（Ossie/EOB）；SQL / 表画像 / join 工具；NGD-Fin 与 TabArena 评测 | **已完成** |
| v0.3+ | refine（RSI）、decide 与评测、L2 `R`、L3 使用通道 | 见 §5 路线 |

---

## 1. 三层设计

知识在三层之间只用一种东西通信：**知识单元 κ = (c, f, C, π, ρ)** —— 内容 / 存储形式 / 条件 / 来源 / 状态。

| 层 | 论文对应 | 一句话职责 |
| --- | --- | --- |
| **L1 Construct** | Discovery `D` | 把多源数据接进来，由 agent 分析、去噪，产出带 `C`、`π` 的知识单元 |
| **L2 Internalize** | `T` + `R` | `T` 改知识层（概念化 / 合并 / 补全 / 修复 / 版本）；`R` 在知识层上回答（多跳 + 聚合 + 排序，返回 `(a, e, u)`） |
| **L3 Decide** | Use `U` | 把知识接进 agent：符号通道（检索 / MCP）、参数通道、非语言 FM 的条件接口 |

三条立场：

- **`C` 与 `π` 在写入时确定**，事后补不回来；原始后端不物化，知识层只存 schema、派生事实与指针。
- **内化不是索引**：`T` 的正确性由 I1–I5 不变量判定（来源不丢 / 独立来源计数 / role-type 兼容 / 条件例外不丢 / 撤回传播）；回答区分 in-graph / inferred / real-world 三类。
- **知识必须可撤回**：注入后撤不回的通道不是一等公民。

---

## 2. 数据基准（v0.1 已接入）

基准在 Knosis 里的角色不是跑分榜，而是**给每层提供不同性质的 ground truth**。

| key | 源类型 | 本地数据 | 规模 | GT 形式 | 主要服务 |
| --- | --- | --- | --- | --- | --- |
| `ngdbench` | 复杂 KG（clean / perturbed 配对） | 5 个域，14.6 GB | 86208 题 | clean 图上的答案；**`noise_info/` 记录了全部注入的噪声** | L1 去噪、L2 `R` |
| `relbench` | 关系数据库（时间切分） | v1 的 7 个库 | 每库若干实体任务 | 标签表（test 切分） | L1 关系库、L3 知识增益 |
| `burr` | 关系库 → 本体 | 4 真实库 + 54 micro | 每场景 1 题 | 人工 DB→本体映射 | L1 schema-as-knowledge |
| `newtonbench` | 方程发现（只有源码） | 12 域 | 每域 27 题 | `laws.py` 里的真值函数 | L1 / L2 方程类知识 |
| `llm-srbench` | 单表 / 符号回归 | 5 个 split，228 MB | 240 题 | 真值表达式（抗记忆构造） | L1 方程类知识 |
| `alphabench` | 时序面板 / 量化因子 | 任务 + IC 真值表 + Qlib 行情 | 6280 题 | `factor_gt`；每日 IC / RankIC 表（CSI300、SP500） | L1 时序、L3 决策 |
| `kramabench` | 多源数据湖 | 6 个域 | 每域约 20 题 | 参考答案 + 参考解代码 | L1 多源、L3 端到端 |
| `tabarena` | 单表（51 个数据集） | 216 MB | 每数据集 30 个官方划分 | 测试行目标值 | L1 单表、L3 非语言 FM（Gap 3） |
| `bibench` | 多表 BI 项目（Power BI） | 100 个用例，约 4 GB（LFS） | 100 题，每例 2–52 张表 | GT 结果表（可有多个等价答案） | L1 多表 / join 知识、L3 端到端分析 |
| `text` | 文本 | 指向本地语料 | — | 无 | L1 文本建图 |

已知限制：

- **AlphaBench 行情**：A 股用社区数据 chenditc/investment_data（到 2026-10，含 CSI300/500/800/1000）；美股只有 Qlib 官方数据（到 2020-11），未找到更新的替代，**暂时只用 A 股**。
- **EHRSHOT 不做**：需签 DUA，获取成本高，已从代码中移除。
- **NGDBench 的 perturbed 图泄漏了噪声答案**（已在 NGD-Fin 上核实）：边属性 `is_noise=True` 标出 11010 条噪声边，被修改的边带 `noise_similarity`（6047 条），新增的边带 `relation`（5497 条）；节点上的 `noise_similarity` / `original_name` 也是加噪痕迹。clean 图的边只有 `label` 一个属性。**交给 agent 前必须只保留 clean 图里有的属性键**，否则去噪评测无效。其他域待核实。
- 指标（`ds.metrics`）只有名字与说明，尚未实现。

---

## 3. v0.1 接口（已实现）

```python
from knosis import load_dataset, list_datasets, list_scenarios, describe

ds = load_dataset("relbench", "rel-f1", task="driver-dnf")
ds.tasks      # list[Task(id, input, answer, split, kind, meta)]；answer 是 GT（值或文件路径）
ds.files      # 命名的数据文件 / 目录；ds.read(key) 按后缀打开
ds.schema     # 表 / DDL / 变量说明等结构信息
ds.units      # 知识单元 κ；目前只有 text 入口在 load 时产出
ds.metrics    # 官方指标名 -> 说明
```

- 每个基准一个 loader（`knosis/benchmarks/<name>.py`，约 40–70 行），`@register` 注册。
- 数据在 `data/<name>/`（`KNOSIS_DATA_DIR` 可改），不入仓；`knosis download <name>` 取数（HF snapshot / OpenML 导出 / git clone）。
- 给 agent 读的说明在 `knosis/cards/<name>.md`；上游来源与许可的细节在 `datacards/`。
- 刻意不做：版本探测、校验和、pickle 安全门等防御性代码。

---

## 4. 总体架构（v0.2 起）

**定位：Knosis 不做 agent，做 agent 用来「生产和使用知识」的那一层。** 外层 agent 循环交给 Codex / Claude Code 这类编码 agent（它们会越来越强、越来越同质）；Knosis 提供它们缺的三样东西：可审计、可演化的**知识层**，能被任何 agent 调用的**知识算子**，以及证明「知识确实有用」的**评测**。

```
knosis/
├── data/        数据面：基准 loader + 数据源接入（v0.1 已有，现为 knosis/benchmarks/）
├── tools/       算子中心：模型工具 / LLM 工具 / 技能，统一接口
├── knowledge/   知识层：κ 存储、版本、来源追踪、撤回传播、I1–I5 检查
├── agents/      编排：工作区、四阶段 prompt、Codex / Claude Code 适配
└── bench/       评测：知识增益与 transmission test
```

### 4.1 四阶段流程（对应 D → T → U）

一个工作区贯穿四个阶段，每个阶段是一次（或多轮）agent 运行。

| 阶段 | 目标 | 论文对应 | 产物 |
| --- | --- | --- | --- |
| 1. explore | 读 BRIEF 与数据，初步分析、找可疑数据（去噪） | L1 | 笔记、可疑项（κ，`form=finding`） |
| 2. extract | 从数据中提取知识单元（事实 / 规则 / 模式 / 方程 / schema），带 `C` 与 `π` | D | `K_0` |
| 3. refine（RSI） | 多轮：合并重复、把实例概括成带条件与例外的规则、用数据验证、修复冲突、淘汰不成立的 | T | `K_1 … K_T` + 每轮变更记录 |
| 4. decide | 用知识层做下游任务 | U | 预测 + 引用了哪些知识 |

```bash
knosis ws init ngdbench ngd-fin --out ws/ngd-fin
knosis ws run ws/ngd-fin explore --agent codex          # 内部调用 codex exec / claude -p
knosis ws run ws/ngd-fin extract --agent codex
knosis ws run ws/ngd-fin refine  --agent codex --rounds 3
knosis ws run ws/ngd-fin decide  --agent claude --knowledge K_3   # 或 none / K_0
```

- **每个阶段给 agent 的是目标，不是步骤。** 阶段 prompt 模板固定四块：**目标 / 输入 / 交付物 / 验收标准**（如「每条知识的 `π` 必须定位回 `data/` 中的具体文件、行或边」「规则必须在数据上验证并报告支持数与反例」）。怎么做、调哪些工具、写什么代码由 agent 决定。模板对所有基准通用。
- **RSI 的反馈信号**：默认用**数据验证**（agent 用代码在数据上检验每条知识，更新 `ρ`），纯自我反思容易越改越空（ACE 报告的 context collapse）。有评测后再加开发集反馈。
- **decide 的对照**：`--knowledge none | K_0 | K_T`、换模型族的 agent、是否允许看原始数据 —— 有了评测，这些组合就是论文的 transmission test，不需另写代码。

### 4.2 工作区

```
ws/ngd-fin/                 （git 仓库：每个阶段 / 每轮提交一次 = 知识层的版本历史）
├── BRIEF.md                数据集介绍 + 下游任务介绍（见 4.3）
├── AGENTS.md               目录约定 + κ 格式 + 工具目录入口；CLAUDE.md 引用它
├── TOOLS.md                本数据适用的工具清单（由 tools/ 注册表生成）
├── data/                   复制进来的可见数据（只读；大数据集用软链接）
├── tasks/                  decide 阶段的题目（不含答案）
├── stages/{1_explore, 2_extract, 3_refine/round_*, 4_decide}/
└── knowledge/units.jsonl   当前知识层
```

**GT 软隔离**（已定）：GT 不进工作区。各基准 GT 的位置：

| 基准 | GT 在哪 | 工作区里怎么处理 |
| --- | --- | --- |
| NGDBench | `query/*.json` 的 `clean_answer`；`noise_info/`；clean 图；**perturbed 图自身的加噪属性**（见 §2） | 只放去掉加噪属性的 perturbed 图与去掉答案的题目 |
| RelBench | `tasks/<t>/test.parquet` 的标签列 | test 只留实体与时间列 |
| TabArena | 整表含测试行目标值 | 按选定划分导出 train 表与无目标的 test 特征 |
| Burr | `mapping.json` / `mappings/` / `*.ttl` | 不放 |
| LLM-SRBench | parquet 的 `expression`；HDF5 的 test / ood_test | 只放 train 与变量说明 |
| NewtonBench | `laws.py` | 不放；模拟器以工具形式提供 |
| AlphaBench | `factor_gt`；IC 真值表 | 不放 |
| KramaBench | workload 的 `answer`；`solutions/` | 不放 |

容器硬隔离以后作为可选项。注意软隔离的一个漏洞：agent 所在环境里装着 Knosis，它可以直接 `load_dataset(...)` 读到原始数据和答案。评测时 agent 的环境不应能访问 `data/`（原始基准目录）。

### 4.3 BRIEF.md：给 agent 的唯一数据说明

一份简要介绍，分三块：

1. **数据是什么**：领域、规模、组成。例如「金融领域的属性图：节点有 Account / Person / Company / Loan / Medium，Account 带余额、类型等属性；边表示转账、担保、申请贷款……」。其中的事实（类型、属性、数量）先从数据算出来再写，保证准确。
2. **下游任务是什么**：任务类型（如多跳查询、聚合计数、管理类操作）+ 几道**不带答案的示例题**。带着任务提取知识效果更好。
3. **知识应该服务什么**：什么样的知识对这些任务有用（如「哪些关系可能缺失或有噪声」「哪些统计量常被查询」）。

**不放测试集本身。** 提取阶段看到具体测试题，agent 会预先算好答案存起来 —— 那是缓存，不是知识（论文式 2 的 `Q` 包含未预见的查询）。测试题只在 decide 阶段给。另保留一个「不告诉任务」的提取模式做对照，检验知识是否通用。

`datacards/`（出处、许可、上游问题）继续保留，只给人看。

### 4.4 tools/：三类算子

| 类型 | 谁执行 | 例子 |
| --- | --- | --- |
| **模型工具** | 神经模型 | ULTRA 链接预测、TabPFN、Chronos、实体消解 embedding |
| **LLM 工具** | Knosis 封装好的 LLM 流程 | AutoSchemaKG 抽 KG、LLM-SR 提方程、事件概念化 |
| **技能（skill）** | **外层 agent 自己执行**；Knosis 提供方法说明、辅助脚本、交付格式与验收检查 | 「从数据规律总结方程并验证」「把实例概括成带条件与例外的规则」 |

- 统一入口：CLI（`knosis tool run <name> ...`）、Python API、MCP 三种都暴露；工作区里的 `TOOLS.md` 列出适用工具，调不调由 agent 决定。
- 每个重模型在自己的环境里运行（独立 conda 环境或容器），核心包保持轻量。
- **硬规则：工具不改数据，只产出带分数、带来源的注解。** 输出就是 κ：`π = <tool>@<version>(<params>)`，`ρ = inferred` + 置信度。agent 再决定信不信、要不要用数据验证（论文 §4.5「发现了不等于已验证」）。
- 每个工具一张说明卡：用途、输入输出、**模型许可**（如 TabPFN-2.5 权重据称不可商用，需逐个核实）。

第一批算子按阶段 × 数据形态规划，**只先接试点用得上的**：

| 阶段 | 文本 | KG | 表格 | 时序 |
| --- | --- | --- | --- | --- |
| 发现 D | AutoSchemaKG | 规则挖掘（AMIE 类） | 符号回归（PySR）、因果发现 | — |
| 去噪 / 修复 | 近重复检测 | **ULTRA**（可疑边、缺失边）、实体消解 | **TabPFN**（不确定性 / 离群） | Chronos 异常检测 |
| 概念化 T | 事件概念化（CAT / CANDLE 类） | schema 归纳 | — | — |
| 推理 R | — | UltraQuery | — | — |
| 使用 U | — | — | TabPFN 接收知识（Gap 3） | Chronos 协变量 |

### 4.5 工具也会进化

工具本身就是**程序性知识**（论文里 Voyager 的技能库、SkillWeaver 的 API、Darwin Gödel Machine 进化自身代码都属此类）。因此工具也是知识层里的一种单元（`form=tool`），与其他知识一样有来源、版本、验证，也一样被 RSI 迭代。

- **两层工具库**：核心工具（Knosis 维护、版本固定）+ 工作区工具 `ws/tools/<name>/`（agent 新建或改进；每个带说明卡、运行脚本、自测、版本号）。
- **进化操作**：新建（把反复出现的分析封装成工具）/ 改进（调参、改 prompt 或代码、在当前数据上微调模型）/ 组合（串成流水线）/ 淘汰。
- **验证后才采用**：新工具或新版本只有在验证上胜过旧版本才被接受（同 Darwin Gödel Machine）。**验证信号不得使用测试 GT**，只用自监督信号，如在 NGD-Fin 上遮掉部分已有边、看工具能否找回；`noise_info/` 只在最终评测时使用，否则就是在针对答案进化。
- **两个循环交替**：refine 每一轮可以改知识（`K_t`），也可以改工具（`Tools_t`）。工具更好 → 知识更好；知识中发现的规律 → 沉淀成新工具。
- **晋升**：在一个工作区证明有效的工具，可拿到其他数据集上试，有效即进入共享工具库 —— 这是「程序性知识能否迁移」的检验（论文 P3）。

### 4.6 knowledge/：项目的核心资产

- **格式**：`units.jsonl`，一行一个 κ，外加 `derived_from`（派生自哪些单元）与 `support`（独立来源数）：

  ```json
  {"id": "...", "content": "...", "form": "finding|fact|rule|formula|schema|tool",
   "condition": "...", "provenance": "data/graph.gpickle#edge/123 | ultra@1.0(...)",
   "status": "observed|inferred|verified|retracted", "derived_from": ["..."], "support": 3}
  ```

- **版本**：工作区 git 提交即版本，可 diff、回滚。
- **检查**：每轮 refine 后自动跑结构检查（I1 来源不丢、`derived_from` 可解析、I2 重复来源不重复计数、I5 撤回传播），不通过打回。Knosis 不判断内容对错，只守结构。
- 规模上来后换成 parquet + 边表 + 来源索引，接口不变。

### 4.7 在 Codex / Claude Code 里用 Knosis（agent 主导）

除了「Knosis 启动 agent」，更常见的用法是**人在用 Codex / Claude Code 做任务，agent 自己想起来调用 Knosis**。同一套阶段模板支持两种模式：

| 模式 | 谁主导 | 怎么跑 |
| --- | --- | --- |
| 驱动模式 | 人或脚本 | `knosis ws run <阶段> --agent codex`：Knosis 启动 agent（`codex exec` / `claude -p`），适合批量实验 |
| **嵌入模式（默认）** | Codex / Claude Code 自己 | agent 调 `knosis ws next` 拿到下一阶段的目标 / 输入 / 交付物 / 验收标准，自己完成，再调 `knosis ws check` 做结构检查并提交版本 |

接入方式（已核实：codex-cli 0.160 支持 skills、plugins、MCP 客户端；Claude Code 2.1 支持 skills、`claude mcp add`、`claude mcp serve`）：

- **CLI**：agent 能跑 shell，`knosis ...` 直接可用。
- **Skill**（让 agent「自己想起来用」的关键）：`SKILL.md` 写清触发场景（分析数据、提取知识、复用已有结论时），`knosis install --claude / --codex` 装到对应目录；Codex 同时读项目的 `AGENTS.md`。
- **MCP server**（`knosis mcp`）：数据加载、工具调用、知识单元读写、结构检查暴露成工具。

**项目级持久知识层**：仓库里的 `.knosis/`。Codex 这次会话提取并验证过的知识，下次会话、换 Claude Code 都能接着用，且每条可追溯来源（论文 P1 / P3）。

**嵌套**：技术上可行（shell 里起 `codex exec` / `claude -p`；Claude Code 可经 `claude mcp serve` 被 Codex 当工具调用）。但外层沙箱常禁网、内层须非交互、成本与递归要控制，所以**默认不嵌套**：嵌入模式下执行者就是当前 agent。只有确实需要另一个 agent 时才嵌套（如 transmission test 必须由另一模型族接收知识），由 Knosis 统一启动，带深度上限（`KNOSIS_DEPTH`）与预算。

### 4.8 试点（已定：两个一起做）

- **NGDBench NGD-Fin**（1 万节点 / 6 万边）：`noise_info/` 精确记录注入的噪声（13849 条噪声边：增 5497 / 删 2839 / 改 6047），是去噪的现成 GT；同一批题在 clean 图上的答案，可检验去噪与知识是否提升答题。配 **ULTRA**。
- **TabArena**（单表）：验证工作区与流程在另一种数据形态上通用。配 **TabPFN**。
- 一组天然的对比：只能写代码的 agent vs 能调神经工具的 agent。

---

## 5. 路线

| 版本 | 内容 |
| --- | --- |
| v0.2 | 工作区 + 四阶段 prompt 模板（驱动 / 嵌入两种模式，含 `ws next` / `ws check`）+ Codex / Claude Code 的 skill 安装 + 知识单元格式与结构检查；tools/ 框架，接 ULTRA 与 TabPFN；NGD-Fin、TabArena 的 BRIEF；先跑通 explore 与 extract |
| v0.3 | refine（RSI）循环 + 不变量检查；**工具进化**（工作区工具、自监督验证、晋升）；接 AutoSchemaKG，文本入口可跑；第一批技能（方程总结、条件规则概括） |
| v0.4 | decide 阶段 + 评测（指标实现）；无知识 / `K_0` / `K_T` 对比 |
| v0.5 | L2 `R`（UltraQuery 等）；L3 非语言 FM 的知识接口（TabArena 上测 Gap 3） |
| v1.0 | transmission test（跨模型族 receiver + matched information / budget）；托管工具运行时 |
| 长期 | 从隐式 FM 抽取规则（Gap 1）；更多数据源接入 |

开源与商业的边界（初步）：格式、loader、工具接口、本地运行器、评测开源；托管 GPU 工具运行时、托管知识层（权限 / 审计 / 撤回）、企业数据源接入作为商业部分。

---

## 6. 与 position paper 的对应

| 论文概念 | Knosis 位置 | 状态 |
| --- | --- | --- |
| 知识单元 κ = (c, f, C, π, ρ) | `knowledge/` 的 `units.jsonl` | v0.2 |
| P1 Separability | 知识层独立于产出它的 agent / 模型，带来源与状态 | v0.2 |
| Discovery `D` | explore + extract 阶段；模型工具 / LLM 工具 / 技能 | v0.2 |
| 发现了不等于已验证 | 工具输出一律 `inferred`；验收要求数据验证 | v0.2 |
| Transformation `T` 与 I1–I5 | refine（RSI）+ 结构检查 | v0.3 |
| 程序性知识（技能、工作流）与其验证 | 工具即知识单元；工具进化须经自监督验证、可晋升到共享库 | v0.3 |
| 内化目标（式 2，含未预见查询） | BRIEF 只给任务类型与示例，测试题只在 decide 给 | v0.2 起 |
| Reasoning `R` | UltraQuery 等 + NGDBench clean / perturbed | v0.5 |
| Use `U`、Gap 3 | decide 阶段；TabPFN 知识接口 | v0.4 / v0.5 |
| transmission test | decide 的 `--knowledge` × 换模型族 | v1.0 |
