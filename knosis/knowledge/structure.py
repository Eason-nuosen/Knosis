"""Forms of the knowledge structure: five ways to organize the same knowledge units (κ / skills / ontology units); all organize, none add assertions.

| Form | File | Produced by | Answers |
| --- | --- | --- | --- |
| Outline (tree) | `kb/outline.yaml` | agent (organize) | what blocks the knowledge falls into and what each covers (see `outline`) |
| Knowledge graph | `kb/graph.json` | agent (structure) | which objects exist in the environment and how they relate |
| Flowchart | `kb/flows/<name>.json` | agent (structure) | for a task type: which steps, where to decide, which knowledge to use |
| Derivation graph | (computed) | Knosis | which knowledge is derived from, merged into or superseded by which |
| Rule / formula cards | (computed) | Knosis | which rules and formulas hold on each object |

Knowledge graph:

    {"entities": [{"id": "table:orders", "type": "table", "label": "orders", "units": ["extract/orders-key"]}],
     "relations": [{"src": "table:orders", "rel": "references", "dst": "table:customers",
                    "label": "cust_id, many-to-one", "units": ["extract/orders-fk"]}]}

Entity `id`s are unique in the graph; suggested `type`s: dataset / table / column / entity_type / variable / concept / metric / tool / task.
Every relation cites at least one active unit (the edge is what those units state) and its endpoints must exist; entities cite the units
describing them, and an entity without citations must be an endpoint of some edge.

Flowchart:

    {"name": "find-grain", "title": "Determine the grain of a table", "goal": "...",
     "nodes": [{"id": "start", "kind": "start", "text": "Get a new table"},
               {"id": "count", "kind": "step", "text": "Group by candidate key and count", "units": ["method/grain-check"]},
               {"id": "dup", "kind": "decision", "text": "Duplicates?", "units": ["..."]},
               {"id": "end", "kind": "end", "text": "Record the grain"}],
     "edges": [{"src": "start", "dst": "count"}, {"src": "dup", "dst": "end", "label": "no"}, ...]}

`kind` is start / step / check / decision / end; exactly one start, at least one end, every node reachable from start,
at least two outgoing edges per decision; step / check / decision cite at least one active unit or `skill:<name>`.

When a cited unit is retracted, stale or merged, `check` reports it and the next structure step updates it.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..lang import t
from .layout import layout
from .units import INACTIVE, load_units

GRAPH = "graph.json"
FLOWS = "flows"
ENTITY_TYPES = ("dataset", "table", "column", "entity_type", "variable", "concept", "metric", "tool", "task", "file")
NODE_KINDS = ("start", "step", "check", "decision", "end")
OBJECT_SCOPES = ("instance", "relation", "dataset")


def graph_path(base) -> Path:
    return layout(base).kb / GRAPH


def flows_dir(base) -> Path:
    return layout(base).kb / FLOWS


def load_graph(base) -> dict | None:
    path = graph_path(base)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_flows(base) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) | {"file": p.name} for p in sorted(flows_dir(base).glob("*.json"))]


def items(base) -> dict[str, dict]:
    from .outline import members

    return members(base)


def dead(item) -> bool:
    return item.get("status") in INACTIVE


def check_refs(where, refs, known, issues, required=True) -> None:
    refs = refs or []
    if required and not refs:
        issues.append(f"structure {where}: cites no unit")
    for uid in refs:
        if uid not in known:
            issues.append(f"structure {where}: unknown unit {uid}")
        elif dead(known[uid]):
            issues.append(f"structure {where}: cites inactive unit {uid} ({known[uid].get('status')})")


def check_graph(graph, known) -> list[str]:
    if not isinstance(graph, dict):
        return ["structure graph: not a JSON object"]
    issues, ids = [], Counter(e.get("id") for e in graph.get("entities", []))
    issues += [f"structure graph: duplicate entity {i}" for i, n in ids.items() if n > 1]
    endpoints = set()
    for k, rel in enumerate(graph.get("relations", [])):
        where = f"graph relation {rel.get('src')} -{rel.get('rel')}-> {rel.get('dst')}"
        if not rel.get("rel"):
            issues.append(f"structure graph relation #{k}: missing rel")
        for end in ("src", "dst"):
            if rel.get(end) not in ids:
                issues.append(f"structure {where}: unknown entity {rel.get(end)}")
            endpoints.add(rel.get(end))
        check_refs(where, rel.get("units"), known, issues)
    for e in graph.get("entities", []):
        if not e.get("id") or not e.get("label"):
            issues.append(f"structure graph entity {e.get('id', '?')}: missing id or label")
        check_refs(f"graph entity {e.get('id')}", e.get("units"), known, issues, required=e.get("id") not in endpoints)
    return issues


def check_flow(flow, known) -> list[str]:
    name = flow.get("name") or flow.get("file", "?")
    issues = []
    if not flow.get("title"):
        issues.append(f"structure flow {name}: missing title")
    nodes = {n.get("id"): n for n in flow.get("nodes", [])}
    if len(nodes) != len(flow.get("nodes", [])):
        issues.append(f"structure flow {name}: duplicate node id")
    if len(nodes) < 3:
        issues.append(f"structure flow {name}: needs at least 3 nodes")
    kinds = Counter(n.get("kind") for n in nodes.values())
    issues += [f"structure flow {name} node {i}: kind must be one of {', '.join(NODE_KINDS)}"
               for i, n in nodes.items() if n.get("kind") not in NODE_KINDS]
    if kinds["start"] != 1:
        issues.append(f"structure flow {name}: needs exactly one start node")
    if kinds["end"] < 1:
        issues.append(f"structure flow {name}: needs at least one end node")
    out = {i: [] for i in nodes}
    for e in flow.get("edges", []):
        if e.get("src") not in nodes or e.get("dst") not in nodes:
            issues.append(f"structure flow {name}: edge {e.get('src')} -> {e.get('dst')} has an unknown end")
        else:
            out[e["src"]].append(e["dst"])
    start = next((i for i, n in nodes.items() if n.get("kind") == "start"), None)
    seen, todo = set(), [start] if start else []
    while todo:
        cur = todo.pop()
        if cur not in seen:
            seen.add(cur)
            todo += out.get(cur, [])
    if start and set(nodes) - seen:
        issues.append(f"structure flow {name}: unreachable nodes {', '.join(sorted(set(nodes) - seen))}")
    for i, n in nodes.items():
        if n.get("kind") == "decision" and len(out[i]) < 2:
            issues.append(f"structure flow {name} node {i}: a decision needs at least two outgoing edges")
        if n.get("kind") in ("step", "check", "decision"):
            check_refs(f"flow {name} node {i}", n.get("units"), known, issues)
        if not n.get("text"):
            issues.append(f"structure flow {name} node {i}: missing text")
    return issues


def check_structure(base) -> list[str]:
    """Structural issues of the knowledge graph and flowcharts (missing files are not reported)."""
    known = items(base)
    issues = []
    if graph_path(base).exists():
        try:
            issues += check_graph(load_graph(base), known)
        except json.JSONDecodeError as error:
            issues.append(f"structure graph: invalid JSON ({error})")
    for path in sorted(flows_dir(base).glob("*.json")) if flows_dir(base).is_dir() else []:
        try:
            issues += check_flow(json.loads(path.read_text(encoding="utf-8")) | {"file": path.name}, known)
        except json.JSONDecodeError as error:
            issues.append(f"structure flow {path.name}: invalid JSON ({error})")
    return issues


def namespaces(base) -> dict:
    """Datasets merged in via `kb merge --namespace`: {prefix: {workspace, benchmark, scenario}}; empty for a single-source knowledge layer."""
    path = layout(base).kb / "sources.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def unit_namespaces(base) -> dict[str, set[str]]:
    """Which datasets each unit comes from: by id prefix; unprefixed units (induced units created after merging) follow derived_from."""
    names = set(namespaces(base))
    known = items(base)
    out = {}

    def resolve(uid, seen=()):
        if uid in out:
            return out[uid]
        head = uid[6:].split("-", 1)[0] if uid.startswith("skill:") else uid.split("/", 1)[0]
        if head in names:
            found = {head}
        elif uid in seen:
            found = set()
        else:
            found = set().union(*[resolve(p, seen + (uid,)) for p in known.get(uid, {}).get("derived_from", [])] or [set()])
        out[uid] = found
        return found

    for uid in known:
        resolve(uid)
    return out


def bridges(base) -> list[dict]:
    """Cross-dataset bridges: entities whose own or adjacent relations' units come from at least two datasets."""
    graph = load_graph(base) or {"entities": [], "relations": []}
    ns = unit_namespaces(base)
    out = []
    for e in graph["entities"]:
        sets = set().union(*[ns.get(u, set()) for u in e.get("units", [])] or [set()])
        if len(sets) >= 2:
            out.append({**e, "datasets": sorted(sets)})
    return out


