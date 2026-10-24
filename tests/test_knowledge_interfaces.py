"""autoschemakg 工具、知识体系大纲、MCP 服务。"""

import io
import json

import pytest

from knosis.cli import main
from knosis.knowledge import check_knowledge, check_units, consolidate, load_units, outline, write_units
from knosis.mcp import Server, serve
from knosis.tools.autoschemakg import run as askg
from knosis.workspace import driver

TEXT = "PUMA appointed Hubert Hinterseher as Chief Financial Officer. PUMA focused on the China market."


def extraction(pid):
    return {"id": pid,
            "entity_relation_dict": [{"Head": "Hubert Hinterseher", "Relation": "serves as", "Tail": "Chief Financial Officer"},
                                     {"Head": "PUMA", "Relation": "focused on", "Tail": "China market"},
                                     {"Head": "PUMA", "Relation": "acquired", "Tail": "Nike"},  # 原文没有：不 grounded
                                     {"Head": "PUMA"}],  # 残缺项丢弃
            "event_entity_dict": [{"Event": "PUMA appointed a CFO.", "Entity": ["PUMA", "Hubert Hinterseher"]}],
            "event_relation_dict": [{"Head": "PUMA appointed a CFO.", "Relation": "before", "Tail": "PUMA focused on China."}]}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    (root / "data").mkdir(parents=True)
    (root / ".knosis").mkdir()
    (root / ".knosis/state.json").write_text("{}")
    (root / "data/doc.md").write_text(TEXT, encoding="utf-8")
    write_units(root / "kb/knowledge/units.jsonl", [
        {"id": "a", "content": "a", "form": "finding", "provenance": "data/doc.md#0-10", "status": "inferred", "scope": "instance"},
        {"id": "m", "content": "m", "form": "procedure", "provenance": "derived", "derived_from": ["a"], "status": "inferred"},
        {"id": "old", "content": "old", "form": "finding", "provenance": "data/doc.md", "status": "retracted"},
    ])
    monkeypatch.chdir(root)
    return root


def test_autoschemakg_pipeline(ws, capsys):
    out = ws / "kg"
    askg.main(["prepare", "--text", "data/", "--out", str(out)])
    passages = askg.read_jsonl(out / "passages.jsonl")
    assert passages[0]["source"] == f"data/doc.md#0-{len(TEXT)}" and "Head" in (out / "PROMPTS.md").read_text()
    askg.write_jsonl(out / "extractions.jsonl", [extraction("p1")])
    askg.main(["build", "--dir", str(out)])
    units = load_units(out / "units.jsonl")
    assert not check_units(units, root=ws)
    triples = {u["content"]: u["meta"]["grounded"] for u in units if u["id"].startswith("autoschemakg/er/")}
    assert triples == {"Hubert Hinterseher —serves as→ Chief Financial Officer": True, "PUMA —focused on→ China market": True,
                       "PUMA —acquired→ Nike": False}
    assert all(u["status"] == "inferred" for u in units)
    # 概念化：按 concept_todo 写概念后再建一次，得到概念层 schema
    todo = askg.read_jsonl(out / "concept_todo.jsonl")
    assert {"PUMA", "focused on"} <= {t["name"] for t in todo} and "CONTEXT" in todo[0]["prompt"]
    askg.write_jsonl(out / "concepts.jsonl", [{"name": "PUMA", "type": "entity", "concepts": ["company", "brand"]},
                                              {"name": "China market", "type": "entity", "concepts": ["market"]}])
    askg.main(["build", "--dir", str(out)])
    schema = json.loads((out / "schema.json").read_text())
    assert schema["patterns"][0] == {"head": "company", "relation": "focused on", "tail": "market", "count": 1}
    capsys.readouterr()
    askg.main(["query", "--dir", str(out), "--node", "hinterseher"])
    assert "Hubert Hinterseher —serves as→ Chief Financial Officer  [p1]" in capsys.readouterr().out


def test_autoschemakg_upstream_format(tmp_path):
    """上游抽取文件：段落在 original_text 里，id 在不同文档间重复，按行号区分。"""
    rows = [{**extraction("1"), "original_text": TEXT}, {**extraction("1"), "original_text": "unrelated text"}]
    path = tmp_path / "upstream.json"
    askg.write_jsonl(path, rows)
    result = askg.build(tmp_path, path, tmp_path / "none.jsonl", 10, 10)
    grounded = [e for e in result["edges"] if e["kind"] == "entity_relation" and e["grounded"]]
    assert {e["passage"] for e in result["edges"]} == {"line1", "line2"} and {e["passage"] for e in grounded} == {"line1"}


