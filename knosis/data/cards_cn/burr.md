# Burr —— 从关系数据库学本体（DB → Ontology 映射）

## 来源

HPI Potsdam / SAP SE / Uni Augsburg。**Burr: A Benchmark for Ontology Learning from
Relational Databases**，Proc. ACM Manag. Data **3(6), Article 305, Dec 2025**（SIGMOD track），
DOI [10.1145/3769770](https://dl.acm.org/doi/10.1145/3769770)。
作者：Lukas Laskowski, Michael Hladik, Jan Portisch, Fabian Panse, Felix Naumann。
仓库 https://github.com/HPI-Information-Systems/burr

**没有 arXiv 预印本，没有 pip 包，没有 HF 数据集，没有 GitHub release。**
数据全在 git 仓库里：`knosis download burr` 会 `git clone`。
上游自带的运行方式要 Docker + 一个活的 PostgreSQL（postgis）+ W&B key，
但 **Knosis 只读文件，不需要起任何服务**。

**许可：未声明。** 仓库里没有 LICENSE / COPYING 文件，GitHub About 面板也没有许可徽章。
按「保留所有权利」对待 —— 不要打包再分发，引用请标注上游。**SAP 企业数据（`rba`）
尤其敏感，注意合规。**

体量很小：54 个 micro 场景（每个含 `schema.sql` + `mapping.json`，通常还有一张 csv）
+ 4 个真实库（Mondial 46 张表、NPD 70 张、ISWC 9 张、SAP RBA 7 张）。
整体几百 MB 级别。

上游自己的说明里场景数写成 46，论文写 54，实际文件树是 58 个叶子场景 ——
**以文件树为准**（54 个 micro + 4 个真实库）。

## 说明

Burr 考的是：**给一个关系数据库的 schema，能不能正确写出它到本体的映射。**

场景分两类：
- **micro-benchmark**（54 个，8 个类别）：人为构造的小型封装场景，每个专测一种建模情形 ——
  没有主键、没有外键、n:m 关系、三元关系、复合键、范式化程度、弱实体、层级冗余……
  类别与数量：`basic` 12、`nm_tables` 9、`normalized` 8、`attributes` 7、
  `complex` 7、`hierarchy` 5、`one_to_n` 4、`one_to_one` 2。
- **real-world**（4 个）：Mondial、NPD FactPages、ISWC、SAP RBA。

**数据布局**（注意 micro 与 real-world 的形态不同）：

```
micro_benchmark/<类别>/<子类>/<场景>/     schema.sql, mapping.json, <场景>_data.csv
real-world/<库>/                          *.sql, mappings/*.json + meta.json
                                          （NPD 与 ISWC 例外：只给一个 .ttl）
```

**这个基准的 gold 就是 `mapping.json`，它是答案。**
所以 Knosis 把它放在 `tasks` 里，**绝不放 `schema`，也绝不写进这段 description**。
调 `ds.tasks` 的那一刻你就拿到了答案，评测之外不要读。

映射文件是四个键的结构：`classes` / `object_properties` / `data_properties`
（外加可选的 `translation_tables`）。类里的 `id` 是 URI 模板，用 `@@表.列@@`
占位主键；join 条件写在类映射上。

**评测有 18 个数**：{类, 关系, 属性} × {precision, recall, F1} × {mapping-based, name-based}
两个家族。两个家族的区别很关键：
- **mapping-based** —— 按「映射到同一个 SQL 来源 + 同一个本体概念」判定相等，是集合/多重集比较。
  这是本基准的贡献点：名字取得不一样但语义对，算对。
- **name-based**（上游表格里叫 "Lexical"）—— 只做字面名字匹配。

上游 README 的表格用 **C / R / A** 代表 Class / Relation / Attribute，
用 "Mapping" / "Lexical" 代表两个家族 —— **README 从没定义过这些缩写**，
要看懂必须去读 `evaluator/metrics/` 下的代码。

适合：schema 理解、DB→本体映射、关系结构到概念层的抽象。
不适合：把 mapping.json 当输入 —— 那是答案，用它就等于抄。

陷阱：
- **上游的 `docker-compose.yml` 是坏的**：里面硬编码了维护者本机的路径
  `/home/lukas/burr/Burr/result:/results`，而且设了 `runtime: nvidia`，
  非 NVIDIA 机器直接跑不起来。
- **默认的实验配置只跑 real-world**，micro-benchmark 的条目在 config 里全被注释掉了。
  想复现论文里的 micro 表格得自己改配置。
- **ground truth 有两种格式**：Mondial 和 RBA 给的是按类拆分的 `mappings/*.json`，
  NPD 和 ISWC 给的是单个 D2RQ `.ttl`。同一个 parser 读，但形态不同。
- **`pip install -e .` 也仍然需要活的 Postgres**，没有「只读文件」的路径。
- 上游指标代码在 import 时就会 `import wandb`，即使 `USE_WANDB=false` 也绕不开。
- 指标文件名拼错成 `caclulate_metrics.py`（少一个 l），grep 的时候注意。
- 仓库里混着 `.DS_Store`、`old/` 子目录、两个 `unfinished_*.sjson` —— 实验室产物，不是发布产物。
- 场景的标识其实就是它的路径：`<类别>__<子类>__<场景>`，比如
  `hierarchy__two_tables__reviewer_1`；真实库是 `<库>__<变体>`，比如 `real_world__mondial__fk`。