def cross_induced(base) -> list[str]:
    """Active induced units created after merging whose sources span at least two datasets."""
    ns, known = unit_namespaces(base), items(base)
    names = set(namespaces(base))
    return [uid for uid, u in known.items() if not dead(u) and u.get("derived_from") and len(ns.get(uid, ())) >= 2
            and uid.split("/", 1)[0] not in names]


def cited(base) -> set[str]:
    graph = load_graph(base) or {}
    out = {u for x in graph.get("entities", []) + graph.get("relations", []) for u in x.get("units", [])}
    for flow in load_flows(base) if flows_dir(base).is_dir() else []:
        out |= {u for n in flow.get("nodes", []) for u in n.get("units", [])}
    return out


def coverage(base) -> dict:
    """Share of active object knowledge cited by the graph; share of procedure / method units and skills cited by flowcharts."""
    known = items(base)
    graph = load_graph(base) or {}
    in_graph = {u for x in graph.get("entities", []) + graph.get("relations", []) for u in x.get("units", [])}
    in_flows = {u for f in (load_flows(base) if flows_dir(base).is_dir() else []) for n in f.get("nodes", [])
                for u in n.get("units", [])}
    live = [u for u in known.values() if not dead(u) and not u["id"].startswith("ontology/")]
    objects = [u["id"] for u in live if u.get("scope") in OBJECT_SCOPES or (u.get("scope") is None and u.get("form") != "skill")]
    procedural = [u["id"] for u in live if u.get("form") in ("procedure", "skill") or u.get("scope") == "method"]
    ratio = lambda part, whole: round(len(set(part) & set(whole)) / len(whole), 3) if whole else 1.0  # noqa: E731
    multi = len(namespaces(base)) >= 2
    return {"objects": len(objects), "graph": ratio(in_graph, objects), "procedural": len(procedural),
            **({"datasets": len(namespaces(base)), "bridges": len(bridges(base))} if multi else {}),
            "flows": ratio(in_flows, procedural), "entities": len(graph.get("entities", [])),
            "relations": len(graph.get("relations", [])), "n_flows": len(load_flows(base)) if flows_dir(base).is_dir() else 0}


