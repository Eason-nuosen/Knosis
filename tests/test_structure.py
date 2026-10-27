"""Structured forms of the knowledge system: knowledge graph, flowcharts, derivation graph, rule / formula cards, and the consolidation structure step."""

import json

from knosis.knowledge import check_knowledge, consolidate, layout, load_units, write_units
from knosis.knowledge import structure as st

from test_consolidate import base, fake_run, unit  # noqa: F401


def units():
    return [unit("orders-key", form="fact", scope="instance"), unit("orders-fk", form="schema", scope="relation"),
            unit("refund-rule", form="rule", scope="dataset"), unit("revenue", form="formula", scope="dataset"),
            unit("grain", form="procedure", scope="method"), unit("old", status="retracted"),
            unit("both", form="rule", scope="dataset", derived_from=["refund-rule", "revenue"], provenance="derived")]


GRAPH = {"entities": [{"id": "table:orders", "type": "table", "label": "orders", "units": ["orders-key", "refund-rule", "revenue"]},
                      {"id": "table:customers", "type": "table", "label": "customers"}],
         "relations": [{"src": "table:orders", "rel": "references", "dst": "table:customers", "label": "cust_id，多对一",
                        "units": ["orders-fk"]}]}
FLOW = {"name": "grain", "title": "判断表的粒度", "nodes": [
    {"id": "s", "kind": "start", "text": "新表"}, {"id": "c", "kind": "step", "text": "按键计数", "units": ["grain"]},
    {"id": "d", "kind": "decision", "text": "有重复？", "units": ["orders-key"]},
    {"id": "e1", "kind": "end", "text": "粒度是一行一单"}, {"id": "e2", "kind": "end", "text": "换候选键"}],
    "edges": [{"src": "s", "dst": "c"}, {"src": "c", "dst": "d"}, {"src": "d", "dst": "e1", "label": "否"},
              {"src": "d", "dst": "e2", "label": "是"}]}


def write(base, graph=GRAPH, flows=(FLOW,)):
    st.graph_path(base).write_text(json.dumps(graph, ensure_ascii=False))
    st.flows_dir(base).mkdir(parents=True, exist_ok=True)
    for f in flows:
        (st.flows_dir(base) / f"{f['name']}.json").write_text(json.dumps(f, ensure_ascii=False))


def test_valid_structure_and_views(base):  # noqa: F811
    write_units(layout(base).units, units())
    write(base)
    assert st.check_structure(base) == []
    cov = st.coverage(base)
    assert cov["entities"] == 2 and cov["relations"] == 1 and cov["n_flows"] == 1
    assert cov["graph"] == 4 / 5 and cov["flows"] == 1.0  # both is not referenced by the graph
    cards = st.cards(base)
    assert cards[0]["entity"] == "table:orders" and {c["id"] for c in cards[0]["units"]} == {"refund-rule", "revenue"}
    assert cards[-1]["label"] == "其他" and cards[-1]["units"][0]["id"] == "both"
    assert {(e["src"], e["dst"]) for e in st.derivation(base)["edges"]} == {("refund-rule", "both"), ("revenue", "both")}
    sub = st.neighbors(base, "customers")
    assert {e["id"] for e in sub["entities"]} == {"table:orders", "table:customers"} and len(sub["relations"]) == 1
    assert "2 个实体、1 条关系" in st.summary(base)


def test_invalid_structure(base):  # noqa: F811
    write_units(layout(base).units, units())
    bad_graph = {"entities": [{"id": "t:a", "label": "a"}, {"id": "t:a", "label": "a2"}, {"id": "t:lonely", "label": "x"}],
                 "relations": [{"src": "t:a", "rel": "joins", "dst": "t:missing", "units": []},
                               {"src": "t:a", "rel": "joins", "dst": "t:a", "units": ["old", "ghost"]}]}
    bad_flow = {"name": "f", "title": "f", "nodes": [
        {"id": "s", "kind": "start", "text": "s"}, {"id": "d", "kind": "decision", "text": "?", "units": ["grain"]},
        {"id": "x", "kind": "step", "text": "孤立"}, {"id": "e", "kind": "end", "text": "e"}],
        "edges": [{"src": "s", "dst": "d"}, {"src": "d", "dst": "e"}]}
    write(base, bad_graph, (bad_flow,))
    issues = "\n".join(st.check_structure(base))
    for needle in ("duplicate entity t:a", "unknown entity t:missing", "cites no unit", "inactive unit old",
                   "unknown unit ghost", "entity t:lonely: cites no unit", "unreachable nodes x",
                   "decision needs at least two outgoing edges", "node x: cites no unit"):
        assert needle in issues, needle
    # also part of knowledge layer checks
    assert any(i.startswith("structure") for i in check_knowledge(base, root=base))


