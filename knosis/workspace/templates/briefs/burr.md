# Burr — $scenario

## 数据是什么

关系数据库：`.sql` 文件是 PostgreSQL 的建表语句（DDL，部分还带实例数据的 INSERT），`.csv` 是表的实例数据。
$layout。每道题对应一个数据库（题目的 `files` 列出它的文件）。
数据可能含噪声（如命名含糊、约束缺失）；哪些是噪声、如何处理，由你判断。

## 下游任务是什么

为每个数据库写出它到本体的映射：数据库里有哪些概念（类）、概念之间有哪些关系、概念有哪些属性，
以及它们分别来自哪些表、列与 join。`tasks/dev.jsonl` 有 $n_dev 道开发题，测试题（$n_test 道）在 decide 阶段给出。

交付 `predictions.jsonl`，每行 `{"id": 题目 id, "answer": 映射}`，映射用 Burr 的 JSON 格式：

```json
{"classes": [{"id": "<实例 URI 模式，用 @@表.列@@ 引用列，如 thing/@@t.id@@>", "class": "<类名>", "name": "<映射名，默认同类名>",
              "condition": "<可选，SQL 条件>", "join": ["<可选，a.x = b.y>"], "subClassOf": "<可选，父类>"}],
 "object_properties": [{"property": "<关系名>", "belongsToClassMap": "<映射名>", "refersToClassMap": "<映射名>",
                        "join": ["a.x = b.y"], "condition": "<可选>"}],
 "data_properties": [{"property": "<属性名>", "belongsToClassMap": "<映射名>", "type": "<string|integer|...>",
                      "column": "<表.列>", "sqlExpression": "<可选，代替 column 的 SQL 表达式>"}]}
```

评测（移植自上游 Burr 评测器）：类、关系、属性各算精确率 / 召回率 / F1，两种口径——
**mapping-based** 看映射到的数据是否一致（URI 模式中的列、条件、join、列 / 表达式），
**name-based** 看类名、关系名、属性名（及所属类名）是否一致。

也可以先把结构写成 `knowledge/ontology/` 下的本体（Ossie 三文件），再转成上面的交付格式；不强制。

## 知识应该服务什么

让未见过的数据库也能映射得更准：表结构到概念的常见模式、如何从键、外键、命名与实例数据判断概念与关系、
哪些表是关联表、继承如何体现等，都可以写成知识。知识应当可复用，不应缓存具体测试题的答案。