def derivation(base) -> dict:
    """Derivation graph: nodes are units, edges come from derived_from / merged_into / superseded_by / conflicts_with."""
    units = {u["id"]: u for u in load_units(layout(base).units)}
    edges = []
    for uid, u in units.items():
        edges += [{"src": p, "dst": uid, "kind": "derived"} for p in u.get("derived_from", []) if p in units]
        if u.get("merged_into") in units:
            edges.append({"src": uid, "dst": u["merged_into"], "kind": "merged"})
        if u.get("superseded_by") in units:
            edges.append({"src": uid, "dst": u["superseded_by"], "kind": "superseded"})
        edges += [{"src": uid, "dst": c, "kind": "conflict"} for c in u.get("conflicts_with", []) if c in units and uid < c]
    linked = {e["src"] for e in edges} | {e["dst"] for e in edges}
    return {"nodes": sorted(linked), "edges": edges}


def cards(base) -> list[dict]:
    """Rule / formula cards: active rule and formula units grouped by the graph entities citing them; those not in the graph go under "其他"."""
    units = [u for u in load_units(layout(base).units) if u.get("form") in ("rule", "formula") and not dead(u)]
    graph = load_graph(base) or {}
    owner = {}
    labels = {e["id"]: e.get("label", e["id"]) for e in graph.get("entities", [])}
    for e in graph.get("entities", []):
        for uid in e.get("units", []):
            owner.setdefault(uid, e["id"])
    for r in graph.get("relations", []):
        for uid in r.get("units", []):
            owner.setdefault(uid, r["src"])
    groups = {}
    for u in units:
        key = owner.get(u["id"], "")
        groups.setdefault(key, []).append({"id": u["id"], "form": u["form"], "content": u["content"],
                                           "condition": u.get("condition", ""), "status": u["status"]})
    return [{"entity": k, "label": labels.get(k, t("Other", "其他")), "units": v} for k, v in sorted(groups.items(), key=lambda x: (x[0] == "", x[0]))]