def test_structure_step(base, monkeypatch):  # noqa: F811
    path = layout(base).units
    write_units(path, units())

    def too_thin():  # only one edge: insufficient graph coverage, no flowchart
        write(base, {"entities": GRAPH["entities"], "relations": GRAPH["relations"][:1]} | {
            "entities": [{"id": "table:orders", "type": "table", "label": "orders"}, GRAPH["entities"][1]]}, ())

    fake_run(monkeypatch, too_thin)
    result = consolidate.run_step(base, "structure")
    assert result["restored"] and any("need 60%" in i for i in result["issues"])
    assert any("no flow" in i for i in result["issues"]) and not st.graph_path(base).exists()

    def edits_units():
        write(base)
        write_units(path, [{**u, "content": "改了"} if u["id"] == "grain" else u for u in load_units(path)])

    fake_run(monkeypatch, edits_units)
    result = consolidate.run_step(base, "structure")
    assert result["restored"] and any("grain: structure must not change units" in i for i in result["issues"])

    fake_run(monkeypatch, lambda: write(base))
    result = consolidate.run_step(base, "structure")
    assert result["issues"] == [] and result["actions"] == {"structure": 1}
    logged = load_units(layout(base).actions)[-1]
    assert logged["op"] == "structure" and logged["entities"] == 2

    # then retract a referenced unit: checks report it, other consolidation steps are not responsible for it
    write_units(path, [{**u, "status": "retracted"} if u["id"] == "orders-fk" else u for u in load_units(path)])
    assert any("inactive unit orders-fk" in i for i in check_knowledge(base, root=base))
    fake_run(monkeypatch, lambda: None)
    assert consolidate.run_step(base, "dedup")["issues"] == []


def test_inherit_copies_structure_only_when_complete(tmp_path):
    from knosis.knowledge.kb import inherit, init_kb

    kb = init_kb(tmp_path / "kb")
    write_units(layout(kb).units, units())
    write(kb)
    full, part = tmp_path / "full", tmp_path / "part"
    for t in (full, part):
        (t / "kb/knowledge").mkdir(parents=True)
    inherit(kb, full)
    inherit(kb, part, ["method"])
    assert (full / "kb/graph.json").exists() and (full / "kb/flows/grain.json").exists()
    assert not (part / "kb/graph.json").exists()


def test_merge_with_namespace(tmp_path):
    """Workspaces from different datasets merged into one KB: same-name ids get prefixes instead of overwriting, references rewritten too; renaming feedback when the KB already has skills does not break the evidence ledger."""
    import json as _json

    from knosis import workspace as w
    from knosis.knowledge import add_evidence
    from knosis.knowledge.kb import init_kb, merge

    (tmp_path / "run.jsonl").write_text(_json.dumps({"role": "user", "content": "hi"}) + "\n")
    kb = init_kb(tmp_path / "kb")
    for ns in ("a", "b"):
        ws = w.init("traces", ns, tmp_path / ns, paths=str(tmp_path / "run.jsonl"))
        write_units(layout(ws).units, [unit("explore/x", content=f"{ns} 的 x", provenance="data/traces/run.json#step/1"),
                                       unit("refine/y", provenance="derived", derived_from=["explore/x"])])
        add_evidence(ws, [{"unit": "explore/x", "verdict": "support", "method": "data", "source": "data/traces/run.json#step/1"}])
        skill = layout(ws).skills / "s"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: s\ndescription: d\nwhen: w\nuses: [explore/x]\n---\n步骤\n")
        layout(ws).feedback.mkdir(parents=True, exist_ok=True)
        (layout(ws).feedback / "001-explore.json").write_text(_json.dumps({"id": "001-explore", "items": []}))
        merge(ws, kb, namespace=ns)
    got = {u["id"]: u for u in load_units(layout(kb).units)}
    assert {"a/explore/x", "b/explore/x", "a/refine/y", "b/refine/y"} <= set(got)
    assert got["b/refine/y"]["derived_from"] == ["b/explore/x"] and got["a/explore/x"]["content"] == "a 的 x"
    ledger = [_json.loads(line) for line in layout(kb).ledger.read_text().splitlines() if line.strip()]
    assert all(isinstance(e, dict) for e in ledger) and {e["unit"] for e in ledger} == {"a/explore/x", "b/explore/x"}
    assert "uses:\n- b/explore/x" in (layout(kb).skills / "b-s/SKILL.md").read_text()
    assert check_knowledge(kb) == []
    # merge records datasets; entities shared across datasets count as bridges, merged induced units find source datasets via derived_from
    assert set(st.namespaces(kb)) == {"a", "b"}
    write_units(layout(kb).units, load_units(layout(kb).units) + [
        unit("induce/m", provenance="derived", derived_from=["a/explore/x", "b/explore/x"], scope="method", form="procedure")])
    write(kb, {"entities": [{"id": "concept:x", "type": "concept", "label": "x", "units": ["a/explore/x", "b/explore/x"]},
                            {"id": "t:a", "type": "table", "label": "a", "units": ["a/refine/y"]}],
               "relations": [{"src": "concept:x", "rel": "applies_to", "dst": "t:a", "units": ["a/explore/x"]}]}, ())
    assert [b["id"] for b in st.bridges(kb)] == ["concept:x"] and st.cross_induced(kb) == ["induce/m"]
    assert "跨数据集" in consolidate.prompt(kb, "structure") and "induce/m" in consolidate.prompt(kb, "structure")
