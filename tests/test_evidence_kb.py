import json
import pickle

import networkx as nx
import pandas as pd
import pytest

from knosis import workspace as w
from knosis.cli import main
from knosis.knowledge import add_evidence, check_knowledge, feedback, kb, load_evidence, load_units, trace, verify, write_units
from knosis.knowledge.evidence import run_check
from knosis.knowledge.select import select


@pytest.fixture
def ngd_root(tmp_path):
    d = tmp_path / "ngd/NGDBenchV1_1/NGDFin"
    (d / "graph").mkdir(parents=True)
    (d / "query").mkdir()
    graph = nx.MultiDiGraph()
    graph.add_node("A:1", label="A")
    for name in ("fin.gpickle", "fin_noise_x.gpickle"):
        with (d / "graph" / name).open("wb") as fh:
            pickle.dump(graph, fh)
    (d / "query/complex_query_agg.json").write_text(json.dumps(
        [{"nlp": f"q{i}", "query": "MATCH", "clean_answer": i, "noise_answer": i + 1} for i in range(20)]))
    return tmp_path / "ngd"


def make(ngd_root, path, **kw):
    return w.init("ngdbench", "ngd-fin", path, root=ngd_root, **{"dev": 4, "limit": 5, **kw})


def unit(uid, **changes):
    return {"id": uid, "content": f"{uid} content", "form": "finding", "provenance": "data/graph.gpickle#node/A:1",
            "status": "inferred", **changes}


def test_sql_check(tmp_path):
    (tmp_path / "data").mkdir()
    pd.DataFrame({"x": [1, 2, 3], "y": [0, 1, 1]}).to_csv(tmp_path / "data/train.csv", index=False)
    assert run_check({"check": {"kind": "sql", "query": "SELECT MIN(x) > 0 FROM train"}}, tmp_path)[0] == "support"
    assert run_check({"check": {"kind": "sql", "query": "SELECT COUNT(*) FROM train WHERE y = 1", "expect": [[3]]}}, tmp_path)[0] == "refute"
    # 留出数据上重跑同一检查：换一张表即可。
    held = {"train": pd.DataFrame({"x": [-1], "y": [0]})}
    assert run_check({"check": {"kind": "sql", "query": "SELECT MIN(x) > 0 FROM train"}}, tmp_path, held)[0] == "refute"


def test_status_must_match_evidence(ngd_root, tmp_path):
    ws = make(ngd_root, tmp_path / "ws")
    write_units(ws / "knowledge/units.jsonl", [unit("a", status="verified")])
    assert any("verified requires" in i for i in w.stage_issues(ws, w.status(ws)))
    add_evidence(ws / "knowledge", [{"unit": "a", "verdict": "support", "method": "data", "source": "data/graph.gpickle#node/A:1"}])
    assert w.stage_issues(ws, w.status(ws)) == ["missing or empty stages/1_explore/notes.md"]
    add_evidence(ws / "knowledge", [{"unit": "a", "verdict": "refute", "method": "human", "source": "review"}])
    assert any("refutes it" in i for i in w.stage_issues(ws, w.status(ws)))
    write_units(ws / "knowledge/units.jsonl", [unit("a", status="contested", support=2)])
    issues = w.stage_issues(ws, w.status(ws))
    assert any("I2" in i for i in issues) and not any("refutes" in i for i in issues)
    add_evidence(ws / "knowledge", [{"unit": "ghost", "verdict": "maybe", "method": "check", "source": "x"}])
    issues = w.stage_issues(ws, w.status(ws))
    assert any("unknown unit: ghost" in i for i in issues) and any("invalid verdict" in i for i in issues)


