# 知识层 v0.5 设计（已实现）

> 状态：2026-10-23 与用户讨论确定，2026-10-24 已实现（现行格式见 [knowledge.md](knowledge.md)、[scope.md](scope.md)）。实现时的取舍：旧布局不做双重兼容，统一用 `knosis migrate` 转换；去重新增状态 `merged`；内化操作记在 `evidence/consolidate.jsonl`（不混进证据账本）；不加 extent；版本化只做 `superseded_by`；skill 上的证据迁移为 `usage/skill:<名字>/migrated` 单元。

v0.4 的知识层把七类东西（units、evidence、checks、skills、ontology、feedback、outline）平铺在一个 `knowledge/` 目录里，
粒度里又混着「对象层级」和「元知识」。v0.5 做三件事：**目录分成两大块**、**粒度分成对象知识与元知识**、**把内化补齐成一组算子**。

## 1. 两大块：kb 与 evidence

```
kb/                         知识主体：永久保存、可继承、可被 select
├── knowledge/
│   ├── units.jsonl         κ：对象知识 + 元知识（method / usage）
│   └── ontology/           结构化知识，支持 OSI 标准（Open Semantic Interchange，现 Apache Ossie 0.2）+ EOB 扩展，用于企业数据的本体层对齐
├── skills/<名字>/SKILL.md  使用流程
└── outline.yaml            导航大纲

evidence/                   来源与验证的全过程
├── ledger.jsonl            证据账本（原 evidence.jsonl）
├── checks/                 可执行检查
├── feedback/               dev 反馈记录（含 dev 划分说明）
└── traces/                 来源轨迹（kb collect 收来的会话、ws init traces 的输入）
```

- **ontology 支持 OSI 标准**（Open Semantic Interchange，现 Apache Ossie）：core 语义模型 / ontology / mapping 三文件，额外信息只写 EOB 扩展、不改官方 schema。用途是企业数据的本体层对齐：agent 检验出的 join、主键、概念可导出给支持 OSI 的语义层工具，企业已有语义模型可经 `kb import-ontology` 导入后由 agent 逐条检验。
- **knowledge = units + ontology**。本体不是单独一层，而是结构化知识的另一种存法：读取时本体元素照旧展开成 `form=schema` 的 κ，
  与 units 一起参与 select、证据、撤回传播、大纲。
- **kb 里只放结论，evidence 里放过程**。κ 的 `provenance` 与 `check` 只是指针，指向 `evidence/` 下的材料。
- 工作区与独立知识库用同一布局（工作区是 `<ws>/kb/` + `<ws>/evidence/`）。`kb merge` 时证据跟着知识一起写回，
  否则继承方无法判断知识是否可信；数据指纹变化后证据过期的规则不变。

## 2. 粒度：对象知识与元知识

| 层（`level`，自动推出） | scope | 回答的问题 | 怎么验证 |
| --- | --- | --- | --- |
| object（关于环境） | `instance` | 某个具体对象（行、节点、边、列）是什么样 | 直接查数据、对照 GT |
| object | `relation` | 对象之间的结构（join、本体关系） | 包含依赖、外键检查 |
| object | `dataset` | 整份数据的规律、分布、公式 | 留出行 / 留出点上重跑 |
| meta（关于知识） | `method` | 怎么**得到**知识：发现与验证的方法 | 脱离原工作区、换数据重跑仍产出有效知识 |
| meta | `usage` | 怎么**用好**知识：哪些知识在什么任务、什么读者下有效 | dev 反馈、消融（`ws fork --drop`） |

- `usage` 取代原 `utility`。`usage` 单元是可被反驳的断言，例如「知识 X 对 NGD 多跳计数题、读者 Codex 有负效果」；
  只能由 feedback / ablation 证据支持为 verified（沿用 v0.4 规则）。
- form 的 `method` 改名为 **`procedure`**（步骤型表达），避免与 scope 的 `method` 撞名。form 变为：
  finding / fact / rule / formula / schema / tool / procedure。

### usage 与 skill 的分工

两者都属于「怎么用知识」，区别是**断言**与**流程**：

| | usage 单元 | skill |
| --- | --- | --- |
| 是什么 | 「X 对 T 有没有用」的断言 | 把若干知识组合成的解题流程 |
| 存放 | `kb/knowledge/units.jsonl`（scope=usage） | `kb/skills/<名字>/SKILL.md` |
| 讲不讲对错 | 讲，可被反驳 | 不讲，只讲步骤 |
| 关系 | 可以评价 skill：「skill S 在 T 上 dev 2/2」记成 usage 单元 | `uses` 引用知识与 usage 单元 |

