"""文本 → 知识图谱（AutoSchemaKG 流程）：切段 → 三元组抽取（agent 或 --llm 命令）→ 建图 → 概念化（schema 归纳）。

三元组抽取提示词逐字取自 AutoSchemaKG `atlas_rag/llm_generator/prompt/triple_extraction_prompt.py`（MIT）；
概念化提示词由上游 entity / event / relation 三个提示合并而来，去掉了少样本示例。
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


# ---------------------------------------------------------------- 切段


def prepare(paths, out: Path, chunk_chars: int, overlap: int) -> list[dict]:
    """文本文件 / 目录 → passages.jsonl（id, source, text）。传入工作区内的 `data/...` 相对路径，来源才能被 ws check 定位。"""
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
    parts = [f"# 抽取提示词（AutoSchemaKG）\n\n`passages.jsonl` 共 {n} 段。对每一段依次执行下面三个提示词（段落正文接在提示词后），"
             "把三个 JSON 数组合成 `extractions.jsonl` 的一行：\n\n"
             '`{"id": "<段 id>", "entity_relation_dict": [...], "event_entity_dict": [...], "event_relation_dict": [...]}`\n\n'
             f"系统提示：{SYSTEM}\n\n只写段落里说了的内容，不要补充外部知识。"]
    parts += [f"## {name} → `{KEYS[name]}`\n\n```text\n{text}\n```" for name, text in TRIPLE_PROMPTS.items()]
    return "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------- 自动抽取（可选）


def ask(command, prompt) -> str:
    result = subprocess.run(shlex.split(command), input=prompt, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError(f"{command} exited with {result.returncode}: {result.stderr[-500:]}")
    return result.stdout


def parse_array(text) -> list:
    """LLM 输出里的 JSON 数组；允许外层有代码块或说明文字，解析不了返回空。"""
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


# ---------------------------------------------------------------- 建图


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def grounded(name, passage_text) -> bool:
    return bool(norm(name)) and norm(name) in norm(passage_text)


def clean_items(items, keys) -> list[dict]:
    """去掉缺字段或不是字符串的项（LLM 输出常见残缺）。"""
    out = []
    for item in items or []:
        if isinstance(item, dict) and all(isinstance(item.get(k), (str, list)) and item.get(k) for k in keys):
            out.append(item)
    return out


def build_graph(extractions, passages: dict) -> tuple[nx.DiGraph, list[dict]]:
    """与 AutoSchemaKG 的 json_to_graphml 同结构：entity / event / passage 节点；实体关系、事件关系、
    事件—实体（is participated by）三类边，实体与事件到所在段落有 mention in 边。"""
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
    """待概念化的节点：度数最高的实体 / 事件与出现最多的关系，附上下文（AutoSchemaKG 的概念化提示需要 CONTEXT）。"""
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
    """把概念写到节点 / 关系上，返回概念层 schema：概念的成员数与（头概念, 关系概念, 尾概念）模式的频次。"""
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
        "content": (f"文本 KG：{kinds['entity']} 个实体、{kinds['event']} 个事件、{kinds['passage']} 段；"
                    f"实体关系 {n_er} 条（头尾逐字出现在原段落的占 {ok / max(n_er, 1):.0%}），"
                    f"最常见关系：{', '.join(r for r, _ in relations.most_common(8))}"),
        "condition": "LLM 抽取，未逐条核对", "provenance": " ; ".join([tool, *sources]),
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
            "condition": "LLM 从该段抽取" + ("" if e["grounded"] else "；头或尾实体未逐字出现在原文，可能是改写或幻觉"),
            "provenance": f"{tool} ; {source}", "meta": e,
        })
    for i, p in enumerate(schema.get("patterns", [])[:20]):
        units.append({
            "id": f"autoschemakg/schema/{i + 1}", "form": "schema", "status": "inferred", "scope": "dataset",
            "content": f"概念层模式：{p['head']} —{p['relation']}→ {p['tail']}（{p['count']} 条实例）",
            "condition": "由概念化归纳，概念取每个节点的第一个概念", "provenance": " ; ".join([tool, *sources]), "meta": p,
        })
    return units


def build(directory: Path, extractions_path: Path, concepts_path: Path, max_units, concept_limit) -> dict:
    passages = {p["id"]: p for p in read_jsonl(directory / "passages.jsonl")} if (directory / "passages.jsonl").exists() else {}
    extractions = read_jsonl(extractions_path)
    for i, row in enumerate(extractions):
        # 上游抽取文件：段落正文在 original_text 里，id 只在文档内编号（不同文档会重复），改用行号。
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


# ---------------------------------------------------------------- 命令行


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows) -> None:
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="切段并写出抽取提示词")
    p.add_argument("--text", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--chunk-chars", type=int, default=3000)
    p.add_argument("--overlap", type=int, default=0)
    e = sub.add_parser("extract", help="用 --llm 命令（从 stdin 读提示词）自动抽取")
    e.add_argument("--dir", required=True)
    e.add_argument("--llm", required=True, help="如 'claude -p' 或 'codex exec --skip-git-repo-check -'")
    e.add_argument("--limit", type=int, help="只抽前 n 段")
    c = sub.add_parser("conceptualize", help="用 --llm 命令为 concept_todo.jsonl 写概念")
    c.add_argument("--dir", required=True)
    c.add_argument("--llm", required=True)
    b = sub.add_parser("build", help="建图、写 κ；目录里有 concepts.jsonl 时一并归纳概念层 schema")
    b.add_argument("--dir", required=True)
    b.add_argument("--extractions", help="默认 <dir>/extractions.jsonl；也可以是上游 AutoSchemaKG 的抽取文件")
    b.add_argument("--max-units", type=int, default=200)
    b.add_argument("--concept-limit", type=int, default=100)
    q = sub.add_parser("query", help="按名字子串查节点的邻居")
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
