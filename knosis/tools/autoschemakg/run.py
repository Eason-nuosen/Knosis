"""Text -> knowledge graph (AutoSchemaKG pipeline): chunk -> triple extraction (agent or --llm command) -> build graph -> conceptualize (schema induction).

The triple extraction prompts are verbatim from AutoSchemaKG `atlas_rag/llm_generator/prompt/triple_extraction_prompt.py` (MIT);
the conceptualization prompt merges the upstream entity / event / relation prompts, with few-shot examples removed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import networkx as nx

from knosis.data.loaders.text import SUFFIXES, chunk
from knosis import lang
from knosis.tools import write_result

SYSTEM = "You are a helpful assistant who always response in a valid array of JSON objects without any explanation"
TRIPLE_PROMPTS = {
    "entity_relation": """Given a passage, summarize all the important entities and the relations between them in a concise manner. Relations should briefly capture the connections between entities, without repeating information from the head and tail entities. The entities should be as specific as possible. Exclude pronouns from being considered as entities.
You must **strictly output in the following JSON format**:
[
    {
        "Head": "{a noun}",
        "Relation": "{a verb}",
        "Tail": "{a noun}",
    }...
]
Here is the passage:""",
    "event_entity": """Please analyze and summarize the participation relations between the events and entities in the given paragraph. Each event is a single independent sentence. Additionally, identify all the entities that participated in the events. Do not use ellipses.
You must **strictly output in the following JSON format**:
[
    {
        "Event": "{a simple sentence describing an event}",
        "Entity": ["entity 1", "entity 2", "..."]
    }...
]
Here is the passage:""",
    "event_relation": """Please analyze and summarize the relationships between the events in the paragraph. Each event is a single independent sentence. Identify temporal and causal relationships between the events using the following types: before, after, at the same time, because, and as a result. Each extracted triple should be specific, meaningful, and able to stand alone.  Do not use ellipses.
You must **strictly output in the following JSON format**:
[
    {
        "Head": "{a simple sentence describing the event 1}",
        "Relation": "{temporal or causality relation between the events}",
        "Tail": "{a simple sentence describing the event 2}"
    }...
]
Here is the passage:""",
}
CONCEPT_PROMPT = """I will give you an {kind}. You need to give several phrases containing 1-2 words for the ABSTRACT {kind} of this {kind}.
You must return your answer in the following format: phrases1, phrases2, phrases3,...
You can't return anything other than answers.
These abstract words should fulfill the following requirements.
1. The ABSTRACT {kind} phrases can well represent the {kind}, and it could be the type of the {kind} or the related concepts of the {kind}.
2. Strictly follow the provided format, do not add extra characters or words.
3. Write at least 3 or more phrases at different abstract level if possible.
4. Do not repeat the same word and the input in the answer.
5. Stop immediately if you can't think of any more phrases, and no explanation is needed.