def test_parse_array():
    assert askg.parse_array('```json\n[{"Head": "a"}]\n```') == [{"Head": "a"}]
    assert askg.parse_array("no json here") == []


def test_outline(ws, capsys):
    kdir = ws
    draft = outline.draft(kdir)
    assert draft["title"] == "ws"
    assert [s["id"] for s in draft["sections"]] == ["method", "instance", "archive"]
    assert not outline.unplaced(draft, outline.members(kdir))
    bad = {"title": "t", "sections": [{"id": "s", "title": "s", "units": ["a", "nope", "old"]},
                                      {"id": "s", "title": "dup", "units": []}]}
    issues = outline.check_outline(bad, outline.members(kdir))
    assert any("unknown unit nope" in i for i in issues) and any("inactive unit old" in i for i in issues)
    assert any("duplicate id" in i for i in issues)
    assert outline.unplaced(bad, outline.members(kdir)) == ["m"]
    # 有大纲时知识层检查会带上它
    outline.write_outline(kdir, bad)
    assert any(i.startswith("outline") for i in check_knowledge(kdir, root=ws))
    before = {u["id"] for u in load_units(ws / "kb/knowledge/units.jsonl")}
    assert consolidate.step_issues(ws, "organize", before, [])[-1].startswith("outline: 1 active units not placed: m")
    main(["knowledge", "outline", "--ws", str(ws)])
    assert "## 未归类（1）" in capsys.readouterr().out
    assert "> a\n> b" in outline.render({"title": "t", "sections": [{"id": "s", "title": "s", "notes": ["a", "b"]}]}, {})
    (ws / "kb/outline.yaml").unlink()
    main(["knowledge", "outline", "--ws", str(ws), "--write"])
    assert not consolidate.step_issues(ws, "organize", before, [])
    prompt = consolidate.prompt(ws, "organize")
    assert "outline.yaml" in prompt and (ws / "kb/outline.draft.yaml").exists()


