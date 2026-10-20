---
name: ultra
version: "0.1"
kind: model
modality: [graph]
stage: [explore, extract]
env: knosis-ultra
requires: [torch, torch_geometric]
license: "ULTRA 上游代码 MIT；checkpoint 需核对所选发布的模型卡，本包不分发权重。"
---

KG 零样本链接预测：给已有边打分与排名，提出可能缺失的边。
输入是含边 `label` 的 NetworkX 图，只读文件，不修改原图。

```bash
knosis tool run ultra -- --graph data/graph.gpickle --out stages/1_explore/ultra --prepare-only
knosis tool run ultra -- --graph data/graph.gpickle --ckpt /models/ultra_3g.pth --out stages/1_explore/ultra --device cuda --topk 50
```

`--prepare-only` 不导入 torch、不下载权重，只导出 `triples.parquet`
和 `mapping.json`，以及空 `units.jsonl` 与 `run.json`。用于 Mac 流程检查，不是模型推断。
真实推断输出 `edge_scores.parquet`、`missing_candidates.parquet`、
带来源与分数的 inferred finding 和运行记录。
`--max-edges N` 限制待评分边数，不截断上下文图。
`--config PATH` 可提供包含 relation_model、entity_model 的 YAML；
默认对应上游 64 维、6 层的 ULTRA checkpoint。未指定设备时有 GPU 用 cuda，否则 cpu。
排名是全实体的未过滤排名，原始分数是 logit，不是校准置信度；不能直接断言噪声。

服务器上克隆 [ULTRA](https://github.com/DeepGraphLearning/ULTRA)，
将仓库加入专用环境的 PYTHONPATH，并在该环境安装 Knosis 与 graph 依赖。
上游 README 的参考组合为 Python 3.9、torch 2.1.0、PyG 2.4.0、
torch-scatter 2.1.2、torch-sparse 0.6.18、ninja；CUDA 11.8+，首次执行编译 rspmm。
实际服务器请匹配 CUDA/torch 的 wheel，不在 Knosis 核心环境安装这些依赖。
checkpoint 从上游 README 的 Checkpoints 或链接的 HuggingFace 集合获取。

解释器通过 `KNOSIS_ULTRA_PYTHON=/opt/conda/envs/knosis-ultra/bin/python` 指定。
模型权重许可不能由代码 MIT 推断；商用前核对具体模型卡及条款。
