import json

import pytest

from knosis import data_dir, load_dataset
from knosis import workspace as w
from knosis.decision import evaluate
from knosis.decision import kramabench as scorer
from knosis.knowledge import feedback, load_units, write_units
from knosis.workspace.exporters import kramabench  # noqa: F401  register exporter

TASKS = [
    {"id": "fire-easy-1", "query": "q1", "answer": 7805421, "answer_type": "numeric_exact", "subtasks": [{"id": "s", "query": "SUB"}]},
    {"id": "fire-easy-2", "query": "q2", "answer": "EACC", "answer_type": "string_exact"},
    {"id": "fire-hard-3", "query": "q3", "answer": ["California", "Nevada"], "answer_type": "list_exact"},
    {"id": "fire-hard-4", "query": "q4", "answer": 0.519, "answer_type": "numeric_approximate"},
    {"id": "fire-hard-5", "query": "q5", "answer": "Great Basin Area", "answer_type": "string_approximate"},
    {"id": "fire-hard-6", "query": "q6", "answer": [6.326, 0.787], "answer_type": "list_approximate"},
    {"id": "fire-hard-7", "query": "q7", "answer": 4.65, "answer_type": "numeric_exact"},
    {"id": "fire-hard-8", "query": "q8", "answer": "No", "answer_type": "string_exact"},
]


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "krama"
    (base / "workload").mkdir(parents=True)
    (base / "workload/fire.json").write_text(json.dumps(TASKS))
    lake = base / "data/fire/input"
    (lake / "sub").mkdir(parents=True)
    (lake / "a.csv").write_text("x,y\n1,2\n")
    (lake / "sub/b.json").write_text("{}")
    (base / "solutions/fire").mkdir(parents=True)
    (base / "solutions/fire/fire-easy-1.py").write_text("print(7805421)")
    return base


def test_export_hides_answers(root, tmp_path):
    ws = w.init("kramabench", "fire", tmp_path / "ws", root=root)
    assert sorted(p.relative_to(ws / "data").as_posix() for p in (ws / "data").rglob("*") if p.is_file()) == ["a.csv", "sub/b.json"]
    dev = load_units(ws / "tasks/dev.jsonl")
    assert len(dev) == 2 and set(dev[0]) == {"id", "question", "answer_kind"}
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    assert len(tests) == 6 and not {t["id"] for t in tests} & {t["id"] for t in dev}
    visible = "".join(p.read_text() for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts and p.suffix != ".gpickle")
    for secret in ("7805421", "EACC", "Great Basin", "SUB", "print("):
        assert secret not in visible
    assert "8 个文件" not in (ws / "BRIEF.md").read_text() and "2 个文件" in (ws / "BRIEF.md").read_text()


def test_score_and_feedback(root, tmp_path):
    ws = w.init("kramabench", "fire", tmp_path / "ws", root=root)
    gold = {t["id"]: t["answer"] for t in TASKS}
    dev = load_units(ws / "tasks/dev.jsonl")
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": dev[0]["id"], "answer": gold[dev[0]["id"]]}, {"id": dev[1]["id"], "answer": "wrong"}])
    record = feedback.submit(ws, path)
    assert [i["ok"] for i in record["items"]] == [True, False] and "gold" in record["items"][1]
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": t["id"], "answer": gold[t["id"]]} for t in tests])
    assert not w.check(ws)
    report = evaluate(ws)
    assert report["accuracy"] == 1.0 and report["score"] == 1.0 and report["missing"] == 0


@pytest.mark.parametrize("kind, pred, gold, ok", [
    ("numeric_exact", "7805421", 7805421, True), ("numeric_exact", 4.6500001, 4.65, True), ("numeric_exact", 4.7, 4.65, False),
    ("numeric_exact", "50%", 0.5, True), ("string_exact", " eacc ", "EACC", True), ("string_exact", 3, "EACC", False),
    ("numeric_approximate", 0.52, 0.519, True), ("numeric_approximate", 0.6, 0.519, False),
    ("list_exact", ["nevada", "California"], ["California", "Nevada"], True), ("list_exact", "California, Nevada", ["California", "Nevada"], True),
    ("list_exact", ["California"], ["California", "Nevada"], False), ("list_approximate", [6.33, 0.787], [6.326, 0.787], True),
    ("string_approximate", "great basin area.", "Great Basin Area", True), ("string_approximate", None, "x", False),
])
def test_metrics(kind, pred, gold, ok):
    assert scorer.score_answer(kind, pred, gold)[1] is ok


def test_list_partial_f1():
    assert scorer.score_answer("list_exact", ["California", "Texas"], ["California", "Nevada"])[0] == 0.5
    assert scorer.score_answer("numeric_approximate", 0.519, 0.519)[0] == 1.0


def test_real_data(tmp_path):
    if not data_dir("kramabench").exists():
        pytest.skip("no local data for kramabench")
    ws = w.init("kramabench", "wildfire", tmp_path / "ws")
    ds = load_dataset("kramabench", "wildfire")
    assert not list((ws / "data").rglob("*.py")) or all(p.name == "load_data.py" for p in (ws / "data").rglob("*.py"))
    gold = {t.id: t.answer for t in ds.tasks}
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": t["id"], "answer": gold[t["id"]]} for t in tests])
    assert not w.check(ws)
    assert evaluate(ws)["accuracy"] == 1.0
