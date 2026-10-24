import json

from knosis import workspace as w
from knosis.data.traces import detect, normalize, read
from knosis.decision import evaluate
from knosis.knowledge import add_evidence, write_units


def codex_rows():
    return [
        {"type": "session_meta", "payload": {"cwd": "/x"}},
        {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "sys"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "count rows"}]}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "input": "wc -l data.csv"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "output": [{"type": "input_text", "text": "3 data.csv"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "x" * 5000}]}},
    ]


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_formats(tmp_path):
    steps = normalize(write(tmp_path / "c.jsonl", codex_rows()))
    assert [(s["role"], s["kind"]) for s in steps] == [("user", "message"), ("assistant", "call"), ("tool", "output"), ("assistant", "message")]
    assert steps[2]["text"] == "3 data.csv" and steps[3]["truncated"] == 5000
    claude = [{"type": "mode"}, {"type": "user", "message": {"role": "user", "content": "hi"}},
              {"type": "assistant", "message": {"role": "assistant", "content": [
                  {"type": "thinking", "thinking": "hm"}, {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
              {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "a.txt"}]}}]
    steps = normalize(write(tmp_path / "cl.jsonl", claude))
    assert detect(read(tmp_path / "cl.jsonl")) == "claude"
    assert [(s["role"], s["kind"]) for s in steps] == [("user", "message"), ("assistant", "reasoning"), ("assistant", "call"), ("tool", "output")]
    msgs = {"messages": [{"role": "user", "content": "go"},
                         {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "f", "arguments": "{}"}}]},
                         {"role": "tool", "content": "ok"}]}
    (tmp_path / "m.json").write_text(json.dumps(msgs))
    assert [(s["role"], s["kind"]) for s in normalize(tmp_path / "m.json")] == [("user", "message"), ("assistant", "call"), ("tool", "output")]
    react = {"task_id": "t1", "instruction": "play a song", "success": False, "completed": True,
             "steps": [{"step": "1", "reasoning": "look up docs", "code": "apis.spotify.login()", "env_feedback": "ok"}]}
    (tmp_path / "r.json").write_text(json.dumps(react))
    steps = normalize(tmp_path / "r.json")
    assert [(s["role"], s["kind"]) for s in steps] == [("user", "message"), ("assistant", "reasoning"), ("assistant", "call"), ("tool", "output"), ("system", "message")]
    assert "success=False" in steps[-1]["text"]


def test_trace_workspace_and_score(tmp_path):
    write(tmp_path / "run1.jsonl", codex_rows())
    env = tmp_path / "env"
    env.mkdir()
    (env / "data.csv").write_text("a\n1\n2\n")
    ws = w.init("traces", "demo", tmp_path / "ws", paths=str(tmp_path / "run1.jsonl"), env=str(env))
    assert (ws / "data/traces/run1.jsonl").exists() and (ws / "data/traces/run1.md").exists() and (ws / "data/env/data.csv").exists()
    assert "4 步" in (ws / "BRIEF.md").read_text()
    write_units(ws / "kb/knowledge/units.jsonl", [
        {"id": "rows", "content": "data.csv 有 2 行数据", "form": "fact", "status": "verified",
         "provenance": "data/traces/run1.jsonl#step/2 ; data/env/data.csv"},
        {"id": "bad", "content": "x", "form": "finding", "status": "inferred", "provenance": "data/traces/run1.jsonl#step/99"}])
    add_evidence(ws, [{"unit": "rows", "verdict": "support", "method": "data", "source": "data/env/data.csv"}])
    w.goto(ws, "decide")
    w.next_prompt(ws)
    report = evaluate(ws)
    assert report["cites_trace"] == 0.5 and report["env_verified"] == 0.5 and report["steps"] == 4


def test_trace_sources_travel_with_kb(tmp_path):
    from knosis.knowledge import check_knowledge
    from knosis.knowledge.kb import init_kb, merge

    write(tmp_path / "run1.jsonl", codex_rows())
    ws = w.init("traces", "demo", tmp_path / "ws", paths=str(tmp_path / "run1.jsonl"))
    write_units(ws / "kb/knowledge/units.jsonl", [
        {"id": "rows", "content": "data.csv 有 2 行数据", "form": "fact", "status": "inferred",
         "provenance": "data/traces/run1.jsonl#step/2"}])
    kb = init_kb(tmp_path / "kb")
    merge(ws, kb)
    assert (kb / "evidence/traces/run1.jsonl").exists() and "evidence/traces/run1.jsonl#step/2" in (kb / "kb/knowledge/units.jsonl").read_text()
    ws2 = w.init("traces", "demo", tmp_path / "ws2", paths=str(tmp_path / "run1.jsonl"), kb=str(kb))
    w.fork(ws2, tmp_path / "ws3", "K_inherit")
    assert (tmp_path / "ws3/evidence/traces/run1.jsonl").exists()
    assert check_knowledge(tmp_path / "ws3", root=tmp_path / "ws3") == []
    (tmp_path / "ws3/evidence/traces/run1.jsonl").unlink()
    assert any("missing source" in i for i in check_knowledge(tmp_path / "ws3", root=tmp_path / "ws3"))
