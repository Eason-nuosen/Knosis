import json
import subprocess

from knosis import workspace as w
from knosis.data.traces import calls, detect, normalize, read, validate, warning
from knosis.decision import evaluate
from knosis.knowledge import add_evidence, load_units, write_units


def codex_rows():
    return [
        {"type": "session_meta", "payload": {"cwd": "/x", "cli_version": "0.160.0"}},
        {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "sys"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "count rows"}]}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "call_id": "c1", "input": "wc -l data.csv"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "c1", "output": [{"type": "input_text", "text": "3 data.csv"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "x" * 5000}]}},
    ]


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def shape(t):
    return [(s["source"], len(s.get("tool_calls", [])), len(s.get("observation", {}).get("results", []))) for s in t["steps"]]


def test_codex(tmp_path):
    t = normalize(write(tmp_path / "c.jsonl", codex_rows()))
    assert validate(t) == [] and shape(t) == [("user", 0, 0), ("agent", 1, 1), ("agent", 0, 0)]
    call = t["steps"][1]["tool_calls"][0]
    assert call["arguments"] == {"input": "wc -l data.csv"} and t["steps"][1]["observation"]["results"][0]["content"] == "3 data.csv"
    assert t["steps"][2]["extra"]["knosis"]["truncated"] == {"message": 5000}
    info = t["extra"]["knosis"]
    assert info["tested"] and info["accounting"]["skipped"] == {"session_meta": 1, "developer": 1} and warning(t) is None
    rows = codex_rows()
    rows[0]["payload"]["cli_version"] = "9.0.0"
    rows.append({"type": "response_item", "payload": {"type": "brand_new"}})
    assert "untested" in warning(normalize(write(tmp_path / "c2.jsonl", rows))) and "brand_new" in warning(normalize(tmp_path / "c2.jsonl"))


