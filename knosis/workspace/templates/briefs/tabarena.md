# TabArena — $name

## 数据是什么

单表数据集 `$name`，目标列 `$target`，任务类型 `$problem_type`。
训练集有 $n_train 行，测试集有 $n_test 行，共 $n_features 个特征。
`data/train.parquet` 含训练标签；`data/test_features.parquet` 不含目标列。
两表的 `row_id` 是原始行号，不是预测特征。

原始列与类型：

$columns

数据集说明：

$description

## 下游任务是什么

为测试特征表的每一行预测 `$target`，保留对应的 `row_id`。
分类可同时提供各类概率。测试标签不在工作区，不能寻找或读取。

## 知识应该服务什么

识别缺失、异常、重复、可疑取值和潜在泄漏特征；
提取特征与目标之间的规律，并记录成立条件和反例；
用领域知识解释数据结构。所有验证仅使用训练数据。
