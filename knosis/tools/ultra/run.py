"""ULTRA input conversion and inference; prepare-only runs without torch."""

from __future__ import annotations

import argparse
import json
import pickle
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

from knosis.tools import write_result


def graph_to_triples(graph):
    entities = sorted(graph.nodes, key=str)
    edges = (list(graph.edges(keys=True, data=True)) if graph.is_multigraph()
             else [(h, t, 0, attrs) for h, t, attrs in graph.edges(data=True)])
    edges.sort(key=lambda edge: (str(edge[0]), str(edge[1]), str(edge[2])))
    relations = sorted({attrs["label"] for *_, attrs in edges})
    entity_ids = {entity: i for i, entity in enumerate(entities)}
    relation_ids = {relation: i for i, relation in enumerate(relations)}
    # (h, r, t) here; ULTRA batches must be converted to (h, t, r) at inference.
    direct = [(entity_ids[h], relation_ids[attrs["label"]], entity_ids[t]) for h, t, _, attrs in edges]
    inverse = [(t, r + len(relations), h) for h, r, t in direct]
    return {"entities": entities, "relations": relations, "edges": edges,
            "direct": direct, "triples": direct + inverse}


def load_model(encoded, ckpt, device=None, config=None):
    import torch
    import yaml
    from torch_geometric.data import Data
    from ultra.models import Ultra
    from ultra.tasks import build_relation_graph

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    triples = torch.tensor(encoded["triples"], dtype=torch.long).reshape(-1, 3)
    graph = Data(edge_index=triples[:, [0, 2]].T, edge_type=triples[:, 1],
                 num_nodes=len(encoded["entities"]), num_relations=2 * len(encoded["relations"]))
    # Upstream relation graph construction uses CPU tensors; move to the device after it is built.
    graph = build_relation_graph(graph).to(device)
    base = {"input_dim": 64, "hidden_dims": [64] * 6, "message_func": "distmult",
            "aggregate_func": "sum", "short_cut": True, "layer_norm": True}
    cfg = (yaml.safe_load(Path(config).read_text()) if config else
           {"relation_model": {"class": "RelNBFNet", **base},
            "entity_model": {"class": "EntityNBFNet", **base}})
    cfg = cfg.get("model", cfg)
    model = Ultra(cfg["relation_model"], cfg["entity_model"]).to(device)
    model.load_state_dict(torch.load(ckpt, map_location=device)["model"])
    model.eval()

    def score(h, r):
        tails = torch.arange(graph.num_nodes, device=device)
        batch = torch.stack([torch.full_like(tails, h), tails, torch.full_like(tails, r)], dim=-1)[None]
        with torch.no_grad():
            return model(graph, batch)[0].cpu().numpy()

    return score, device


def score_edges(encoded, scorer, topk=50, max_edges=None):
    entities, relations = encoded["entities"], encoded["relations"]
    queries = defaultdict(list)
    existing = defaultdict(set)
    for triple in encoded["direct"]:
        h, r, t = triple
        existing[h, r].add(t)
    for triple, edge in list(zip(encoded["direct"], encoded["edges"]))[:max_edges]:
        h, r, t = triple
        queries[h, r].append((t, edge[2]))
    scores, missing = [], []
    for (h, r), tails in queries.items():
        values = scorer(h, r)
        order = sorted(range(len(entities)), key=lambda t: (-float(values[t]), t))
        ranks = {t: i + 1 for i, t in enumerate(order)}
        for t, key in tails:
            scores.append({"src": str(entities[h]), "label": relations[r], "dst": str(entities[t]),
                           "key": str(key), "score": float(values[t]), "rank": ranks[t]})
        for t in order[:topk]:
            if t not in existing[h, r]:
                missing.append({"src": str(entities[h]), "label": relations[r],
                                "dst": str(entities[t]), "score": float(values[t])})
    return (pd.DataFrame(scores, columns=["src", "label", "dst", "key", "score", "rank"]),
            pd.DataFrame(missing, columns=["src", "label", "dst", "score"]))


def findings(scores, missing, graph_path, topk):
    units = []
    for kind, rows in (("suspicious", scores.sort_values("rank", ascending=False).head(topk)),
                       ("missing", missing.sort_values("score", ascending=False).head(topk))):
        for row in rows.to_dict("records"):
            edge = f"{row['src']}|{row['label']}|{row['dst']}"
            # A missing edge has no edge location, so the provenance points to the observed head node.
            location = f"edge/{edge}" if kind == "suspicious" else f"node/{row['src']}"
            units.append({
                "id": f"ultra/{kind}/{len(units)}", "form": "finding",
                "content": f"{'可疑边' if kind == 'suspicious' else '可能缺失的边'}: {edge}",
                "condition": "模型候选，需用数据验证",
                "provenance": f"tool:ultra@0.1(topk={topk}) ; {graph_path}#{location}",
                "status": "inferred", "meta": row,
            })
    return units


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ckpt")
    parser.add_argument("--config")
    parser.add_argument("--topk", type=int, default=50)
    parser.add_argument("--max-edges", type=int)
    parser.add_argument("--device")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.prepare_only and not args.ckpt:
        parser.error("--ckpt is required for real inference")
    started = time.monotonic()
    with Path(args.graph).open("rb") as fh:
        encoded = graph_to_triples(pickle.load(fh))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    params = vars(args).copy()
    params.update(n_entities=len(encoded["entities"]), n_relations=len(encoded["relations"]),
                  n_edges=len(encoded["direct"]))
    if args.prepare_only:
        pd.DataFrame(encoded["triples"], columns=["head", "relation", "tail"]).to_parquet(
            out / "triples.parquet", index=False,
        )
        (out / "mapping.json").write_text(json.dumps({
            "entities": [str(e) for e in encoded["entities"]], "relations": encoded["relations"],
            "inverse_relation_offset": len(encoded["relations"]),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        units = []
    else:
        scorer, params["device"] = load_model(encoded, args.ckpt, args.device, args.config)
        scores, missing = score_edges(encoded, scorer, args.topk, args.max_edges)
        scores.to_parquet(out / "edge_scores.parquet", index=False)
        missing.to_parquet(out / "missing_candidates.parquet", index=False)
        units = findings(scores, missing, args.graph, args.topk)
    write_result(out, "ultra", params, units, started)


if __name__ == "__main__":
    main()
