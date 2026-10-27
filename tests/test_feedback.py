import json
import pickle
import subprocess

import networkx as nx
import pytest

from knosis import workspace as w
from knosis.cli import main
from knosis.knowledge import check_units, feedback, load_units, write_units


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


def make(ngd_root, tmp_path, **kw):
    return w.init("ngdbench", "ngd-fin", tmp_path / kw.pop("name", "ws"), root=ngd_root, dev=4, limit=5, **kw)


def gold(task_id):
    return int(task_id.rsplit("/", 1)[1])


def test_submit_answer_mode(ngd_root, tmp_path):
    ws = make(ngd_root, tmp_path, budget=2)
    dev = load_units(ws / "tasks/dev.jsonl")
    assert len(dev) == 4 and "answer" not in json.dumps(dev)
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": dev[0]["id"], "answer": gold(dev[0]["id"])}, {"id": dev[1]["id"], "answer": -1}])
    record = feedback.submit(ws, path)
    assert record["id"] == "001-explore" and record["metrics"]["answer_set_em"] == 0.5
    assert [i["ok"] for i in record["items"]] == [True, False]
    assert record["items"][1]["gold"] == gold(dev[1]["id"])
    unit = {"id": "u", "content": "dev 题答错，相关数据可能有噪声", "form": "finding", "status": "inferred",
            "provenance": f"feedback:{record['id']}#item/{dev[1]['id']}"}
    assert not check_units([unit], root=ws)
    assert check_units([{**unit, "provenance": "feedback:999-x"}], root=ws)
    feedback.submit(ws, path)
    with pytest.raises(RuntimeError, match="unavailable"):
        feedback.submit(ws, path)


def test_submit_rejects_test_ids_and_hides_gold(ngd_root, tmp_path, capsys):
    ws = make(ngd_root, tmp_path, feedback="score")
    w.goto(ws, "decide")
    w.next_prompt(ws)
    test_id = load_units(ws / "tasks/tasks.jsonl")[0]["id"]
    path = ws / "stages/4_decide/probe.jsonl"
    write_units(path, [{"id": test_id, "answer": 0}])
    with pytest.raises(ValueError, match="dev ids"):
        feedback.submit(ws, path)
    dev_id = load_units(ws / "tasks/dev.jsonl")[0]["id"]
    write_units(path, [{"id": dev_id, "answer": 0}])
    main(["feedback", "submit", str(path), "--ws", str(ws)])
    out = capsys.readouterr().out
    assert '"ok"' in out and '"gold"' not in out


def test_prompts_mention_feedback(ngd_root, tmp_path):
    ws = make(ngd_root, tmp_path)
    assert "knosis feedback submit" in w.next_prompt(ws) and "还剩 20 次" in w.next_prompt(ws)
    no_dev = w.init("ngdbench", "ngd-fin", tmp_path / "nodev", root=ngd_root, dev=0, limit=5)
    assert w.status(no_dev)["feedback"]["mode"] == "none" and "没有 dev 反馈" in w.next_prompt(no_dev)


def test_driver_auto_feedback_per_round(ngd_root, tmp_path, monkeypatch):
    ws = make(ngd_root, tmp_path)
    w.goto(ws, "refine")
    dev = load_units(ws / "tasks/dev.jsonl")
    original, prompts = subprocess.run, []

    def agent(command, **kwargs):
        if command[0] != "codex":
            return original(command, **kwargs)
        prompts.append(command[-1])
        state = w.status(ws)
        directory = w.stage_dir(ws, state)
        write_units(ws / "kb/knowledge/units.jsonl", [{"id": f"r{state['round']}", "content": "c", "form": "fact",
                                                     "status": "observed", "provenance": "tool:x@1()"}])
        (directory / "changelog.md").write_text("round")
        write_units(directory / "dev_predictions.jsonl", [{"id": t["id"], "answer": gold(t["id"])} for t in dev[:state["round"]]])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(w.driver.subprocess, "run", agent)
    w.run(ws, stages=["refine"], rounds=2)
    records = feedback.records(ws)
    assert [r["id"] for r in records] == ["001-refine-r1", "002-refine-r2"]
    assert "001-refine-r1.json" in prompts[1] and "001-refine-r1" not in prompts[0]
    # feedback records are snapshotted with knowledge versions
    assert (ws / "stages/3_refine/round_1/evidence/feedback/001-refine-r1.json").exists()
    fork = w.fork(ws, tmp_path / "k1", "K_1")
    assert [p.name for p in (fork / "evidence/feedback").iterdir()] == ["001-refine-r1.json"]
    assert w.status(fork)["feedback"]["mode"] == "none"
    assert not list((w.fork(ws, tmp_path / "none", "none") / "evidence/feedback").iterdir())


def test_full_mode_requires_all_dev(ngd_root, tmp_path):
    ws = make(ngd_root, tmp_path, feedback_full=True)
    dev = load_units(ws / "tasks/dev.jsonl")
    path = ws / "stages/1_explore/part.jsonl"
    write_units(path, [{"id": dev[0]["id"], "answer": 0}])
    with pytest.raises(ValueError, match="answering all dev tasks"):
        feedback.submit(ws, path)
    write_units(path, [{"id": t["id"], "answer": gold(t["id"])} for t in dev])
    assert feedback.submit(ws, path)["metrics"]["answer_set_em"] == 1.0
    assert "必须回答全部开发题" in w.feedback_note(ws, w.status(ws))
