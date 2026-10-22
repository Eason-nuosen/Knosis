# 演示结果（v0.4，2026-10-21）

四类场景（单表、方程、多表、KG）上各跑通了一个小规模演示，另有从 agent 轨迹提取知识的演示（§5）：agent 在任务中提出、验证、修订知识，Knosis 记录证据、评测知识与任务。
全部用 Codex（`gpt-6.1-sol`，reasoning effort medium）驱动模式：explore → extract → refine（2 轮，带 dev 反馈）→ decide。
**每个设置只跑一次、题量很小，数字只说明流程跑通与现象，不构成统计结论。** 工作区在 `ws/`（不入仓）。

## 1. 单表 + TabPFN（TabArena）

**healthcare_insurance_expenses**（回归，训练 792 行 / 测试 446 行 / dev 100 行，repeat 0 fold 0）

| 设置 | RMSE | MAE | R² |
| --- | --- | --- | --- |
| 训练均值 | 11557.9 | 8848.3 | ≈0 |
| 纯 TabPFN（原始 6 特征） | 4110.8 | 1934.9 | 0.873 |
| agent 自己建模（未用 TabPFN，全流程，两次） | 4005.6 / 4047.7 | 2250.4 / 2295.0 | 0.879 / 0.877 |
| agent + TabPFN（不给知识，只跑 decide） | 4032.8 | 1981.1 | 0.878 |
| **agent + 知识 + TabPFN**（K_final，只跑 decide） | 4018.8 | **1783.9** | 0.879 |

知识（吸烟×BMI 交互、BMI 分段、年龄²）被转成 TabPFN 的派生特征，用 `tabpfn cv` 在训练集上比较后选择，CV 结果记回对应知识的证据。
MAE 比纯 TabPFN 低 7.8%；RMSE 差异在噪声范围内。带 SQL 检查的 7 条规律中 6 条在留出测试行上仍成立。
不强制时 agent 两次都没用 TabPFN（偏好自己写的线性模型）。

**Another-Dataset-on-used-Fiat-500**（先验少见；训练 925 / 测试 513）

| 设置 | RMSE | MAE | R² |
| --- | --- | --- | --- |
| 训练均值 | 1905.3 | 1606.0 | ≈0 |
| 纯 TabPFN | **681.7** | 500.7 | 0.872 |
| agent 自己建模（禁用 TabPFN） | 700.8 | 534.4 | 0.865 |
| agent + TabPFN | 682.3 | **499.9** | 0.872 |
| agent + 知识 + TabPFN | 684.0 | 503.6 | 0.871 |

知识（车龄 / 里程强负相关、二者不可替代、地理有条件信息量、价格按整十标价）是对的，但 TabPFN 已能从原始特征学到，转成特征后无增益。
初步判断：知识能否帮到 TabPFN，取决于数据里有没有 TabPFN 难以自行学到的结构。

## 2. 方程发现

**LLM-SRBench lsr_synth_matsci**（dev 2 / 测试 3 题，45 分钟）：测试 NMSE 中位数 5e-14，Acc₀.₁ 测试 1/3、分布外 3/3。
25 条知识、3 个候选被反驳并撤回（如「全局线性」「普遍零截距」）；`knosis knowledge trace` 可看到候选族 → 留出检验 → 反馈 → 收窄的过程。
agent 没给公式标 `meta.task / meta.expression`，因此「知识本身在留出点上是否成立」这次没算出来。

**NewtonBench m0_gravity**（只用 vanilla 系统；dev 2 组定律 / 测试 4 组，约 15 分钟）：测试 **4/4** 定律发现正确（RMSLE 1e-16～1e-19），
包括改写过的 `C·(m1·m2)²/r^1.5`、`C·m1/r^2.6`。28 次 `newton` 工具实验；「所有题都是 C·m1·m2/r²」的候选在新实验上偏差 1e18 被反驳撤回；
9 条 method（单轴缩放估指数、多背景检验无关变量、复测估噪声、对数域验证等），1 条 skill（`discover-positive-power`，引用 17 条知识）。

## 3. 多表 + 本体

本体来自 ontology-bench 的 annotations-claude，以知识库导入（`knosis kb import-ontology`）；BI-Bench 导入时去掉来自 Power BI 元数据的关系与逐题变换（`--strip-gt`）。

**RelBench rel-f1 / driver-top3**（继承本体）：AUROC 0.829（平凡基线 0.5），决策引用 13 条知识；继承的本体本来就与外键 GT 一致（13/13），测不出修正。

