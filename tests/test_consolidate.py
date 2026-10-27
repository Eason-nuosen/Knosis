"""v0.5：内化（去重、矛盾处理、构建知识体系）的不变式与流程，以及 v0.4 布局迁移。"""

import json

import pytest

from knosis.cli import main
from knosis.knowledge import check_knowledge, check_units, consolidate, layout, load_evidence, load_units, write_units
from knosis.knowledge.migrate import migrate
from knosis.knowledge.select import select


def unit(uid, **kw):
    return {"id": uid, "content": kw.pop("content", f"内容 {uid}"), "form": kw.pop("form", "finding"),
            "provenance": kw.pop("provenance", "data/t.csv#row/1"), "status": kw.pop("status", "inferred"), **kw}


@pytest.fixture
def base(tmp_path):
    root = tmp_path / "ws"
    (root / "data").mkdir(parents=True)
    (root / "data/t.csv").write_text("a\n1\n")
    (root / ".knosis").mkdir()
    (root / ".knosis/state.json").write_text("{}")
    write_units(root / "kb/knowledge/units.jsonl", [])
    return root


def test_merge_alias_and_supersede():
    units = [unit("a"), unit("b", status="merged", merged_into="a"), unit("c", derived_from=["b"]),
             unit("old", status="stale", superseded_by="a")]
    assert check_units(units) == []
    # 别名指向已失效单元、merged 缺 merged_into、superseded_by 却仍活跃
    bad = [unit("a", status="retracted"), unit("b", status="merged", merged_into="a"), unit("d", status="merged"),
           unit("e", superseded_by="a")]
    issues = check_units(bad)
    assert any("b: merged_into a must resolve to an active unit" in i for i in issues)
    assert any("d: merged requires merged_into" in i for i in issues)
    assert any("e: superseded_by requires status stale or retracted" in i for i in issues)


def test_conflicts_must_be_resolved_or_contested():
    pair = [unit("a", conflicts_with=["b"]), unit("b", conflicts_with=["a"])]
    assert any("unresolved conflict with b" in i for i in check_units(pair))
    assert check_units([unit("a", conflicts_with=["b"], status="contested"), unit("b", conflicts_with=["a"])]) == []
    assert check_units([unit("a", conflicts_with=["b"]), unit("b", status="retracted")]) == []


def test_select_hides_contested_and_usage_rules(base):
    write_units(base / "kb/knowledge/units.jsonl", [unit("a"), unit("c", status="contested"),
                                                    unit("u", scope="usage", status="verified", form="fact")])
    assert [u["id"] for u in select(base)] == ["a", "u"]
    assert {u["id"] for u in select(base, include_contested=True)} == {"a", "c", "u"}
    issues = check_knowledge(base, root=base)
    assert any("usage knowledge can only be verified by feedback or ablation" in i for i in issues)


def test_skill_effects_are_usage_units(base):
    skill = base / "kb/skills/s/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: s\ndescription: d\nwhen: w\nuses: [b]\n---\n步骤\n")
    write_units(base / "kb/knowledge/units.jsonl", [unit("a"), unit("b", status="merged", merged_into="a")])
    write_units(base / "evidence/ledger.jsonl", [{"id": "e-0001", "unit": "skill:s", "verdict": "support",
                                                 "method": "feedback", "source": "x", "created": "t"}])
    issues = check_knowledge(base, root=base)
    assert any("skill effects are usage units" in i for i in issues)
    # skill 引用被合并的单元：按别名解析到活跃的 a，不要求 skill 失效
    assert not any("uses inactive knowledge" in i for i in issues)