def summary(base) -> str:
    """Text summary for humans and agents."""
    graph, cov = load_graph(base), coverage(base)
    lines = [(t(f"Knowledge graph: {cov['entities']} entities, {cov['relations']} relations, citing {cov['graph']:.0%} of active object "
                f"knowledge ({cov['objects']} units)",
                f"知识图谱：{cov['entities']} 个实体、{cov['relations']} 条关系，引用了 {cov['graph']:.0%} 的活跃对象知识（{cov['objects']} 条）")
              if graph else t("Knowledge graph: none yet (kb/graph.json)", "知识图谱：还没有（kb/graph.json）")),
             t(f"Flowcharts: {cov['n_flows']}, citing {cov['flows']:.0%} of procedure / method / skill ({cov['procedural']} units)",
               f"流程图：{cov['n_flows']} 张，引用了 {cov['flows']:.0%} 的 procedure / method / skill（{cov['procedural']} 条）")]
    if graph:
        types = Counter(e.get("type", "?") for e in graph.get("entities", []))
        rels = Counter(r.get("rel") for r in graph.get("relations", []))
        lines.append(t("Entity types: ", "实体类型：") + t(", ", "，").join(f"{k} {v}" for k, v in types.most_common()))
        lines.append(t("Relations: ", "关系：") + t(", ", "，").join(f"{k} {v}" for k, v in rels.most_common(12)))
    for flow in load_flows(base) if flows_dir(base).is_dir() else []:
        lines.append(t(f"- Flow {flow.get('name')}: {flow.get('title')} ({len(flow.get('nodes', []))} nodes)",
                       f"- 流程 {flow.get('name')}：{flow.get('title')}（{len(flow.get('nodes', []))} 个节点）"))
    return "\n".join(lines)


def neighbors(base, entity, depth=1) -> dict:
    """Subgraph around an entity: the entity, relations and neighbors within depth hops, and the units they cite."""
    graph = load_graph(base) or {"entities": [], "relations": []}
    ents = {e["id"]: e for e in graph["entities"]}
    hits = [i for i, e in ents.items() if entity in (i, e.get("label"))] or \
           [i for i, e in ents.items() if entity.lower() in (i + " " + e.get("label", "")).lower()]
    frontier, keep, rels = set(hits), set(hits), []
    for _ in range(depth):
        nxt = set()
        for r in graph["relations"]:
            if r["src"] in frontier or r["dst"] in frontier:
                if r not in rels:
                    rels.append(r)
                nxt |= {r["src"], r["dst"]}
        frontier = nxt - keep
        keep |= nxt
    return {"entities": [ents[i] for i in sorted(keep) if i in ents], "relations": rels}
