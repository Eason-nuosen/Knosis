# RelBench — $db / $task

## 数据是什么

$description

关系库放在 `data/db/<表>.parquet`，只含 $cutoff（测试时刻）之前的记录；没有时间列的表是全量。
数据可能含噪声；哪些是噪声、如何处理，由你判断。

各表：

$tables

结构（主键 / 时间列 / 外键）：

$schema

## 下游任务是什么

任务 `$task`（$task_type）：$task_description

- `data/train.parquet`：训练样本，含目标列 `$target`（时间早于 $val_timestamp）。
- `data/dev_features.parquet`：$n_dev 条开发样本（$val_timestamp 之后），只有 $keys，标签不给；可提交拿反馈。
- `data/test_features.parquet`：$n_test 条测试样本（$cutoff 之后），只有 $keys。

每个样本在其时间列给出的时刻做预测，只能使用该时刻之前的信息。
交付 CSV：`row_id` 与 `prediction` 两列，$format。

## 知识应该服务什么

让同类实体在未来时刻的预测更准：关于表间关系、实体行为、时间规律与数据可信度的知识都可以提取。
知识应当可复用，不应缓存具体测试样本的答案。
