"""Who&When：轨迹转换（步号与标注对齐、GT 不进轨迹）、导出器、打分器、dev 反馈。"""

import json

import pytest

from knosis import load_dataset
from knosis import workspace as w
from knosis.data import data_dir
from knosis.data.traces import normalize, validate
from knosis.decision import evaluate
from knosis.knowledge.feedback import submit


def hand(n):
    return {"question": f"q{n}", "groundtruth": "Renzo Gracie", "is_corrected": False, "question_ID": f"h{n}",
            "mistake_agent": "Websurfer", "mistake_step": "2", "mistake_reason": "SECRET-REASON clicked an irrelevant page",
            "history": [{"role": "human", "content": f"q{n}"}, {"role": "Orchestrator (thought)", "content": "plan"},
                        {"role": "WebSurfer", "content": "clicked"}, {"role": "Orchestrator (-> WebSurfer)", "content": "go on"}]}


def algo(n):
    return {"question": f"a{n}", "ground_truth": "8", "is_correct": False, "question_ID": f"a{n}", "level": "2",
            "mistake_agent": "Excel_Expert", "mistake_step": "0", "mistake_reason": "SECRET-REASON missed edge cases",
            "system_prompt": {"Excel_Expert": "## Your role\nExcel"},
            "history": [{"role": "assistant", "name": "Excel_Expert", "content": "code"},
                        {"role": "user", "name": "Computer_terminal", "content": "exitcode: 0"}]}


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "ww"
    for folder, make in (("Hand-Crafted", hand), ("Algorithm-Generated", algo)):
        (base / "Who&When" / folder).mkdir(parents=True)
        for n in range(1, 4):
            (base / "Who&When" / folder / f"{n}.json").write_text(json.dumps(make(n)))
    return base


def test_trace_alignment_and_no_gt(root):
    t = normalize(root / "Who&When/Hand-Crafted/1.json")
    assert validate(t) == [] and [s["source"] for s in t["steps"]] == ["user", "agent", "agent", "agent"]
    assert [s.get("extra", {}).get("knosis", {}).get("agent") for s in t["steps"]] == [None, "Orchestrator", "WebSurfer", "Orchestrator"]
    text = json.dumps(t)
    assert "SECRET-REASON" not in text and "Renzo" not in text and "mistake" not in text
    t = normalize(root / "Who&When/Algorithm-Generated/1.json")
    assert len(t["steps"]) == 2 and t["extra"]["knosis"]["agents"]["Excel_Expert"]["instructions"].startswith("## Your role")
    assert t["extra"]["knosis"]["task"]["question"] == "a1"


def test_workspace_score_and_feedback(root, tmp_path):
    ds = load_dataset("whoandwhen", "all", root=root)
    assert len(ds.tasks) == 6 and ds.tasks[0].answer["step"] == 1 and ds.tasks[-1].answer["step"] == 3  # mistake_step + 1
    ws = w.init("whoandwhen", "all", tmp_path / "ws", root=str(root), dev=2, limit=4)
    dev = [json.loads(line) for line in (ws / "tasks/dev.jsonl").read_text().splitlines()]
    assert len(dev) == 2 and "reference_answer" not in dev[0] and (ws / dev[0]["trace"]).exists()
    leaked = [p for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts and "SECRET-REASON" in p.read_text(errors="ignore")]
    assert leaked == []
    golds = {t.id: t.answer for t in ds.tasks}
    sub = ws / "stages/1_explore/dev.jsonl"
    sub.write_text("".join(json.dumps({"id": t["id"], "answer": {"agent": golds[t["id"]]["agent"].lower(), "step": golds[t["id"]]["step"]}}) + "\n"
                           for t in dev))
    record = submit(ws, sub)
    assert record["metrics"]["agent"] == 1.0 and record["metrics"]["step"] == 1.0 and "SECRET-REASON" in record["items"][0]["gold"]
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = [json.loads(line) for line in (ws / "tasks/tasks.jsonl").read_text().splitlines()]
    assert len(tests) == 4
    rows = [{"id": tests[0]["id"], "answer": {"agent": golds[tests[0]["id"]]["agent"], "step": golds[tests[0]["id"]]["step"]}},
            {"id": tests[1]["id"], "answer": {"agent": golds[tests[1]["id"]]["agent"], "step": "99"}}]
    (ws / "stages/4_decide/predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    report = evaluate(ws)
    assert report["agent"] == 0.5 and report["step"] == 0.25 and report["missing"] == 2
    assert 0 < report["reference"]["random"]["step"] < 1


def test_with_reference_answer(root, tmp_path):
    ws = w.init("whoandwhen", "hand", tmp_path / "ws", root=str(root), dev=1, limit=2, answer="true")
    assert json.loads((ws / "tasks/dev.jsonl").read_text().splitlines()[0])["reference_answer"] == "Renzo Gracie"


@pytest.mark.skipif(not (data_dir("whoandwhen") / "Who&When").exists(), reason="Who&When data not downloaded")
def test_real_data():
    ds = load_dataset("whoandwhen")
    assert len(ds.tasks) == 184 and sum(t.kind == "hand" for t in ds.tasks) == 58
    for t in ds.tasks:
        trace = normalize(t.meta["file"], "whoandwhen")
        assert validate(trace) == [] and len(trace["steps"]) == t.meta["n_steps"] and 1 <= t.answer["step"] <= t.meta["n_steps"]
        assert t.answer["reason"] not in json.dumps(trace)