即：**usage 管有没有用，skill 管怎么做**。skill 的效果不再直接写成以 `skill:<名字>` 为对象的证据，而是写成 usage 单元，再由证据支持。

## 3. 内化：一组作用在 kb 上的算子

内化（L2 Internalize）= 让知识库保持正确、不重复、不自相矛盾、成体系。每个算子都在 `evidence/ledger.jsonl` 留痕。
由 agent 判断内容，Knosis 只检查不变式。

| 算子 | 做什么 | Knosis 检查的不变式 | 现状 |
| --- | --- | --- | --- |
| verify | 重跑可执行检查，记证据 | 状态与证据一致、I2、证据过期 | 已有 |
| **dedup 去重** | 找同一对象（`about` / 来源相同）上内容相近的单元，合并为一条 | 旧 id 留 `merged_into` 别名且可解析；来源合并；支持数按独立来源计（I2） | 只在 collect 提示词里写入时顺手做 |
| **conflict 矛盾处理** | 找同一对象上互斥的断言，三选一处理：① 收窄条件，两条在不同条件下都成立；② 用新证据裁决，一方撤回；③ 环境变了，按版本处理（`superseded_by`、有效期） | 每对已识别的矛盾要么已处理，要么双方为 `contested`；`contested` 默认不被 select 选中 | 只在 collect 提示词里写入时改 contested |
| **organize 构建知识体系** | 把零散的单跳知识（一条只讲一个对象、一步关系）串成清晰的脉络：场景 → 数据间关系 → 具体对象，标出知识间的依赖与推导链；串联中可归纳出上位规律（多条 instance → dataset 规律，多次成功 → method） | 大纲只组织、不新增断言；归纳出的上位规律是新断言，必须 `derived_from` 原单元，状态从 inferred 起步，需再验证 | 只有大纲（`knowledge organize`），归纳未做 |
| archive 归档 | 失效单元、usage 长期为零或为负的单元移出默认检索 | 不删除，可恢复；大纲里只能在 archive 节 | 部分（大纲 archive 节） |

命令：`knosis knowledge consolidate [--steps dedup,conflict,organize] [--agent codex|claude]`，依次启动 agent 做三步，
每步验收不过重试一次，仍不过用 git 恢复。`knosis kb collect` 结束时改为自动运行 consolidate（替代现在只跑 organize）。
MCP 增加对应工具（候选重复对、候选矛盾对的列表），让 agent 在会话中也能处理。

## 4. 迁移

| v0.4 | v0.5 |
| --- | --- |
| `knowledge/units.jsonl` | `kb/knowledge/units.jsonl` |
| `knowledge/ontology/` | `kb/knowledge/ontology/` |
| `knowledge/skills/` | `kb/skills/` |
| `knowledge/outline.yaml` | `kb/outline.yaml` |
| `knowledge/evidence.jsonl` | `evidence/ledger.jsonl` |
| `knowledge/checks/` | `evidence/checks/`（`check.path` 同步改写） |
| `knowledge/feedback/` | `evidence/feedback/`（`feedback:` 来源写法不变） |
| 知识库 `traces/` | `evidence/traces/` |
| `scope=utility`，id `utility/…` | `scope=usage`，id `usage/…`（旧 id 留别名） |
| `form=method` | `form=procedure` |
| 以 `skill:<名字>` 为对象的证据 | 转成一条 usage 单元 + 证据 |

提供 `knosis migrate <工作区或知识库>` 一次转换，旧布局在过渡期内仍可读（只读）。
受影响代码：`knowledge/units.py`、`kb.py`、`evidence.py`、`feedback.py`、`outline.py`、`skills.py`、`mcp.py`、`cli.py`、
`workspace/`（快照路径、提示词模板 AGENTS.md / refine.md / collect.md / organize.md）、`decision/`（used_units 统计），以及相关测试。

## 待定

- 原先提过的「适用范围 extent」（run / dataset / benchmark / modality / general，由证据算出已证实范围）是否一并加入，待用户决定。
- 矛盾处理中的版本化（bi-temporal）是先只做 `superseded_by`，还是同时记有效期，待定。