def test_python_check_verify_expiry_and_trace(ngd_root, tmp_path):
    ws = make(ngd_root, tmp_path / "ws")
    (ws / "knowledge/checks").mkdir()
    (ws / "knowledge/checks/has_node.py").write_text(
        "import pickle,sys\ng=pickle.load(open('data/graph.gpickle','rb'))\nprint('nodes', g.number_of_nodes())\n"
        "sys.exit(0 if 'A:1' in g else 1)\n")
    write_units(ws / "knowledge/units.jsonl", [
        unit("m", form="method", content="按 id 前缀判断类型", check={"kind": "python", "path": "knowledge/checks/has_node.py"}),
        unit("b", status="verified", provenance="derived", derived_from=["m"]),
    ])
    entries = verify(ws)
    assert [(e["unit"], e["verdict"]) for e in entries] == [("m", "support")] and "nodes 1" in entries[0]["note"]
    assert "data/graph.gpickle" in entries[0]["inputs"]
    add_evidence(ws / "knowledge", [{"unit": "b", "verdict": "support", "method": "derivation", "source": "derived",
                                     "inputs": entries[0]["inputs"]}])
    assert check_knowledge(ws / "knowledge", root=ws) == []
    text = trace(ws / "knowledge", "b")
    assert "**b**" in text and "**m**" in text and "support（check" in text
    # 数据变了，证据过期，verified 失去支持。
    graph = nx.MultiDiGraph()
    with (ws / "data/graph.gpickle").open("wb") as fh:
        pickle.dump(graph, fh)
    assert any("verified requires" in i for i in check_knowledge(ws / "knowledge", root=ws))
    assert verify(ws, ["m"])[0]["verdict"] == "refute"


def test_select(ngd_root, tmp_path):
    ws = make(ngd_root, tmp_path / "ws")
    write_units(ws / "knowledge/units.jsonl", [
        unit("a", about=["Loan"]), unit("b", form="method", content="Detect label noise"), unit("c", status="retracted")])
    add_evidence(ws / "knowledge", [{"unit": "b", "verdict": "support", "method": "human", "source": "x"}])
    assert [u["id"] for u in select(ws / "knowledge")] == ["a", "b"]
    assert [u["id"] for u in select(ws / "knowledge", about=["Loan"])] == ["a"]
    assert [u["id"] for u in select(ws / "knowledge", text="label")] == ["b"]
    assert select(ws / "knowledge", form="method")[0]["evidence"] == {"support": 1}
    assert {u["id"] for u in select(ws / "knowledge", include_inactive=True)} == {"a", "b", "c"}


def test_kb_inherit_merge_and_fork(ngd_root, tmp_path):
    base = kb.init_kb(tmp_path / "kb")
    ws = make(ngd_root, tmp_path / "ws1")
    dev = load_units(ws / "tasks/dev.jsonl")
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": t["id"], "answer": int(t["id"].rsplit("/", 1)[1])} for t in dev])
    record = feedback.submit(ws, path)
    write_units(ws / "knowledge/units.jsonl", [
        unit("m", form="method"), unit("f", provenance=f"feedback:{record['id']}#item/{dev[0]['id']}", derived_from=["m"])])
    add_evidence(ws / "knowledge", [{"unit": "f", "verdict": "support", "method": "feedback",
                                     "source": f"feedback:{record['id']}#item/{dev[0]['id']}"}])
    version = kb.merge(ws, base)
    assert version and len(load_units(base / "units.jsonl")) == 2
    renamed = f"ws1.{record['id']}"
    assert (base / f"feedback/{renamed}.json").exists()
    assert load_units(base / "units.jsonl")[1]["provenance"].startswith(f"feedback:{renamed}")
    assert load_evidence(base)[0]["source"].startswith(f"feedback:{renamed}") and check_knowledge(base) == []

    # 第二个工作区：继承全部；同一数据集上反馈见过的题不进测试集；继承的反馈不占预算。
    ws2 = make(ngd_root, tmp_path / "ws2", kb=base, seed=1, limit=12)
    state = w.status(ws2)
    assert state["kb"]["units"] == 2 and set(state["exclude"]) <= {t["id"] for t in dev}
    assert feedback.left(ws2, state) == 20 and (ws2 / "stages/0_inherit/knowledge/units.jsonl").exists()
    w.goto(ws2, "decide")
    w.next_prompt(ws2)
    assert not {t["id"] for t in load_units(ws2 / "tasks/tasks.jsonl")} & {t["id"] for t in dev}
    assert w.stage_issues(ws2, w.status(ws2)) == ["missing or empty predictions: stages/4_decide/predictions.jsonl"]

    # 只继承元知识。
    ws3 = make(ngd_root, tmp_path / "ws3", kb=base, kb_scope=["method"])
    assert [u["id"] for u in load_units(ws3 / "knowledge/units.jsonl")] == ["m"]
    write_units(ws3 / "knowledge/units.jsonl", [unit("m", form="method"), unit("n")])
    fork = w.fork(ws3, tmp_path / "fork", "K_inherit")
    assert [u["id"] for u in load_units(fork / "knowledge/units.jsonl")] == ["m"]
    dropped = w.fork(ws3, tmp_path / "drop", "K_final", drop=["n"])
    assert [u["id"] for u in load_units(dropped / "knowledge/units.jsonl")] == ["m"]
    assert w.status(dropped)["dropped"] == ["n"]