def test_mcp_server(ws):
    server = Server(ws)

    def call(tool, **arguments):
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}})
        return reply["result"]

    init = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
    assert init["result"]["protocolVersion"] == "2025-03-26"
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    names = {t["name"] for t in server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
    assert {"knowledge_select", "knowledge_add", "tool_run", "knowledge_outline"} <= names and "eval" not in names
    assert json.loads(call("knowledge_select", scope="method")["content"][0]["text"])[0]["id"] == "m"
    new = {"id": "n", "content": "n", "form": "rule", "provenance": "data/doc.md#0-4", "status": "inferred"}
    assert not call("knowledge_add", unit=new)["isError"]
    assert call("knowledge_add", unit=new)["isError"]  # 重复 id
    missing = call("knowledge_add", unit={**new, "id": "x", "provenance": "data/missing.csv"})
    assert missing["isError"] and "missing data source" in missing["content"][0]["text"]
    # 撤回父单元时，派生单元未跟着失效（I5）→ 拒绝
    assert call("knowledge_update", id="a", fields={"status": "retracted"})["isError"]
    assert not call("knowledge_update", id="n", fields={"status": "retracted"})["isError"]
    assert {u["id"]: u["status"] for u in load_units(ws / "kb/knowledge/units.jsonl")}["n"] == "retracted"
    result = json.loads(call("evidence_add", unit="m", verdict="refute", method="derivation", source="a")["content"][0]["text"])
    assert result["unit_issues"]  # 被反驳后要求改状态
    assert call("nope")["isError"]
    run = json.loads(call("tool_run", name="autoschemakg", args=["prepare", "--text", "data/", "--out", "kg"])["content"][0]["text"])
    assert run["returncode"] == 0 and (ws / "kg/passages.jsonl").exists()


def test_mcp_stdio(ws):
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "bogus"}]
    out = io.StringIO()
    serve(ws, io.StringIO("\n".join(json.dumps(m) for m in lines) + "\nnot json\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert replies[0]["result"] == {} and replies[1]["error"]["code"] == -32601 and replies[2]["error"]["code"] == -32700


# ---------------------------------------------------------------- 日常收集与安装


def codex_session(path, cwd, calls=3):
    rows = [{"timestamp": "t", "type": "session_meta", "payload": {"id": "x", "cwd": str(cwd)}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "fix it"}]}}]
    for i in range(calls):
        rows += [{"type": "response_item", "payload": {"type": "function_call", "name": "exec", "arguments": f"ls {i}"}},
                 {"type": "response_item", "payload": {"type": "function_call_output", "output": f"out {i}"}}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_collect(tmp_path, monkeypatch):
    from knosis.knowledge import collect, kb as kbmod

    kb = kbmod.init_kb(tmp_path / "kb")
    sessions = tmp_path / "codex/sessions/2026/10/22"
    project, wsdir = tmp_path / "proj", tmp_path / "ws"
    (wsdir / ".knosis").mkdir(parents=True)
    (wsdir / ".knosis/state.json").write_text("{}")
    project.mkdir()
    codex_session(sessions / "rollout-a.jsonl", project)
    codex_session(sessions / "rollout-b.jsonl", project, calls=1)    # 调用太少
    codex_session(sessions / "rollout-c.jsonl", wsdir / "sub")        # Knosis 工作区内
    codex_session(sessions / "rollout-d.jsonl", kb)                   # 收集自身的会话
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    assert collect.parse_since("2h") < collect.parse_since("1h")
    found, skipped = collect.find(kb, since="1d")
    assert [s["session"] for s in found] == ["rollout-a"]
    assert skipped == {"collected": 0, "inside_kb": 1, "workspace": 1, "few_calls": 1, "unreadable": 0}
    assert len(collect.find(kb, since="1d", include_workspaces=True)[0]) == 2

    def fake_agent(cmd, cwd, env, stdin, stdout, stderr):  # 模拟 agent：写一条引用轨迹的知识
        units = load_units(kb / "kb/knowledge/units.jsonl")
        write_units(kb / "kb/knowledge/units.jsonl", units + [{"id": "collect/ls", "content": "ls works", "form": "finding",
                                                  "status": "inferred", "provenance": "evidence/traces/rollout-a.jsonl#step/1"}])
        return type("R", (), {"returncode": 0})()

    real = collect.subprocess.run
    monkeypatch.setattr(collect.subprocess, "run", lambda *a, **k: fake_agent(a[0], **k) if a[0][0] == "codex" else real(*a, **k))
    result = collect.run(kb, since="1d", consolidate=False)
    assert result["added"] == ["collect/ls"] and (kb / "evidence/traces/rollout-a.md").exists()
    assert collect.collected(kb) == {"rollout-a"} and not collect.find(kb, since="1d")[0]
    assert "collect: 1 codex sessions" in collect.git(kb, "log", "-1", "--format=%s")
    # 不引用本次轨迹的新单元不通过，重试后仍不通过就恢复知识库
    codex_session(sessions / "rollout-e.jsonl", project)

    def bad_agent(cmd, cwd, env, stdin, stdout, stderr):
        units = load_units(kb / "kb/knowledge/units.jsonl")
        if not any(u["id"] == "collect/bad" for u in units):
            write_units(kb / "kb/knowledge/units.jsonl", units + [{"id": "collect/bad", "content": "x", "form": "finding",
                                                      "status": "inferred", "provenance": "somewhere"}])
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(collect.subprocess, "run", lambda *a, **k: bad_agent(a[0], **k) if a[0][0] == "codex" else real(*a, **k))
    result = collect.run(kb, since="1d", consolidate=False)
    assert result["restored"] and "must cite" in result["issues"][0]
    assert [u["id"] for u in load_units(kb / "kb/knowledge/units.jsonl")] == ["collect/ls"] and not (kb / "evidence/traces/rollout-e.md").exists()


def test_install_mcp(tmp_path, monkeypatch):
    from knosis.cli import install_skill

    monkeypatch.delenv("CODEX_HOME", raising=False)
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('model = "x"\n')
    install_skill(codex=True, home=tmp_path, kb=tmp_path / "kb")
    install_skill(codex=True, home=tmp_path, kb=tmp_path / "kb2")   # 再装一次替换，不重复
    text = config.read_text()
    assert text.startswith('model = "x"\n') and text.count("[mcp_servers.knosis]") == 1 and "kb2" in text
    assert 'default_tools_approval_mode = "approve"' in text
    config.write_text("[mcp_servers.knosis]\ncommand = \"other\"\n")
    with pytest.raises(SystemExit):
        install_skill(codex=True, home=tmp_path, kb=tmp_path / "kb")


def test_select_keywords(ws):
    server = Server(ws)
    write_units(ws / "kb/knowledge/units.jsonl", load_units(ws / "kb/knowledge/units.jsonl") + [
        {"id": "k", "content": "alpha beta", "form": "finding", "provenance": "data/doc.md", "status": "inferred"}])
    assert [u["id"] for u in server.knowledge_select(text="beta alpha zzz")] == ["k"]
    assert server.knowledge_select(text="zzz yyy") == []