**BI-Bench 项目 149612320**（dev 1 / 测试 2）与 **KramaBench archeology**（dev 3 / 测试 9），三种条件：

| 条件 | BI-Bench 测试 | BI 本体 join 对比 Power BI GT（P/R） | KramaBench 测试 | 决策引用本体 |
| --- | --- | --- | --- | --- |
| 不用本体 | 2/2 | — | 4/9 | — |
| 自己构建任务相关本体 | 2/2 | 0.73 / 0.80 | 4/9 | 是 |
| 继承已有本体（去 GT），可修改 | 2/2 | 0/0 → 0.73 / 0.80 | 4/9 | 否 |

- 题量太小，任务指标分不出条件差异；KramaBench 失败题多为数值口径本身有争议的题（标注报告记录了官方解答与 workload 答案不一致）。
- 继承的本体被 agent 在数据上检验后基本重建（BI 去掉全部概念、join 换成 11 条已验证的；KramaBench 由 10 表 / 12 join / 73 概念缩成 8 / 1 / 0），
  BI 上最终与「自己构建」的 join 集合完全相同。
- 另一个 BI 项目 280113507（继承本体）：测试 2/3，本体未修改。

## 4. 噪声 KG（NGDBench NGD-Fin）

**题集问题**：NGDBench 的 NL 题面大量与 Cypher / GT 不一致（丢常数、否定翻转、把关系或端点说错、笛卡尔积计数等）。按「题面包含 Cypher 全部常数且提到所用关系」检查：

| 子集 | 有 NL 的题 | 不完整 |
| --- | --- | --- |
| NGD-Fin | 8250 | 72.6% |
| NGD-Bi | 27440 | 67.4% |
| NGD-MCP | 12500 | 40.1% |
| NGD-Econ | 2757 | 3.0% |
| NGD-Prime | 23165 | 0.0% |

NGD-Fin 通过上述检查的题里仍有 36% 有结构问题。演示改用人工核对的 30 题（`-o curated=ngd-fin-demo`，
`knosis/workspace/exporters/curated/ngd-fin-demo.yaml`）：按 Cypher 的真实语义重写题面，逐题在干净图上复算，与 GT 全部一致。
此前用未核对 NL 题得到的 NGD 结论作废。

**dev 给答案 vs 只给对错**（dev 10 / 测试 20，测试中 18 题受噪声影响）

| 条件 | 测试 EM | F1 | 受噪声影响题 EM | dev 反馈轨迹 | 耗时 |
| --- | --- | --- | --- | --- | --- |
| 照抄含噪图上执行 Cypher 的答案 | 0.10 | 0.258 | 0.0 | — | — |
| 给答案，每次全做 | **0.60** | **0.72** | 0.556 | 0.3 → 0.7 → 0.8 → 0.8（4 次） | 33 分钟 |
| 只给对错，自选题 | 0.55 | 0.67 | 0.50 | 0.1 → … → 0.8（10 次） | 49 分钟 |

噪声断言（`noise.jsonl`，对比干净图与含噪图的 diff；精确率均 ≈1.0，下表为召回）：

| 噪声类型 | 给答案 | 只给对错 |
| --- | --- | --- |
| 节点类型 | 1.00 | 1.00 |
| 属性（字段级 / 节点级） | 0.38 / 0.35 | ≈0 / 0.01 |
| 多出的边 | 0.77 | 0 |
| 改关系的边 | 0.41 | 0 |
| 缺失的边 | 0.20 | 0 |

给答案时 agent 能对比正确答案与自己的查询结果，推断出具体哪些边 / 属性是噪声并写成可执行的检测方法；只给对错时学得更慢，几乎不产出噪声知识。
两组共同失败的题集中在补不回缺失边、认不出被改的属性值、首跳属性被改的多跳计数。

## 5. 从 agent 轨迹提取知识

入口 `knosis ws init traces <名字> -o paths=<轨迹> [-o env=<轨迹当时的数据目录>]`。支持四种格式：
Codex rollout、Claude Code 会话、逐步记录（agent-rsi 的 AppWorld ReAct）、OpenAI 风格 messages。
四种格式都统一成步骤序列，知识的来源写到 `data/traces/<id>.jsonl#step/<n>`。
BRIEF 要求把轨迹里的话当成那个 agent 的说法，而不是事实：有环境的就复核，没有环境的保持 inferred。
打分器报告三项：
- `cites_trace`：引用了真实存在的步骤的知识占比；
- `env_verified`：有触及环境的支持证据的占比；
- `trace_checked`：只核对了与轨迹记录一致的占比。