def test_kb_merge_rejects_broken_knowledge(ngd_root, tmp_path):
    base = kb.init_kb(tmp_path / "kb")
    ws = make(ngd_root, tmp_path / "ws")
    write_units(ws / "knowledge/units.jsonl", [unit("a", status="verified")])
    with pytest.raises(ValueError, match="verified requires"):
        kb.merge(ws, base)
    assert load_units(base / "units.jsonl") == []


def test_cli_knowledge_commands(ngd_root, tmp_path, capsys, monkeypatch):
    ws = make(ngd_root, tmp_path / "ws")
    write_units(ws / "knowledge/units.jsonl", [unit("a")])
    tool_out = tmp_path / "evidence.jsonl"
    write_units(tool_out, [{"unit": "a", "verdict": "support", "method": "tool", "source": "tool:fit@0.1(x)"}])
    main(["knowledge", "evidence", "import", str(tool_out), "--ws", str(ws)])
    main(["knowledge", "evidence", "add", "--ws", str(ws), "--unit", "a", "--verdict", "undetermined",
          "--method", "data", "--source", "data/graph.gpickle", "--inputs", "data/graph.gpickle"])
    main(["knowledge", "check", "--ws", str(ws)])
    main(["knowledge", "select", "--ws", str(ws)])
    out = capsys.readouterr().out
    assert "e-0001 a support" in out and "e-0002" in out and "OK" in out and '"support": 1' in out
    assert load_evidence(ws / "knowledge")[1]["inputs"]["data/graph.gpickle"]


def test_method_checks_must_be_self_contained(ngd_root, tmp_path):
    ws = make(ngd_root, tmp_path / "ws")
    w.goto(ws, "extract")
    (ws / "knowledge/checks").mkdir()
    (ws / "stages/2_extract/helper.py").write_text("OK = 0\n")
    (ws / "knowledge/checks/bad.py").write_text("import sys\nsys.path.insert(0, 'stages/2_extract')\nimport helper\nsys.exit(helper.OK)\n")
    (ws / "knowledge/checks/good.py").write_text("import pickle,sys\npickle.load(open('data/graph.gpickle','rb'))\n")
    write_units(ws / "knowledge/units.jsonl", [
        unit("bad", form="method", check={"kind": "python", "path": "knowledge/checks/bad.py"}),
        unit("good", form="method", check={"kind": "python", "path": "knowledge/checks/good.py"}),
        unit("outside", form="method", check={"kind": "python", "path": "stages/2_extract/helper.py"})])
    issues = w.stage_issues(ws, w.status(ws))
    assert "bad: method check is not self-contained (fails with only data/ and knowledge/)" in issues
    assert "outside: method check must live under knowledge/checks/" in issues
    assert not any(i.startswith("good:") for i in issues)


def test_scope_inference_and_index(ngd_root, tmp_path):
    from knosis.knowledge import scope_of
    from knosis.knowledge.select import index

    assert scope_of(unit("a")) == "instance"
    assert scope_of(unit("b", provenance="data/graph.gpickle")) == "dataset"
    assert scope_of(unit("c", form="method")) == "method"
    assert scope_of({"id": "ontology/join/x", "form": "schema", "provenance": "o.yaml#relationship/x"}) == "relation"
    assert scope_of(unit("d", scope="utility")) == "utility"
    ws = make(ngd_root, tmp_path / "ws")
    write_units(ws / "knowledge/units.jsonl", [unit("a", about=["data/graph.gpickle#node/A:1"]), unit("bad", scope="domain")])
    assert any("invalid scope: domain" in i for i in check_knowledge(ws / "knowledge", root=ws))
    write_units(ws / "stages/4_decide/used_units.jsonl", [{"id": "q", "used_units": ["a"]}])
    view = index(ws / "knowledge", ws)
    assert view["data/graph.gpickle#node/A:1"] == {"units": ["a", "bad"], "used_in": {"a": 1}}
    assert view["data/graph.gpickle"]["units"] == ["a", "bad"]


