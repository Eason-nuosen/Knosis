import json

import pandas as pd
import pytest

import knosis.decision.bibench as scorer
import knosis.workspace.exporters.bibench  # noqa: F401  注册
from knosis import data_dir, list_scenarios
from knosis import workspace as w
from knosis.decision import evaluate
from knosis.knowledge import feedback, load_ontology, load_units, write_units


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def root(tmp_path):
    bench = tmp_path / "bi-bench"
    cases = {"1": "total amount?", "2-1": "amount per year?", "3": "count orders?"}
    put(bench / "queries.json", json.dumps(cases))
    for cid in cases:
        put(bench / cid / "Sales.csv", "Year,Amount\n2020,3\n2021,5\n")
    put(bench / "gt/1.csv", "total\n8\n")
    put(bench / "gt/2-1_1.csv", "Year,Amount\n2020,3\n2021,5\n")
    put(bench / "gt/2-1_2.csv", "Year,Amount\n2020,$3\n2021,$5\n")
    put(bench / "gt/3.csv", "n\n2\n")
    meta = tmp_path / "tools/data_management_tools"
    put(meta / "metadata/1/query_metadata.json", json.dumps({"tables": ["Sales.csv"]}))
    put(meta / "metadata/1/_tables.csv", "ID,Name\n1,Sales\n")
    put(meta / "metadata/1/_columns.csv",
        "ID,TableID,ExplicitName,InferredName,ExplicitDataType,InferredDataType,Type,Expression\n"
        "11,1,Year,,6,19,1,\n12,1,Amount,,8,19,1,\n")
    put(meta / "metadata/1/_relationships.csv",
        "ID,FromTableID,FromColumnID,FromCardinality,ToTableID,ToColumnID,ToCardinality,IsActive,CrossFilteringBehavior\n")
    put(meta / "transformation/1/unpivot/Sales.csv", "hint\n")
    put(meta / "join/1.csv", "case_id,from_table\n")
    return tmp_path


def test_matching_rules():
    m = scorer.matches
    gold = pd.DataFrame({"Year": [1991, 1992], "Share": ["8.95%", "9.15%"]})
    assert m(gold, pd.DataFrame({"y": [1992, 1991], "s": [0.0915, 0.0895]}))   # 行序无关，% 解析
    assert not m(gold, pd.DataFrame({"y": [1991], "s": [0.0895]}))              # 形状不同
    assert m(pd.DataFrame({"v": [8]}), pd.DataFrame({"a": ["x", "y"], "b": [1, 8.3]}))  # 1×1 只要出现
    assert not m(pd.DataFrame({"v": [8]}), pd.DataFrame({"b": [9]}))
    assert m(pd.DataFrame({"a": [100.0, None]}), pd.DataFrame({"a": [100.5, 0]}))     # 缺失记为 0
    assert scorer.table({"columns": ["a"], "rows": [[1], [2]]}).shape == (2, 1)
    assert scorer.table(3.5).shape == (1, 1)


def test_export_all_without_hints(root, tmp_path):
    ws = w.init("bibench", "all", tmp_path / "ws", root=root, dev=1, seed=0)
    assert sorted(p.name for p in (ws / "data").iterdir()) == ["1", "2-1", "3"]
    assert [p.name for p in (ws / "data/1").iterdir()] == ["Sales.csv"]
    text = json.dumps(load_units(ws / "tasks/dev.jsonl")) + (ws / "BRIEF.md").read_text()
    assert "query_metadata" not in text and "unpivot" not in text.replace("unpivot 等变换", "")
    assert not list(ws.rglob("gt")) and not (ws / "knowledge/ontology").exists()
    assert not list(ws.rglob("join")) and not list(ws.rglob("transformation"))
    assert len(load_units(ws / "tasks/dev.jsonl")) == 1


def test_score_and_feedback(root, tmp_path):
    ws = w.init("bibench", "all", tmp_path / "ws", root=root, dev=1, seed=0)
    [dev] = load_units(ws / "tasks/dev.jsonl")
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = [t["id"] for t in load_units(ws / "tasks/tasks.jsonl")]
    right = {"1": 8, "2-1": {"columns": ["Year", "Amount"], "rows": [[2021, 5], [2020, 3]]}, "3": 2}
    preds = [{"id": tid, "answer": right[tid] if i == 0 else 999} for i, tid in enumerate(tests)]
    write_units(ws / "stages/4_decide/predictions.jsonl", preds)
    assert not w.check(ws)
    assert evaluate(ws)["success"] == 0.5
    path = ws / "stages/4_decide/dev.jsonl"
    write_units(path, [{"id": dev["id"], "answer": right[dev["id"]]}])
    record = feedback.submit(ws, path)
    assert record["items"][0]["ok"] and record["items"][0]["gold"][0]["n_rows"] >= 1


def test_single_case_metadata(root, tmp_path):
    ws = w.init("bibench", "1", tmp_path / "ws", root=root, metadata=True)
    assert w.status(ws)["feedback"]["mode"] == "none"  # 单用例没有 dev 题
    docs = load_ontology(ws / "knowledge/ontology")
    assert [d["name"] for d in docs["semantic_model"]["datasets"]] == ["sales"]
    assert "knowledge/ontology/" in (ws / "BRIEF.md").read_text()
    w.goto(ws, "decide")
    w.next_prompt(ws)
    assert [t["id"] for t in load_units(ws / "tasks/tasks.jsonl")] == ["1"]


def test_real_bibench(tmp_path):
    if not data_dir("bibench").exists():
        pytest.skip("no local data for bibench")
    case = list_scenarios("bibench")[0]
    ws = w.init("bibench", case, tmp_path / "ws", metadata=True)
    w.goto(ws, "decide")
    w.next_prompt(ws)
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": case, "answer": 0}])
    assert evaluate(ws)["success"] in (0.0, 1.0)
    gold = pd.read_csv(sorted((data_dir("bibench") / "bi-bench/gt").glob(f"{case}*.csv"))[0])
    answer = {"columns": list(gold.columns), "rows": gold.to_numpy().tolist()}
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": case, "answer": answer}])
    assert evaluate(ws)["success"] == 1.0