**A. Codex 从自己的轨迹提取（有环境）。** 源轨迹是 §4 中「不带知识直接做 NGD 测试 20 题」的那次 Codex 运行：33 步，13 次工具调用，测试 EM 0.65；
提取时给了同一张含噪图作为环境。explore → extract → refine 共约 17 分钟，产出 37 条知识，其中 4 条为 method，另有 2 个 skill。
22 条 verified，4 条候选被反驳后撤回；`env_verified` 0.97。
- 典型例子：原轨迹第 23、27 步声称「按 (loanAmount, loanUsage) 组内一致的利率修复了异常利率」。
  在环境上复算后，这次修复实际改动 0 个节点（`explore/rate-repair-no-effect`），于是候选「组内修复有效」被反驳撤回。
- 其余知识：类型以 ID 前缀为准（1008 个节点 label 冲突）、平行边计数式 E=U+D、二跳连接的 multiplicity、日期 / 类别 / 利率的质量筛查。

**迁移检验**：把提取出的知识 `kb merge` 进知识库，在源轨迹没见过的 10 道题（原 dev 题）上只跑 decide：

| 条件 | 测试 EM（两次运行） | 受噪声影响题 EM |
| --- | --- | --- |
| 不带知识 | 0.70 / 0.70 | 0.625 |
| 继承轨迹知识（K_inherit） | 0.30 / 0.30 | 0.125 |

两次运行逐题对错完全相同，所以差距不是运行噪声。原因是：
- 含噪图里有被改关系的边，例如 Person→Account 的边被标成 `Company_Own_Account`。
- 不带知识的 agent 按「操作名 + 端点前缀」把这类边修回来了。
- 继承的知识如实记录了「7706 条冲突边大多没有唯一修复」。agent 据此改成按原始 label 查询、不修复，于是漏掉了这些边。

这些知识是对的，但对任务有害。源轨迹没有任何答案反馈，提取阶段无法得知哪种修复策略对任务有用，utility 全部空白。
这说明：从无反馈的轨迹中提取的知识，进入决策前需要经过 utility 检验（dev 反馈或消融），只验证正确性不够。

**B. agent-rsi 的 AppWorld 轨迹（无环境）。** 源数据如下：
- Qwen3.8-27B 在 test_normal 上的 6 条 Spotify 轨迹，成功 4 条、失败 2 条，共 382 步。
- 来自 pod 上 `runs/baseline/eval/qwen3_8/none_seed0`，为只读拷贝。

提取约 16 分钟，产出 43 条知识（6 条撤回）和 3 个 skill。`env_verified` 0，`trace_checked` 1.0：
所有检查都只能核对「说法与轨迹记录一致」，因此只有方法类知识标了 verified，其余保持 inferred。
用 agent-rsi 流水线在真实环境中验证过的 356 条 Spotify 知识作参照（来自另一批轨迹，场景不重叠），逐条比对：

| 对照 agent-rsi | 条数 |
| --- | --- |
| 只关于轨迹文件本身（截断、可见性等），不比 | 7 |
| 一致 | 7 |
| agent-rsi 更精确，兼容 | 5 |
| agent-rsi 未覆盖 | 18 |
| 矛盾 | 0 |

- 一致的例子：登录后要显式传 `access_token`，否则返回 401；`play_music` 的 song / album / playlist / queue_position 至多选一个；liked、song library、downloaded 是不同集合。
- agent-rsi 更精确的例子：`page_limit` 大于 20 时报 422，默认等价于 5。这类结论要在环境里做实验才能得到，轨迹里看不出来。
- 未覆盖的部分有三类：任务结果层面的教训（「每步 API 都成功但任务失败」「局部成功不等于验收通过」）、聚合与集合推理方法、phone app 的语义。
- 判定由子 agent 逐条比对完成，没有人工复核。

**改动**：知识库合并时，被引用的轨迹会复制进 KB 的 `traces/`，来源改写为 `knowledge/traces/...`，继承后仍能定位。
继承来的单元和证据会打上 `inherited` 标记，规则如下：
- 其中 `data/` 来源指向产生它的那个环境，新工作区的数据布局可能不同（轨迹工作区是 `data/env/`，NGD 是 `data/`），文件不存在时不判定；
- 文件存在但内容变了，照旧判过期。

## 6. 文本 → KG、MCP、知识体系（2026-10-22）