def test_claude_groups_blocks_and_subagents(tmp_path):
    rows = [{"type": "mode"},
            {"type": "user", "version": "2.1.300", "sessionId": "s1", "message": {"role": "user", "content": "hi"}},
            # 一条 assistant 消息拆成多行写，result 夹在中间
            {"type": "assistant", "message": {"id": "m1", "role": "assistant", "content": [{"type": "thinking", "thinking": "hm"}]}},
            {"type": "assistant", "message": {"id": "m1", "role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "a.txt"}]}},
            {"type": "assistant", "message": {"id": "m1", "role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "Agent", "input": {"prompt": "go"}}]}},
            {"type": "user", "toolUseResult": {"agentId": "abc"},
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": "done"}]}]}},
            {"type": "assistant", "message": {"id": "m2", "role": "assistant", "content": [{"type": "text", "text": "ok"}]}}]
    path = write(tmp_path / "s1.jsonl", rows)
    (tmp_path / "s1/subagents").mkdir(parents=True)
    write(tmp_path / "s1/subagents/agent-abc.jsonl", [{"type": "user", "message": {"role": "user", "content": "go"}},
                                                      {"type": "assistant", "message": {"id": "x", "role": "assistant", "content": [{"type": "text", "text": "done"}]}}])
    assert detect(read(path)) == "claude"
    t = normalize(path)
    assert validate(t) == [] and shape(t) == [("user", 0, 0), ("agent", 1, 1), ("agent", 1, 1), ("agent", 0, 0)]
    assert t["steps"][1]["reasoning_content"] == "hm" and t["steps"][2]["observation"]["results"][0]["content"] == "done"
    assert t["subagent_trajectories"][0]["trajectory_id"] == "abc" and t["extra"]["knosis"]["subagent_calls"] == {"t2": "abc"}
    assert t["extra"]["knosis"]["version"] == "2.1.300" and t["extra"]["knosis"]["tested"]


def test_other_formats(tmp_path):
    msgs = {"messages": [{"role": "user", "content": "go"},
                         {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "f", "arguments": "{\"a\": 1}"}}]},
                         {"role": "tool", "tool_call_id": "1", "content": "ok"}]}
    (tmp_path / "m.json").write_text(json.dumps(msgs))
    t = normalize(tmp_path / "m.json")
    assert validate(t) == [] and shape(t) == [("user", 0, 0), ("agent", 1, 1)] and t["steps"][1]["tool_calls"][0]["arguments"] == {"a": 1}
    react = {"task_id": "t1", "instruction": "play a song", "success": False, "completed": True,
             "steps": [{"step": "1", "reasoning": "look up docs", "code": "apis.spotify.login()", "env_feedback": "ok"}]}
    (tmp_path / "r.json").write_text(json.dumps(react))
    t = normalize(tmp_path / "r.json")
    assert validate(t) == [] and shape(t) == [("user", 0, 0), ("agent", 1, 1)]
    assert t["extra"]["knosis"]["outcome"] == {"completed": True, "success": False}
    # 已经是 ATIF 的原样读回
    (tmp_path / "a.json").write_text(json.dumps(t))
    assert normalize(tmp_path / "a.json") == t


def test_trace_workspace_and_score(tmp_path):
    write(tmp_path / "run1.jsonl", codex_rows())
    env = tmp_path / "env"
    env.mkdir()
    (env / "data.csv").write_text("a\n1\n2\n")
    ws = w.init("traces", "demo", tmp_path / "ws", paths=str(tmp_path / "run1.jsonl"), env=str(env))
    assert (ws / "data/traces/run1.json").exists() and (ws / "data/traces/run1.md").exists() and (ws / "data/env/data.csv").exists()
    assert "3 步，工具调用 1 次" in (ws / "BRIEF.md").read_text() and "## step 2 · agent" in (ws / "data/traces/run1.md").read_text()
    write_units(ws / "kb/knowledge/units.jsonl", [
        {"id": "rows", "content": "data.csv 有 2 行数据", "form": "fact", "status": "verified",
         "provenance": "data/traces/run1.json#step/2 ; data/env/data.csv"},
        {"id": "bad", "content": "x", "form": "finding", "status": "inferred", "provenance": "data/traces/run1.json#step/99"}])
    add_evidence(ws, [{"unit": "rows", "verdict": "support", "method": "data", "source": "data/env/data.csv"}])
    w.goto(ws, "decide")
    w.next_prompt(ws)
    report = evaluate(ws)
    assert report["cites_trace"] == 0.5 and report["env_verified"] == 0.5 and report["steps"] == 3


def test_trace_sources_travel_with_kb(tmp_path):
    from knosis.knowledge import check_knowledge
    from knosis.knowledge.kb import init_kb, merge

    write(tmp_path / "run1.jsonl", codex_rows())
    ws = w.init("traces", "demo", tmp_path / "ws", paths=str(tmp_path / "run1.jsonl"))
    write_units(ws / "kb/knowledge/units.jsonl", [
        {"id": "rows", "content": "data.csv 有 2 行数据", "form": "fact", "status": "inferred",
         "provenance": "data/traces/run1.json#step/2"}])
    kb = init_kb(tmp_path / "kb")
    merge(ws, kb)
    assert (kb / "evidence/traces/run1.json").exists() and (kb / "evidence/traces/run1.md").exists()
    assert "evidence/traces/run1.json#step/2" in (kb / "kb/knowledge/units.jsonl").read_text()
    ws2 = w.init("traces", "demo", tmp_path / "ws2", paths=str(tmp_path / "run1.jsonl"), kb=str(kb))
    w.fork(ws2, tmp_path / "ws3", "K_inherit")
    assert (tmp_path / "ws3/evidence/traces/run1.json").exists()
    assert check_knowledge(tmp_path / "ws3", root=tmp_path / "ws3") == []
    (tmp_path / "ws3/evidence/traces/run1.json").unlink()
    assert any("missing source" in i for i in check_knowledge(tmp_path / "ws3", root=tmp_path / "ws3"))


def test_migrate_legacy_traces(tmp_path):
    """v0.5 工作区里的旧步骤序列：转成 ATIF，引用改到新步号，BRIEF 重写。"""
    from knosis.knowledge.migrate import migrate

    write(tmp_path / "run1.jsonl", codex_rows())
    ws = w.init("traces", "demo", tmp_path / "ws", paths=str(tmp_path / "run1.jsonl"))
    (ws / "data/traces/run1.json").unlink()
    old = [{"step": 0, "role": "user", "kind": "message", "text": "count rows"},
           {"step": 1, "role": "assistant", "kind": "reasoning", "text": "use wc"},
           {"step": 2, "role": "assistant", "kind": "call", "name": "exec", "text": "wc -l data.csv"},
           {"step": 3, "role": "tool", "kind": "output", "text": "3 data.csv"},
           {"step": 4, "role": "assistant", "kind": "message", "text": "2 rows"}]
    write(ws / "data/traces/run1.jsonl", old)
    write_units(ws / "kb/knowledge/units.jsonl", [
        {"id": "rows", "content": "data.csv 有 2 行数据", "form": "fact", "status": "verified",
         "provenance": "data/traces/run1.jsonl#step/3 ; data/traces/run1.jsonl#step/4"}])
    add_evidence(ws, [{"unit": "rows", "verdict": "support", "method": "data", "source": "data/traces/run1.jsonl#step/0"}])
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    report = migrate(ws)
    assert report["traces"]["traces"] == 1
    assert not (ws / "data/traces/run1.jsonl").exists()
    t = json.loads((ws / "data/traces/run1.json").read_text())
    assert validate(t) == [] and calls(t) == 1 and shape(t) == [("user", 0, 0), ("agent", 1, 1), ("agent", 0, 0)]
    assert load_units(ws / "kb/knowledge/units.jsonl")[0]["provenance"] == "data/traces/run1.json#step/2 ; data/traces/run1.json#step/3"
    assert "data/traces/run1.json#step/1" in (ws / "evidence/ledger.jsonl").read_text()
    assert "run1.json" in (ws / "BRIEF.md").read_text() and "jsonl" not in (ws / "BRIEF.md").read_text()
    from knosis.knowledge import check_knowledge

    assert check_knowledge(ws) == []  # 证据的数据指纹随转换更新，不算过期
    assert migrate(ws)["skipped"] == "already current"