def write_skill(ws, name, uses, status="active", derived=()):
    path = ws / "knowledge/skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    head = {"name": name, "description": "d", "when": "w", "uses": list(uses), "status": status, "derived_from": list(derived)}
    path.write_text("---\n" + json.dumps(head) + "\n---\n先做 A，再做 B。\n")


def test_skills_checks_select_and_utility(ngd_root, tmp_path):
    from knosis.knowledge.select import select_skills

    ws = make(ngd_root, tmp_path / "ws")
    write_units(ws / "knowledge/units.jsonl", [unit("a"), unit("r", status="retracted")])
    write_skill(ws, "solve", ["a"])
    write_skill(ws, "old", ["r"])
    write_skill(ws, "ghost", ["nope"], derived=["missing-record"])
    issues = check_knowledge(ws / "knowledge", root=ws)
    assert any("old: uses inactive knowledge r" in i for i in issues)
    assert any("ghost: unknown knowledge in uses: nope" in i for i in issues)
    assert any("ghost: unknown feedback record" in i for i in issues)
    assert not any("skill solve" in i for i in issues)
    assert [s["name"] for s in select_skills(ws / "knowledge")] == ["ghost", "old", "solve"]

    # dev 反馈附 used_units：按题型生成 utility 候选（κ 与 skill 都统计）
    dev = load_units(ws / "tasks/dev.jsonl")
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": t["id"], "answer": int(t["id"].rsplit("/", 1)[1]) if i < 2 else -1} for i, t in enumerate(dev)])
    write_units(ws / "stages/1_explore/dev_used_units.jsonl",
                [{"id": t["id"], "used_units": ["a", "skill:solve"] if i < 2 else []} for i, t in enumerate(dev)])
    feedback.submit(ws, path)
    made = {u["id"]: u for u in load_units(ws / "knowledge/units.jsonl") if u.get("scope") == "utility"}
    kind = dev[0]["kind"]
    assert set(made) == {f"utility/a/{kind}", f"utility/skill:solve/{kind}"}
    assert made[f"utility/a/{kind}"]["meta"]["acc_used"] == 1.0 and made[f"utility/a/{kind}"]["meta"]["acc_other"] == 0.0
    assert {e["unit"]: e["verdict"] for e in load_evidence(ws / "knowledge")}[f"utility/a/{kind}"] == "support"
    # utility 只能由反馈或消融证据支持为 verified
    units = load_units(ws / "knowledge/units.jsonl")
    write_units(ws / "knowledge/units.jsonl", [{**u, "status": "verified"} if u["id"] == f"utility/a/{kind}" else u for u in units])
    assert not any(f"utility/a/{kind}: utility" in i for i in check_knowledge(ws / "knowledge", root=ws))


def test_kb_inherits_skills_by_scope(ngd_root, tmp_path):
    base = kb.init_kb(tmp_path / "kb")
    ws = make(ngd_root, tmp_path / "ws1")
    write_units(ws / "knowledge/units.jsonl", [unit("m", form="method"), unit("a")])
    write_skill(ws, "solve", ["a"])
    kb.merge(ws, base)
    ws2 = make(ngd_root, tmp_path / "ws2", kb=base, kb_scope=["skill", "instance"])
    assert (ws2 / "knowledge/skills/solve/SKILL.md").exists() and [u["id"] for u in load_units(ws2 / "knowledge/units.jsonl")] == ["a"]
    ws3 = make(ngd_root, tmp_path / "ws3", kb=base, kb_scope=["method"])
    assert not (ws3 / "knowledge/skills").exists()