三个演示都很小（单次 `codex exec`，reasoning effort medium），只说明接口能用。

**autoschemakg 复现上游建图。** 用 NGD-Econ 上游的抽取文件（`kg_extraction/qwen2.5-14b-instruct_multi_financial.json`，664 段，
Qwen2.5-14B 按 AutoSchemaKG 抽取）直接 `build`，与上游发布的 `multiEcon.gpickle` 对照（按名字比较，不分大小写）：
我们的实体关系与事件关系边中 98.5% 出现在上游图里，节点名 99.5% 出现在上游图里，说明建图规则与上游一致。
其中头尾实体都逐字出现在原段落的实体关系占 76%；其余是改写、缩写或幻觉，工具在 `meta.grounded` 里标出。产物：`ws/demo-askg-econ/`。

**Codex 自己抽取并用图答题。** 文本是 PUMA 2023 年报中约 2500 字符的一段，后半段有 OCR 乱码（字符位移）。
Codex 按工具写出的 AutoSchemaKG 提示词自己抽取（实体关系 26 条、事件—实体 11 条、事件关系 1 条），建图，给 15 个节点写概念，
再用 `query` 查图回答 4 道事实题（CFO 是谁、重点市场、审计委员会主席交接、监事会扩员人数），4 题全对，每题附图中支撑边；
乱码部分被跳过。耗时 64 秒，约 2.6 万 token。头尾逐字出现在原文的实体关系占 96%。产物：`ws/demo-askg-text/`（`answers.md`、`kg/`）。

**Codex 只通过 MCP 操作知识层。** 在 newton 工作区的副本上，要求 Codex 不用 shell、只用 MCP：筛选 method、追溯证据链、
看大纲草稿、新增一条派生的适用条件规则、记 derivation 证据、检查。全部完成，知识层检查前后都是 28 个原有问题、新增 0 个。
第一次运行时所有 MCP 调用被拒：`codex exec` 下 MCP 调用默认需要审批而审批策略是 never，要给该服务设
`default_tools_approval_mode="approve"`（见 [interfaces.md](interfaces.md)）。约 3 万 token。产物：`ws/demo-mcp-newton/`。

**Codex 整理知识体系。** `knosis knowledge organize` 在 newton 工作区副本（44 条 κ、1 个 skill、1 条已撤回）上运行，
一次通过验收（151 秒，约 5.9 万 token）。结果分三层：场景「独立发现定律并提交经过验证的函数」（下分审计、辨识、依赖检验、
源码验证、反馈复核 5 节）、数据间关系（任务分组、实验接口）、数据本身（幂律诊断、观测质量、两道开发题各一节、独立验证）、
另有归档节放撤回的单元。Codex 在 10 个节的 `notes` 里标出疑似重复或矛盾的单元，例如两条 utility 统计的是同两道题，不能当作独立支持；
已撤回的「经典引力指数」假设与两道题的反馈结构矛盾。单元本身没有改动。产物：`ws/demo-organize-newton/knowledge/outline.yaml`。

## 知识层的使用情况

| 演示 | κ 数 | 粒度分布 | skill | 被反驳的证据 |
| --- | --- | --- | --- | --- |
| NGD 给答案 | 44 | dataset 28 / instance 11 / method 5 | — | 2 |
| BI-Bench 自建本体 | 74 | — | 2 | — |
| KramaBench 继承本体 | 70 | dataset 35 / method 7 / utility 28 | 4 | 20 |
| NewtonBench | 44 | dataset 14 / method 9 / utility 17 / instance 2 / relation 2 | 1 | 1 |

utility 由 dev 提交附带的 `used_units` 自动生成；KramaBench 上它暴露出「时间对齐」「表格布局」两条知识被用到的 3 道测试题全错，需要消融区分是题难还是知识有误。

## 已知局限

- 每个设置一次运行、题量小；对照组之间的差异多数在噪声范围内。
- GT 隔离是软隔离（原始数据与 agent 在同一台机器）。
- KramaBench 的字符串近似题、方程的符号等价未用 LLM 裁判。
- 轨迹提取的 `env_verified` 对检查类证据按「依赖输入里有环境文件」判断；`data_inputs` 记的是工作区全部数据文件，会偏宽。
- 尚未做：Claude Code 驱动（Claude Code 轨迹已能读入，未单独演示）、跨 agent 读者对照、只继承 method / skill 到新工作区的迁移实验、Burr / AlphaBench / text 的端到端演示。