{kind}: {name}
CONTEXT: {context}
Your answer:"""
KEYS = {"entity_relation": "entity_relation_dict", "event_entity": "event_entity_dict", "event_relation": "event_relation_dict"}
VERSION = "0.1"


# ---------------------------------------------------------------- chunking


def prepare(paths, out: Path, chunk_chars: int, overlap: int) -> list[dict]:
    """Text file / directory -> passages.jsonl (id, source, text). Pass a `data/...` path relative to the workspace so ws check can locate sources."""
    passages = []
    for root in map(Path, paths):
        files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES) if root.is_dir() else [root]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for start, end in chunk(text, chunk_chars, overlap):
                if text[start:end].strip():
                    passages.append({"id": f"p{len(passages) + 1}", "source": f"{path.as_posix()}#{start}-{end}",
                                     "text": text[start:end]})
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "passages.jsonl", passages)
    (out / "PROMPTS.md").write_text(prompts_markdown(len(passages)), encoding="utf-8")
    return passages


def prompts_markdown(n) -> str:
    parts = [lang.t(f"# Extraction prompts (AutoSchemaKG)\n\n`passages.jsonl` has {n} passages. For each passage run the three prompts below in turn (passage text appended after the prompt),"
                    " and combine the three JSON arrays into one line of `extractions.jsonl`:\n\n"
                    '`{"id": "<passage id>", "entity_relation_dict": [...], "event_entity_dict": [...], "event_relation_dict": [...]}`\n\n'
                    f"System prompt: {SYSTEM}\n\nWrite only what the passage says; do not add external knowledge.",
                    f"# 抽取提示词（AutoSchemaKG）\n\n`passages.jsonl` 共 {n} 段。对每一段依次执行下面三个提示词（段落正文接在提示词后），"
                    "把三个 JSON 数组合成 `extractions.jsonl` 的一行：\n\n"
                    '`{"id": "<段 id>", "entity_relation_dict": [...], "event_entity_dict": [...], "event_relation_dict": [...]}`\n\n'
                    f"系统提示：{SYSTEM}\n\n只写段落里说了的内容，不要补充外部知识。")]
    parts += [f"## {name} → `{KEYS[name]}`\n\n```text\n{text}\n```" for name, text in TRIPLE_PROMPTS.items()]
    return "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------- automatic extraction (optional)


def ask(command, prompt) -> str:
    result = subprocess.run(shlex.split(command), input=prompt, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError(f"{command} exited with {result.returncode}: {result.stderr[-500:]}")
    return result.stdout


def parse_array(text) -> list:
    """The JSON array in LLM output; tolerates surrounding code fences or prose, returns empty if unparsable."""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def extract(passages, command) -> list[dict]:
    rows = []
    for passage in passages:
        row = {"id": passage["id"]}
        for name, prompt in TRIPLE_PROMPTS.items():
            row[KEYS[name]] = parse_array(ask(command, f"{SYSTEM}\n\n{prompt}\n{passage['text']}"))
        rows.append(row)
        print(f"{passage['id']}: " + ", ".join(f"{k}={len(row[k])}" for k in KEYS.values()), file=sys.stderr)
    return rows


# ---------------------------------------------------------------- graph building


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def grounded(name, passage_text) -> bool:
    return bool(norm(name)) and norm(name) in norm(passage_text)


def clean_items(items, keys) -> list[dict]:
    """Drop items with missing or non-string fields (common in truncated LLM output)."""
    out = []
    for item in items or []:
        if isinstance(item, dict) and all(isinstance(item.get(k), (str, list)) and item.get(k) for k in keys):
            out.append(item)
    return out


def build_graph(extractions, passages: dict) -> tuple[nx.DiGraph, list[dict]]:
    """Same structure as AutoSchemaKG's json_to_graphml: entity / event / passage nodes; three edge types (entity relation, event relation,
    event-entity "is participated by"), plus mention in edges from entities and events to their passages."""
    g, edges = nx.DiGraph(), []

    def node(name, kind, pid):
        key = f"{kind}:{name.strip()}"
        if key not in g:
            g.add_node(key, id=name.strip(), type=kind, passages="")
        g.nodes[key]["passages"] = ",".join(sorted(set(filter(None, g.nodes[key]["passages"].split(","))) | {pid}))
        g.add_edge(key, f"passage:{pid}", relation="mention in", kind="mention")
        return key

    def edge(h, relation, t, kind, pid, text):
        g.add_edge(h, t, relation=relation.strip(), kind=kind, passage=pid)
        edges.append({"head": g.nodes[h]["id"], "relation": relation.strip(), "tail": g.nodes[t]["id"], "kind": kind,
                      "passage": pid, "grounded": grounded(g.nodes[h]["id"], text) and grounded(g.nodes[t]["id"], text)})

    for row in extractions:
        pid = str(row["id"])
        text = passages.get(pid, {}).get("text", "")
        g.add_node(f"passage:{pid}", id=pid, type="passage", source=passages.get(pid, {}).get("source", ""))
        for item in clean_items(row.get("entity_relation_dict"), ("Head", "Relation", "Tail")):
            edge(node(item["Head"], "entity", pid), item["Relation"], node(item["Tail"], "entity", pid), "entity_relation", pid, text)
        for item in clean_items(row.get("event_entity_dict"), ("Event", "Entity")):
            event = node(item["Event"], "event", pid)
            for name in item["Entity"] if isinstance(item["Entity"], list) else [item["Entity"]]:
                if isinstance(name, str) and name.strip():
                    g.add_edge(event, node(name, "entity", pid), relation="is participated by", kind="event_entity", passage=pid)
        for item in clean_items(row.get("event_relation_dict"), ("Head", "Relation", "Tail")):
            edge(node(item["Head"], "event", pid), item["Relation"], node(item["Tail"], "event", pid), "event_relation", pid, text)
    return g, edges


def concept_todo(g, limit) -> list[dict]:
    """Nodes to conceptualize: highest-degree entities / events and most frequent relations, with context (AutoSchemaKG's conceptualization prompt needs CONTEXT)."""
    def context(key):
        rels = [f"{d['relation']} {g.nodes[t]['id']}" for _, t, d in g.out_edges(key, data=True) if d.get("kind") != "mention"]
        return "; ".join(rels[:3])

    nodes = sorted((k for k, d in g.nodes(data=True) if d["type"] in ("entity", "event")), key=lambda k: -g.degree(k))
    todo = [{"name": g.nodes[k]["id"], "type": g.nodes[k]["type"], "context": context(k)} for k in nodes[:limit]]
    relations = Counter(d["relation"] for _, _, d in g.edges(data=True) if d.get("kind") in ("entity_relation", "event_relation"))
    todo += [{"name": r, "type": "relation", "context": ""} for r, _ in relations.most_common(limit // 4 or 1)]
    for item in todo:
        item["prompt"] = CONCEPT_PROMPT.format(kind=item["type"].upper(), name=item["name"], context=item["context"])
    return todo


def apply_concepts(g, concepts) -> dict:
    """Write concepts onto nodes / relations and return the concept-level schema: concept member counts and frequencies of (head concept, relation concept, tail concept) patterns."""
    by_name = {(c["type"], norm(c["name"])): [x.strip() for x in c["concepts"] if x.strip()] for c in concepts}
    for _, d in g.nodes(data=True):
        if (d["type"], norm(d["id"])) in by_name:
            d["concept"] = ",".join(by_name[d["type"], norm(d["id"])])
    members, patterns = Counter(), Counter()
    for _, d in g.nodes(data=True):
        for c in filter(None, d.get("concept", "").split(",")):
            members[c] += 1
    for h, t, d in g.edges(data=True):
        if d.get("kind") != "entity_relation":
            continue
        hc, tc = g.nodes[h].get("concept", ""), g.nodes[t].get("concept", "")
        rc = by_name.get(("relation", norm(d["relation"])), [d["relation"]])
        if hc and tc:
            patterns[hc.split(",")[0], rc[0], tc.split(",")[0]] += 1
    return {"concepts": dict(members.most_common()),
            "patterns": [{"head": h, "relation": r, "tail": t, "count": n} for (h, r, t), n in patterns.most_common()]}


def to_units(g, edges, passages, schema, max_units, params) -> list[dict]:
    tool = f"tool:autoschemakg@{VERSION}({params})"
    kinds = Counter(d["type"] for _, d in g.nodes(data=True))
    relations = Counter(e["relation"] for e in edges if e["kind"] == "entity_relation")
    sources = sorted({p["source"].split("#", 1)[0] for p in passages.values() if p.get("source")})
    ok = sum(e["grounded"] for e in edges if e["kind"] == "entity_relation")
    n_er = sum(e["kind"] == "entity_relation" for e in edges)
    units = [{
        "id": "autoschemakg/graph", "form": "schema", "status": "inferred", "scope": "dataset",
        "content": lang.t(f"Text KG: {kinds['entity']} entities, {kinds['event']} events, {kinds['passage']} passages; "
                          f"{n_er} entity relations ({ok / max(n_er, 1):.0%} with head and tail appearing verbatim in the source passage), "
                          f"most common relations: {', '.join(r for r, _ in relations.most_common(8))}",
                          f"文本 KG：{kinds['entity']} 个实体、{kinds['event']} 个事件、{kinds['passage']} 段；"
                          f"实体关系 {n_er} 条（头尾逐字出现在原段落的占 {ok / max(n_er, 1):.0%}），"
                          f"最常见关系：{', '.join(r for r, _ in relations.most_common(8))}"),
        "condition": lang.t("LLM extraction, not checked one by one", "LLM 抽取，未逐条核对"), "provenance": " ; ".join([tool, *sources]),
        "meta": {"nodes": dict(kinds), "edges": g.number_of_edges(), "relations": dict(relations.most_common(20))},
    }]
    degree = {d["id"]: g.degree(k) for k, d in g.nodes(data=True) if d["type"] == "entity"}
    ranked = sorted((e for e in edges if e["kind"] == "entity_relation"), key=lambda e: (-degree.get(e["head"], 0), e["passage"]))
    seen = set()
    for e in ranked:
        key = (norm(e["head"]), norm(e["relation"]), norm(e["tail"]))
        if key in seen:
            continue
        seen.add(key)
        if len(seen) > max_units:
            break
        source = passages.get(e["passage"], {}).get("source") or f"passage:{e['passage']}"
        units.append({
            "id": f"autoschemakg/er/{len(seen)}", "form": "finding", "status": "inferred", "scope": "relation",
            "content": f"{e['head']} —{e['relation']}→ {e['tail']}",
            "condition": lang.t("extracted by an LLM from this passage", "LLM 从该段抽取") + ("" if e["grounded"] else lang.t(
                "; the head or tail entity does not appear verbatim in the source, possibly a paraphrase or hallucination",
                "；头或尾实体未逐字出现在原文，可能是改写或幻觉")),
            "provenance": f"{tool} ; {source}", "meta": e,
        })
    for i, p in enumerate(schema.get("patterns", [])[:20]):
        units.append({
            "id": f"autoschemakg/schema/{i + 1}", "form": "schema", "status": "inferred", "scope": "dataset",
            "content": lang.t(f"Concept-level pattern: {p['head']} —{p['relation']}→ {p['tail']} ({p['count']} instances)",
                              f"概念层模式：{p['head']} —{p['relation']}→ {p['tail']}（{p['count']} 条实例）"),
            "condition": lang.t("induced by conceptualization, taking each node's first concept",
                                "由概念化归纳，概念取每个节点的第一个概念"), "provenance": " ; ".join([tool, *sources]), "meta": p,
        })
    return units


def build(directory: Path, extractions_path: Path, concepts_path: Path, max_units, concept_limit) -> dict:
    passages = {p["id"]: p for p in read_jsonl(directory / "passages.jsonl")} if (directory / "passages.jsonl").exists() else {}
    extractions = read_jsonl(extractions_path)
    for i, row in enumerate(extractions):
        # Upstream extraction file: passage text is in original_text and ids are per-document (they repeat across documents), so use line numbers.
        row["id"] = f"line{i + 1}" if row.get("original_text") else str(row.get("id", i + 1))
        if row["id"] not in passages and row.get("original_text"):
            passages[row["id"]] = {"id": row["id"], "source": f"{extractions_path.as_posix()}#line/{i + 1}", "text": row["original_text"]}
    g, edges = build_graph(extractions, passages)
    schema = apply_concepts(g, read_jsonl(concepts_path)) if concepts_path.exists() else {}
    nx.write_graphml(g, directory / "graph.graphml")
    with (directory / "nodes.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "type", "degree", "concept", "passages"])
        for k, d in g.nodes(data=True):
            if d["type"] != "passage":
                writer.writerow([d["id"], d["type"], g.degree(k), d.get("concept", ""), d.get("passages", "")])
    with (directory / "edges.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["head", "relation", "tail", "kind", "passage", "grounded"])
        writer.writeheader()
        writer.writerows(edges)
    write_jsonl(directory / "concept_todo.jsonl", concept_todo(g, concept_limit))
    if schema:
        (directory / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=1), encoding="utf-8")
    units = to_units(g, edges, passages, schema, max_units, f"build,max_units={max_units}")
    return {"graph": g, "edges": edges, "schema": schema, "units": units}


def query(directory: Path, needle, hops) -> list[str]:
    g = nx.read_graphml(directory / "graph.graphml")
    starts = [k for k, d in g.nodes(data=True) if d.get("type") != "passage" and needle.lower() in d.get("id", "").lower()]
    lines, frontier, seen = [], set(starts), set(starts)
    for _ in range(hops):
        nxt = set()
        for k in frontier:
            for h, t, d in [*g.out_edges(k, data=True), *g.in_edges(k, data=True)]:
                if d.get("kind") == "mention":
                    continue
                lines.append(f"{g.nodes[h]['id']} —{d['relation']}→ {g.nodes[t]['id']}  [{d.get('passage', '')}]")
                nxt |= {h, t} - seen
        seen |= nxt
        frontier = nxt
    return list(dict.fromkeys(lines))


# ---------------------------------------------------------------- CLI


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows) -> None:
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="chunk text and write the extraction prompts")
    p.add_argument("--text", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--chunk-chars", type=int, default=3000)
    p.add_argument("--overlap", type=int, default=0)
    e = sub.add_parser("extract", help="extract automatically with the --llm command (reads the prompt from stdin)")
    e.add_argument("--dir", required=True)
    e.add_argument("--llm", required=True, help="e.g. 'claude -p' or 'codex exec --skip-git-repo-check -'")
    e.add_argument("--limit", type=int, help="extract only the first n passages")
    c = sub.add_parser("conceptualize", help="write concepts for concept_todo.jsonl with the --llm command")
    c.add_argument("--dir", required=True)
    c.add_argument("--llm", required=True)
    b = sub.add_parser("build", help="build the graph and write κ; also induce the concept-level schema if concepts.jsonl exists")
    b.add_argument("--dir", required=True)
    b.add_argument("--extractions", help="default <dir>/extractions.jsonl; may also be an upstream AutoSchemaKG extraction file")
    b.add_argument("--max-units", type=int, default=200)
    b.add_argument("--concept-limit", type=int, default=100)
    q = sub.add_parser("query", help="look up node neighbors by name substring")
    q.add_argument("--dir", required=True)
    q.add_argument("--node", required=True)
    q.add_argument("--hops", type=int, default=1)
    args = parser.parse_args(argv)
    started = time.monotonic()

    if args.cmd == "prepare":
        passages = prepare(args.text, Path(args.out), args.chunk_chars, args.overlap)
        print(f"{len(passages)} passages -> {Path(args.out) / 'passages.jsonl'}; prompts: {Path(args.out) / 'PROMPTS.md'}")
    elif args.cmd == "extract":
        directory = Path(args.dir)
        passages = read_jsonl(directory / "passages.jsonl")[:args.limit]
        write_jsonl(directory / "extractions.jsonl", extract(passages, args.llm))
        print(f"{len(passages)} passages extracted -> {directory / 'extractions.jsonl'}")
    elif args.cmd == "conceptualize":
        directory = Path(args.dir)
        rows = []
        for item in read_jsonl(directory / "concept_todo.jsonl"):
            answer = ask(args.llm, item["prompt"]).strip().splitlines()
            rows.append({"name": item["name"], "type": item["type"], "concepts": answer[-1].split(",") if answer else []})
        write_jsonl(directory / "concepts.jsonl", rows)
        print(f"{len(rows)} concepts -> {directory / 'concepts.jsonl'}")
    elif args.cmd == "build":
        directory = Path(args.dir)
        result = build(directory, Path(args.extractions or directory / "extractions.jsonl"), directory / "concepts.jsonl",
                       args.max_units, args.concept_limit)
        write_result(directory, "autoschemakg", vars(args), result["units"], started)
        g = result["graph"]
        print(f"{g.number_of_nodes()} nodes, {g.number_of_edges()} edges, {len(result['units'])} units -> {directory}"
              + (f"; schema: {len(result['schema']['concepts'])} concepts" if result["schema"] else ""))
    else:
        print("\n".join(query(Path(args.dir), args.node, args.hops)) or "no match")


if __name__ == "__main__":
    main()
