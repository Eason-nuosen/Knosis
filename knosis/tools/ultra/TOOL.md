---
name: ultra
version: "0.1"
kind: model
modality: [graph]
stage: [explore, extract]
env: knosis-ultra
requires: [torch, torch_geometric]
license: "Upstream ULTRA code is MIT; check the model card of the checkpoint release you choose. This package does not distribute weights."
---

Zero-shot KG link prediction: scores and ranks existing edges and proposes edges that may be missing.
The input is a pickled NetworkX graph (directed or multigraph) whose edges carry a `label` attribute; the file is only read, and the original graph is not modified.

```bash
knosis tool run ultra -- --graph data/graph.gpickle --out stages/1_explore/ultra --prepare-only
knosis tool run ultra -- --graph data/graph.gpickle --ckpt /models/ultra_3g.pth --out stages/1_explore/ultra --device cuda --topk 50
```

`--prepare-only` does not import torch or download weights; it only exports `triples.parquet` (with inverse relations added)
and `mapping.json`, plus an empty `units.jsonl` and `run.json`. It is for checking the pipeline without the model environment, not model inference.
Real inference requires `--ckpt` and writes `edge_scores.parquet` (score and rank of each existing edge), `missing_candidates.parquet` (top `--topk` tails per (head, relation) not already in the graph),
inferred findings with sources and scores (the `--topk` lowest-ranked existing edges as suspicious edges, and the `--topk` highest-scoring missing candidates), and a run record.
`--max-edges N` limits the number of edges scored; it does not truncate the context graph.
`--config PATH` can supply a YAML with relation_model and entity_model;
the default matches the upstream 64-dim, 6-layer ULTRA checkpoints. Without `--device`, cuda is used if a GPU is available, otherwise cpu.
Ranks are unfiltered ranks over all entities, and raw scores are logits, not calibrated confidences; they cannot be taken directly as proof of noise.

On the server, clone [ULTRA](https://github.com/DeepGraphLearning/ULTRA),
add the repository to the PYTHONPATH of a dedicated environment, and install Knosis and the graph dependencies in that environment.
The reference combination in the upstream README is Python 3.9, torch 2.1.0, PyG 2.4.0,
torch-scatter 2.1.2, torch-sparse 0.6.18, ninja; CUDA 11.8+, and rspmm is compiled on first run.
Match the CUDA / torch wheels to your server; do not install these dependencies in the core Knosis environment.
Get checkpoints from the Checkpoints section of the upstream README or the linked HuggingFace collection.

Set the interpreter with `KNOSIS_ULTRA_PYTHON=/opt/conda/envs/knosis-ultra/bin/python`.
The weight license cannot be inferred from the MIT code license; check the specific model card and terms before commercial use.