def test_candidates_and_actions(base):
    write_units(base / "kb/knowledge/units.jsonl", [
        unit("a", content="订单表的 order_id 是主键，没有重复值", about=["data/t.csv#col/order_id"]),
        unit("b", content="订单表的 order_id 是主键，没有重复", about=["data/t.csv#col/order_id"]),
        unit("c", content="完全无关的另一件事情", about=["data/t.csv#col/x"])])
    found = consolidate.candidates(base)
    assert [(p["a"], p["b"]) for p in found["duplicates"]] == [("a", "b")]
    before = {u["id"]: u for u in load_units(layout(base).units)}
    after = {**before, "b": {**before["b"], "status": "merged", "merged_into": "a"},
             "n": unit("n", provenance="derived", derived_from=["a", "c"])}
    ops = {a["op"] for a in consolidate.actions(before, after, "dedup")}
    assert ops == {"merge", "induce"}


def fake_run(monkeypatch, edit):
    real = consolidate.subprocess.run

    def run(cmd, *args, **kw):
        if cmd[0] != "codex":
            return real(cmd, *args, **kw)
        edit()
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(consolidate.subprocess, "run", run)


def test_consolidate_step_logs_and_restores(base, monkeypatch):
    path = layout(base).units
    write_units(path, [unit("a", content="同一件事"), unit("b", content="同一件事")])

    def merge():
        units = load_units(path)
        write_units(path, [units[0], {**units[1], "status": "merged", "merged_into": "a"}])

    fake_run(monkeypatch, merge)
    result = consolidate.run_step(base, "dedup")
    assert result["issues"] == [] and result["actions"] == {"merge": 1}
    logged = load_units(layout(base).actions)
    assert logged[0]["op"] == "merge" and logged[0]["into"] == "a" and logged[0]["step"] == "dedup"

    def delete():  # 删除单元不允许：重试一次仍不过就恢复
        write_units(path, load_units(path)[:1])

    fake_run(monkeypatch, delete)
    result = consolidate.run_step(base, "conflict")
    assert result["restored"] and "must not be deleted" in result["issues"][0]
    assert [u["id"] for u in load_units(path)] == ["a", "b"]


def test_organize_step_requires_outline_and_induction_provenance(base, monkeypatch):
    from knosis.knowledge import outline

    path = layout(base).units
    write_units(path, [unit("a"), unit("b")])

    def organize():
        write_units(path, load_units(path) + [unit("g", content="归纳", provenance="derived", derived_from=["a"])])
        outline.write_outline(base, {"title": "t", "sections": [{"id": "s", "title": "s", "units": ["a", "b", "g"]}]})

    fake_run(monkeypatch, organize)
    result = consolidate.run_step(base, "organize")
    assert result["restored"] and any("at least two derived_from" in i for i in result["issues"])
    assert not layout(base).outline.exists()


def v04_workspace(tmp_path):
    ws = tmp_path / "old"
    k = ws / "knowledge"
    (k / "checks").mkdir(parents=True)
    (k / "feedback").mkdir()
    (k / "skills/s").mkdir(parents=True)
    (ws / ".knosis").mkdir()
    (ws / ".knosis/state.json").write_text("{}")
    (ws / "data").mkdir()
    (ws / "data/t.csv").write_text("a\n1\n")
    (k / "checks/c.py").write_text("import sys\nsys.path.insert(0, 'knowledge/checks')\n")
    (k / "feedback/001-explore.json").write_text(json.dumps({"id": "001-explore", "items": []}))
    (k / "skills/s/SKILL.md").write_text("---\nname: s\ndescription: d\nwhen: w\nuses: [utility/a/all]\n---\n步骤\n")
    write_units(k / "units.jsonl", [
        unit("a", form="method", check={"kind": "python", "path": "knowledge/checks/c.py"}),
        unit("utility/a/all", scope="utility", form="fact", provenance="feedback:001-explore", derived_from=["a"])])
    write_units(k / "evidence.jsonl", [
        {"id": "e-0001", "unit": "skill:s", "verdict": "support", "method": "feedback", "source": "feedback:001-explore",
         "created": "t"}])
    snap = ws / "stages/2_extract/knowledge"
    snap.mkdir(parents=True)
    write_units(snap / "units.jsonl", [unit("a", form="method")])
    write_units(ws / "stages/4_decide/used_units.jsonl", [{"id": 1, "used_units": ["utility/a/all"]}])
    return ws


