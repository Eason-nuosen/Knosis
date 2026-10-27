"""Graph QA (NGDBench) scoring: answer-set EM / F1; noise claims (`noise.jsonl`) are scored against the clean / perturbed graph diff."""

from __future__ import annotations

import pickle
from collections import defaultdict
from functools import cache

from ..knowledge import load_units
from . import answers, mean, register, register_knowledge


def scalar(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return f"{float(value):.6g}"
    if value is None:
        return "null"
    text = str(value).strip()
    try:
        return f"{float(text):.6g}"
    except ValueError:
        return text


def answer_set(value) -> frozenset:
    """Scalar -> singleton set; lists deduplicated; dict rows compare values only (aliases need not match the Cypher RETURN), a single-column dict equals its value."""
    items = value if isinstance(value, list) else [value]
    return frozenset(
        (scalar(*item.values()) if len(item) == 1 else tuple(sorted(scalar(v) for v in item.values())))
        if isinstance(item, dict) else scalar(item) for item in items
    )


def f1(pred: frozenset, gold: frozenset) -> float:
    if not pred and not gold:
        return 1.0
    hit = len(pred & gold)
    return 2 * hit / (len(pred) + len(gold)) if hit else 0.0


def summarize(rows) -> dict:
    return {"answer_set_em": mean(rows, "ok"), "answer_set_f1": mean(rows, "f1")}


@register("ngdbench")
def score(ws, state, ds, path, ids) -> dict:
    gold = {t.id: t for t in ds.tasks}
    predictions = answers(path)
    items, noise, by_kind, split = [], [], defaultdict(list), defaultdict(list)
    for tid in ids:
        task = gold[tid]
        g = answer_set(task.answer)
        p = answer_set(predictions[tid]) if tid in predictions else frozenset()
        # Reference: score from copying the answer on the noisy observed graph; if the two differ, the task is affected by noise.
        n = answer_set(task.meta.get("noise_answer"))
        group = "noise_unaffected" if n == g else "noise_affected"
        item = {"id": tid, "kind": task.kind, "ok": p == g, "f1": f1(p, g), "gold": task.answer, "group": group}
        items.append(item)
        by_kind[task.kind].append(item)
        noise.append({"ok": n == g, "f1": f1(n, g)})
        split[group].append((item, noise[-1]))
    metrics = {**summarize(items), "missing": sum(tid not in predictions for tid in ids),
               "by_kind": {k: {"n": len(v), **summarize(v)} for k, v in sorted(by_kind.items())}}
    # Split by whether noise changes the answer: only affected tasks test denoising.
    reference = {"noisy_graph_answer": summarize(noise)}
    for group in ("noise_affected", "noise_unaffected"):
        rows = split[group]
        ours, noisy = summarize([r[0] for r in rows]), summarize([r[1] for r in rows])
        metrics[f"n_{group}"] = reference["noisy_graph_answer"][f"n_{group}"] = len(rows)
        for key in ("answer_set_em", "answer_set_f1"):
            metrics[f"{key[11:]}_{group}"] = ours[key]
            reference["noisy_graph_answer"][f"{key[11:]}_{group}"] = noisy[key]
    return {"metrics": metrics, "items": items, "reference": reference}


@cache
def noise_truth(clean_path, perturbed_path) -> dict:
    """Noise ground truth from an item-by-item diff of the clean and perturbed graphs; ids and keys are compared as str."""
    with open(clean_path, "rb") as fh:
        clean = pickle.load(fh)
    with open(perturbed_path, "rb") as fh:
        noisy = pickle.load(fh)
    ce = {(str(u), str(v), str(k)): a.get("label") for u, v, k, a in clean.edges(keys=True, data=True)}
    ne = {(str(u), str(v), str(k)): a.get("label") for u, v, k, a in noisy.edges(keys=True, data=True)}
    fields = {(str(n), key) for n, attrs in clean.nodes(data=True)
              for key, value in attrs.items() if noisy.nodes[n].get(key) != value}
    return {
        "node_label": {n for n, key in fields if key == "label"},
        "node_attr": {n for n, _ in fields},
        "node_attr_field": fields,
        "added": set(ne.keys() - ce.keys()),
        "relabel": {e for e in ce.keys() & ne.keys() if ce[e] != ne[e]},
        "deleted": {(u, v, ce[(u, v, k)]) for u, v, k in ce.keys() - ne.keys()},
    }


def prf(asserted: set, truth: set) -> dict:
    hit = len(asserted & truth)
    p, r = hit / max(1, len(asserted)), hit / max(1, len(truth))
    return {"n_asserted": len(asserted), "n_true": len(truth), "precision": p, "recall": r,
            "f1": 2 * p * r / (p + r) if hit else 0.0}


@register_knowledge("ngdbench")
def score_knowledge(ws, state, ds) -> dict:
    """Per-category precision / recall / F1 of `stages/4_decide/noise.jsonl` (one noise claim per line)."""
    path = ws / "stages/4_decide/noise.jsonl"
    if not path.exists():
        return {"noise": {"reported": False}}
    truth = noise_truth(ds.files["clean"], ds.files["perturbed"])
    rows = defaultdict(list)
    for row in load_units(path):
        rows[row["kind"]].append(row)
    edges = {(str(r["src"]), str(r["dst"]), str(r["key"])): r.get("type") for r in rows["edge"]}
    return {"noise": {
        "reported": True,
        "node_label": prf({str(r["node"]) for r in rows["node_label"]}, truth["node_label"]),
        "node_attr": prf({str(r["node"]) for r in rows["node_attr"]}, truth["node_attr"]),
        "node_attr_field": prf({(str(r["node"]), r["field"]) for r in rows["node_attr"] if r.get("field")},
                               truth["node_attr_field"]),
        "edge": prf(set(edges), truth["added"] | truth["relabel"]),
        **{f"edge_{t}": prf({e for e, kind in edges.items() if kind == t}, truth[t]) for t in ("added", "relabel")},
        "missing_edge": prf({(str(r["src"]), str(r["dst"]), r["label"]) for r in rows["missing_edge"]},
                            truth["deleted"]),
    }}
