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
分类可同时提供各类概率（列名 `probability_<类别>`）。测试标签不在工作区，不能寻找或读取。
若有 `data/dev_features.parquet`，它是去掉标签的开发行，可提交预测换取反馈。

## 知识应该服务什么

数据可能含噪声；哪些是噪声、如何处理，由你判断。
提取特征与目标之间可复用的规律，记录成立条件和反例；验证只用训练数据与反馈。
能写成 SQL 检查（表名 `train`）的规律，写进 κ 的 `check`；评测时这些检查会在带标签的留出行上重跑，
用来评估知识本身是否成立（与预测分数分开统计）。