def test_migrate_workspace(tmp_path):
    ws = v04_workspace(tmp_path)
    with pytest.raises(RuntimeError, match="knosis migrate"):
        layout(ws)
    report = migrate(ws)
    assert report["kind"] == "workspace" and report["snapshots"] == 1 and not (ws / "knowledge").exists()
    units = {u["id"]: u for u in load_units(ws / "kb/knowledge/units.jsonl")}
    assert units["a"]["form"] == "procedure" and units["a"]["check"]["path"] == "evidence/checks/c.py"
    assert units["usage/a/all"]["scope"] == "usage"
    assert units["usage/skill:s/migrated"]["meta"]["of"] == "skill:s"
    assert load_evidence(ws)[0]["unit"] == "usage/skill:s/migrated"
    assert "evidence/checks" in (ws / "evidence/checks/c.py").read_text()
    assert "usage/a/all" in (ws / "kb/skills/s/SKILL.md").read_text()
    assert "usage/a/all" in (ws / "stages/4_decide/used_units.jsonl").read_text()
    assert load_units(ws / "stages/2_extract/kb/knowledge/units.jsonl")[0]["form"] == "procedure"
    assert check_knowledge(ws, root=ws) == []
    assert migrate(ws)["skipped"] == "already current"


def test_migrate_kb_cli(tmp_path, capsys):
    kb = tmp_path / "kb"
    (kb / "traces").mkdir(parents=True)
    (kb / "traces/s1.jsonl").write_text("{}\n")
    write_units(kb / "units.jsonl", [unit("collect/x", provenance="knowledge/traces/s1.jsonl#step/1")])
    write_units(kb / "evidence.jsonl", [])
    (kb / ".gitignore").write_text("*.log\noutline.draft.yaml\n")
    main(["migrate", str(kb)])
    assert '"kind": "kb"' in capsys.readouterr().out
    assert load_units(kb / "kb/knowledge/units.jsonl")[0]["provenance"] == "evidence/traces/s1.jsonl#step/1"
    assert (kb / "evidence/traces/s1.jsonl").exists() and "kb/outline.draft.yaml" in (kb / ".gitignore").read_text()
    assert check_knowledge(kb) == []


def test_compact_topic_and_invariants(base, monkeypatch):
    path = layout(base).units
    write_units(path, [unit("a", content="订单表 order_id 唯一"), unit("b", content="订单表 order_id 非空"),
                       unit("c", content="用户表 age 有缺失")])
    assert [u["id"] for u in consolidate.topic_units(base, "订单表 order_id")] == ["a", "b"]
    text = consolidate.prompt(base, "compact", topic="订单表")
    assert "订单表" in text and "`a`" in text and "`c`" not in text and "只动与主题有关的单元" in text
    assert "`c`" in consolidate.prompt(base, "compact")

    def drop():  # 只改状态、不指向主单元：不允许悄悄丢掉
        units = load_units(path)
        write_units(path, [units[0], {**units[1], "status": "stale"}, units[2]])

    fake_run(monkeypatch, drop)
    result = consolidate.run_step(base, "compact", topic="订单表")
    assert result["restored"] and any("need merged_into" in i for i in result["issues"])

    def merge():
        units = load_units(path)
        write_units(path, [{**units[0], "content": "订单表 order_id 唯一且非空"},
                           {**units[1], "status": "merged", "merged_into": "a"}, units[2]])

    fake_run(monkeypatch, merge)
    result = consolidate.run_step(base, "compact", topic="订单表")
    assert result["issues"] == [] and result["active"] == [3, 2] and result["topic"] == "订单表"
    assert load_units(layout(base).actions)[-1]["op"] == "compact"

    fake_run(monkeypatch, lambda: None)  # 没有可压缩的：什么都不改也通过
    assert consolidate.run_step(base, "compact")["issues"] == []
