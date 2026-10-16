---
name: tabpfn
version: "0.1"
kind: model
modality: [table]
stage: [explore, extract, decide]
env: knosis-tabpfn
license: "TabPFN 当前上游代码 Apache-2.0；模型权重采用独立且随版本变化的许可，部分受 gated/非商用限制，须核对所选 checkpoint。"
---

表格预测与训练集 OOF 可疑标签检查。输入 parquet，只读；
`row_id` 不作为特征。支持分类概率/熵，以及回归预测/分位数区间/残差。

```bash
knosis tool run tabpfn -- predict --train data/train.parquet --test data/test_features.parquet --target TARGET --out stages/4_decide/tabpfn --prepare-only
knosis tool run tabpfn -- predict --train data/train.parquet --test data/test_features.parquet --target TARGET --problem-type regression --out stages/4_decide/tabpfn
knosis tool run tabpfn -- oof --train data/train.parquet --target TARGET --folds 5 --out stages/1_explore/tabpfn
```

`--prepare-only` 不导入 TabPFN，不下载模型：输出 `input_summary.parquet`、
空 `units.jsonl` 和 `run.json`，用于 Mac 上检查接口，绝不输出伪预测。
真实 predict 输出 `predictions.parquet`；oof 输出 `oof_predictions.parquet`
和标签可疑项 finding。所有注解都为 inferred，不直接写入知识层。

`--problem-type auto|classification|regression`；auto 以目标 dtype 判断，
数值型分类标签应显式选 classification。
`--model` 是所选版本的本地 checkpoint 路径，默认 auto 使用安装版本的默认权重。
`--device` 默认 auto。`--max-rows` 默认 10000，`--max-features` 默认 500，
固定 `--seed` 下采样并在 run.json 记录实际训练行与特征；这不是所有版本的统一上限，
请按所选权重的上限与显存修改。OOF 始终覆盖所有训练行，只对每折 fit 数据下采样。
OOF 不读取测试标签，低真值概率或大残差不是噪声的充分证据。

服务器专用环境安装 `tabpfn` 以及 Knosis，首次真实推断可能下载权重。
用 `KNOSIS_TABPFN_PYTHON=/opt/conda/envs/knosis-tabpfn/bin/python` 指定环境。
上游：[PriorLabs/TabPFN](https://github.com/PriorLabs/TabPFN)；
代码 LICENSE 与 HuggingFace checkpoint 的模型许可分别核对，不将代码许可视作权重许可。
本版未固定、未下载或验证某个权重，不宣称任何版本均可商用。
