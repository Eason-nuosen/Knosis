# Burr

| 项 | 值 |
| --- | --- |
| 全名 | Burr: A Benchmark for Ontology Learning from Relational Databases |
| 出处 | Proc. ACM Manag. Data **3(6), Article 305, Dec 2025**（SIGMOD track），SIGMOD 2026 宣讲 |
| DOI | [10.1145/3769770](https://dl.acm.org/doi/10.1145/3769770) · DBLP `journals/pacmmod/LaskowskiHPPN25` |
| 作者 | Lukas Laskowski (HPI), Michael Hladik (SAP), Jan Portisch (SAP), Fabian Panse (Augsburg), Felix Naumann (HPI) |
| 代码 | https://github.com/HPI-Information-Systems/burr |
| arXiv | **没有找到预印本**（似乎直接投了 ACM）—— 未核实 |
| 勘误 | PACMMOD 4(1), Feb 2026 的更正说明原标题漏了 "[Experiments & Analysis]"（仅见搜索片段，未直接核实） |
| 访问 | 公开（git clone） |
| **许可** | **未声明** |
| Releases | **0 个** |
| 仓库单 commit | `530a5bc`，日期 2026-05-05 |

## 许可

**没有 LICENSE 文件。** 已核实：`ls -a | grep -i licen` 无返回；
GitHub About 面板无许可徽章、无描述、无 topics。
**复用条款未指定** —— 按「保留所有权利」对待。

**⚠️ 含 SAP 企业数据（`rba`）**，合规上尤其敏感。

## 获取

```bash
knosis download burr     # git clone 上游仓库
```

**数据全在 git 仓库里** —— 没有 pip 包、没有 HF 数据集、没有 release、没有申请表。
clone 下来就有全部 SQL、全部 mapping JSON、以及评测器。

上游的运行方式需要 Docker + 活的 PostgreSQL（`postgis/postgis:14-3.3`）+
W&B key。**Knosis 只读文件，不起任何服务。**

## 体量（上游三处说法不一致，以文件树为准）

| 来源 | 场景数 |
| --- | --- |
| README | 「46 个场景」 |
| 论文摘要 | 54 |
| **实际文件树** | **54 个 micro + 4 个真实库 = 58 个叶子场景** |

micro-benchmark 的 8 个类别（`find micro_benchmark -name schema.sql | wc -l` = 54）：

| 类别 | 数 | 测什么 |
| --- | --- | --- |
| `basic` | 12 | 表 / 属性 / 关系 / 无主键 / 无外键 基线 |
| `nm_tables` | 9 | n:m、三元关系、复合键、无约束 |
| `normalized` | 8 | 1NF/2NF/3NF、冗余、一表多概念 |
| `attributes` | 7 | 布尔关系、复合、多值、隐晦命名、弱实体 |
| `complex` | 7 | `scenario_a`…`scenario_f` 组合 |
| `hierarchy` | 5 | 完全冗余、反范式、each-combination、规范化、双子表 |
| `one_to_n` | 4 | 二元 n:1、带额外表、自反 |
| `one_to_one` | 2 | 单关系 vs 双关系 |

4 个真实库：

| key | 目录 | 表数 |
| --- | --- | --- |
| `mondial` | `real-world/mondial` | 46 |
| `npd` | `real-world/npd_factpages` | 70 |
| `iswc` | `real-world/iswc` | 9 |
| `rba` | `real-world/rba` | **7**（SAP 企业数据，已移除一张空表） |

## 布局

```
micro_benchmark/<类别>/<子类>/<场景>/
    schema.sql            # DDL + 通常还有实例数据
    mapping.json          # **gold 映射（答案）**
    <场景>_data.csv       # 实例行（可选）
    mapping.ttl / test_mapping.ttl   # 偶尔的 D2RQ turtle 变体

real-world/<库>/
    *.sql                 # schema（+ 实例数据）
    mappings/*.json       # 按本体类拆分的映射 + meta.json   （mondial 20 个、rba 23 个）
    meta.json             # 前缀声明
    *.ttl                 # 单体 D2RQ ground truth          （npd、iswc）
```

具体路径示例（文件树实况）：
`micro_benchmark/basic/table/person/{schema.sql,mapping.json,person_basic.csv}`、
`micro_benchmark/attributes/multi_value_attributes/hobbies/{…,hobbies.csv,person.csv}`、
`real-world/mondial/mappings/{country.json,city.json,river.json,…,meta.json}`。

**⚠️ ground truth 有两种形态**：mondial 与 rba 给按类拆分的 `mappings/*.json` 目录；
**npd 与 iswc 给单个 D2RQ `.ttl`**。同一个 parser（`JsonMapping` / `D2RQMapping`）读，
但加载器必须两种都接。

## 场景命名

没有全局命名规则 —— **名字就是它的路径**。
`ExperimentManager.start_experiments` 派生出的 ID 形如
`f"{group}__{base_scenario}__{scenario}"`，例如 `hierarchy__two_tables__reviewer_1`；
真实库是 `<库>__<变体>`，例如 `real_world__mondial__fk`。
`SCENARIO` 环境变量接受的是**实验配置的 key**（默认 `base_experiment`），**不是**场景名。

## Gold 映射结构

四个顶层键（`evaluator/mapping_parser/mapping/JsonMapping.py::parse_mapping` 实况）：

```json
{
  "classes": [
    { "id": "author_@@author.aid@@",   // URI 模板；@@表.列@@ 是主键占位
      "class": "Author",
      "name": "AuthorPerson",          // class-map 名，被 join 引用
      "prefix": "mondial",             // 默认 "base"
      "subClassOf": ["Person"],
      "bNodeIdColumns": "…", "condition": "…", "join": ["…"], "translateWith": "…" }
  ],
  "object_properties": [
    { "property": "hasCity", "belongsToClassMap": "CountryFull",
      "refersToClass": "City",         // 或 "refersToClassMap"
      "join": ["city.country = country.code"], "inverseOf": "cityIn" }
  ],
  "data_properties": [
    { "property": "population", "belongsToClassMap": "CountryFull",
      "type": "integer", "column": "Country.Population" }
  ],
  "translation_tables": [ { "name": "…", "translations": {} } ]   // 可选
}
```

`meta.json` 侧车提供 `relation_prefix` 与 `prefixes`（短名 → URI）。
上游 README 原话：*"For better readability, we decided to choose a `JSON` format,
which is automatically translated to `D2RQ`."*

## 指标（18 个数）

两个家族 × 三个元素种类 × {precision, recall}（F1 由 `2PR/(P+R)` 导出）：

- **`mapping_based`**（上游表格里叫 "Mapping"）—— 集合/多重集比较。
  相等判定用 `concept_based_equality`：两条映射匹配当且仅当
  **映射到同一个 SQL 来源 + 同一个本体概念**，而不是名字相同。
  `precision = Σ min(count_ref, count_learned) / Σ count_learned`；
  `recall = Σ tp / Σ count_ref`。**这是本基准的贡献点。**
- **`name_based`**（表格里叫 "Lexical"）—— 集合比较，纯**字面名字匹配**。

元素种类（`evaluator/metrics/caclulate_metrics.py`）：
`cls_*`（classes）、`rel_*`（object properties）、`attr_*`（data properties）。

**⚠️ 上游 README 的表格用 C / R / A 代表 Class / Relation / Attribute，
用 "Mapping" / "Lexical" 代表两个家族 —— 但 README 从未定义过这些缩写。**
要看懂必须读代码。样例值（Mondial / Ontop）：mapping C 0.56、R 0.28、A 0.51；
lexical C 0.38、R 0.00、A 0.35。
README 还带一条更正横幅：*"Values updated after correcting a small number of
missing database constraints in Mondial and NPD"* —— 抄来的表格若数字不同就是过期的。

## 已知问题

- **`docker-compose.yml` 开箱即坏**：硬编码了维护者本机路径
  `/home/lukas/burr/Burr/result:/results`，且设了 `runtime: nvidia` —— 非 NVIDIA 机器跑不起来。
- **默认实验配置只跑 `real_world`**：`config_template.py` 里 micro-benchmark 条目
  全被注释掉，`systems` 里也只启用了 `d2rmapper`。
  想复现论文的 micro 表格得自己改配置。
- **`pip install -e .` 仍然需要活的 Postgres**，每个 SQL 文件都要导进去。
  **没有「只读文件」的路径。**
- **W&B 在 import 时就被拉起**：`caclulate_metrics.py` 与 `ExperimentManager.py`
  顶部都是 `import wandb`，即使 `USE_WANDB=false` 也绕不开。
- **指标文件名拼错成 `caclulate_metrics.py`**（少一个 l），grep 时注意。
- 仓库里混着 `.DS_Store`、`old/` 子目录、两个 `unfinished_*.sjson`
  —— 实验室产物，不是发布产物。
