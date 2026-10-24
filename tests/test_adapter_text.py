from knosis import workspace as w
from knosis.decision import text as scorer
from knosis.knowledge import check_units, load_units, write_units
from knosis.workspace.exporters import text  # noqa: F401  注册导出器


def corpus(tmp_path):
    root = tmp_path / "corpus"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("Alice founded Acme in 1999.\n\nAcme makes rockets.")
    (root / "sub/b.txt").write_text("Bob joined Acme in 2005.")
    (root / "copy.txt").write_text("alice founded acme in 1999. acme makes rockets.")
    return root


def test_export_places_corpus(tmp_path):
    root = corpus(tmp_path)
    ws = w.init("text", str(root), tmp_path / "ws")
    assert sorted(p.relative_to(ws / "data").as_posix() for p in (ws / "data").rglob("*") if p.is_file()) == \
        ["a.md", "copy.txt", "sub/b.txt"]
    assert (ws / "data/a.md").stat().st_ino == (root / "a.md").stat().st_ino  # 硬链接
    assert not (ws / "data/a.md").is_symlink()
    state = w.status(ws)
    assert state["output"] is None and state["feedback"]["mode"] == "none"
    assert not load_units(ws / "tasks/dev.jsonl")
    assert "data/<文件>#<start>-<end>" in (ws / "BRIEF.md").read_text()
    w.goto(ws, "decide")
    assert "没有下游预测" in w.next_prompt(ws)
    assert not w.check(ws) and w.status(ws)["completed"]


def test_score_knowledge_grounding(tmp_path):
    ws = w.init("text", str(corpus(tmp_path)), tmp_path / "ws")
    units = [
        {"id": "founded", "content": "Alice 于 1999 年创立 Acme", "form": "fact", "status": "verified",
         "provenance": "data/a.md#0-27", "meta": {"quote": "founded Acme in 1999"}},
        {"id": "wrong-quote", "content": "Bob 创立 Acme", "form": "fact", "status": "inferred",
         "provenance": "data/sub/b.txt#0-24", "meta": {"quote": "Bob founded"}},
        {"id": "bad-span", "content": "x", "form": "fact", "status": "observed", "provenance": "data/a.md#10-9999"},
        {"id": "rule", "content": "公司由创始人创立", "form": "rule", "status": "inferred", "provenance": "derived",
         "derived_from": ["founded"]},
    ]
    write_units(ws / "kb/knowledge/units.jsonl", units)
    assert not check_units(units, root=ws)
    result = scorer.score(ws, w.status(ws), None, None, [])
    m = result["metrics"]
    assert m["units"] == 4 and m["by_form"] == {"fact": 3, "rule": 1}
    assert m["with_text_span"] == 0.75 and m["span_resolvable"] == 2 / 3
    assert m["quote_supported"] == 0.5 and m["grounded"] == 0.25
    assert [i["ok"] for i in result["items"]] == [True, False, False, False]
