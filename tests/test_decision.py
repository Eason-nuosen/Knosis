import json
import pickle

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from knosis import workspace as w
from knosis.cli import main
from knosis.decision import evaluate, graph_qa, tabular
from knosis.knowledge import load_units, write_units


def test_answer_sets():
    s = graph_qa.answer_set
    assert s(12) == s([12.0]) == s("12") == s(["12", "12"])
    assert s([{"a": "x", "cnt": 1}]) == s([{"b": "x", "n": 1.0}])
    assert s([{"b.createTime": "t1"}, {"b.createTime": "t2"}]) == s(["t1", "t2"])
    assert s(True) == s("true") == frozenset({"true"})
    assert graph_qa.f1(s(["a", "b"]), s(["a"])) == pytest.approx(2 / 3)
    assert graph_qa.f1(s([]), s([])) == 1.0


def test_tabular_metrics():
    assert tabular.regression([1, 2, 3], [1, 2, 3]) == {"rmse": 0.0, "mae": 0.0, "r2": 1.0}
    y = ["a", "b", "b", "a"]
    preds = pd.DataFrame({"prediction": ["a", "b", "a", "a"], "probability_a": [0.9, 0.2, 0.6, 0.7],
                          "probability_b": [0.1, 0.8, 0.4, 0.3]})
    m = tabular.classification(y, preds, ["a", "b"])
    assert m["accuracy"] == 0.75 and m["roc_auc"] == 1.0 and m["log_loss"] > 0
    assert set(tabular.classification(y, preds[["prediction"]], ["a", "b"])) == {"accuracy"}
    assert tabular.roc_auc(np.array([True, False, True]), np.array([0.2, 0.5, 0.9])) == 0.5


@pytest.fixture
def tab_ws(tmp_path):
    root = tmp_path / "raw/toy"
    root.mkdir(parents=True)
    pd.DataFrame({"x": range(8), "y": ["a", "b"] * 4}).to_parquet(root / "data.parquet")
    pd.DataFrame({"repeat": 0, "fold": 0, "row": range(8), "split": ["train"] * 5 + ["test"] * 3}).to_parquet(root / "splits.parquet")
    (root / "meta.json").write_text(json.dumps({"target": "y", "problem_type": "binary", "categorical": [], "n_rows": 8, "n_features": 1}))
    ws = w.init("tabarena", "toy", tmp_path / "ws", root=root.parent)
    w.goto(ws, "decide")
    w.next_prompt(ws)
    return ws


def test_evaluate_tabular(tab_ws, capsys):
    # test rows 5,6,7 have truth b,a,b
    pd.DataFrame({"row_id": [5, 6, 7], "prediction": ["b", "a", "a"]}).to_csv(tab_ws / "stages/4_decide/predictions.csv", index=False)
    write_units(tab_ws / "kb/knowledge/units.jsonl", [{"id": "k", "content": "c", "form": "fact", "provenance": "tool:x@1()", "status": "stale"}])
    write_units(tab_ws / "stages/4_decide/used_units.jsonl", [{"id": 5, "used_units": ["k"]}, {"id": 6, "used_units": ["ghost"]}])
    report = evaluate(tab_ws)
    assert report["accuracy"] == pytest.approx(2 / 3) and report["n"] == 3
    assert report["reference"]["train_prior"]["accuracy"] == pytest.approx(1 / 3)  # training majority class a, test truth b,a,b
    assert report["usage"]["unknown_units"] == ["ghost"] and report["usage"]["inactive_units"] == ["k"]
    assert json.loads((tab_ws / ".knosis/eval.json").read_text())["accuracy"] == report["accuracy"]
    main(["eval", str(tab_ws)])
    assert '"accuracy"' in capsys.readouterr().out


def test_evaluate_blocked_inside_agent(tab_ws, monkeypatch):
    monkeypatch.setenv("KNOSIS_DEPTH", "1")
    with pytest.raises(RuntimeError, match="disabled"):
        evaluate(tab_ws)


def test_evaluate_graph(tmp_path):
    d = tmp_path / "ngd/NGDBenchV1_1/NGDFin"
    (d / "graph").mkdir(parents=True)
    (d / "query").mkdir()
    graph = nx.MultiDiGraph()
    graph.add_node("A:1", label="A")
    for name in ("fin.gpickle", "fin_noise_x.gpickle"):
        with (d / "graph" / name).open("wb") as fh:
            pickle.dump(graph, fh)
    (d / "query/complex_query_agg.json").write_text(json.dumps(
        [{"nlp": f"q{i}", "query": "MATCH", "clean_answer": i, "noise_answer": i if i % 2 else -1} for i in range(20)]))
    ws = w.init("ngdbench", "ngd-fin", tmp_path / "ws", root=tmp_path / "ngd", dev=4, limit=5, seed=1)
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tasks = load_units(ws / "tasks/tasks.jsonl")
    assert len(tasks) == 5
    gold = {f"ngd-fin/complex_query_agg/{i}": i for i in range(20)}
    preds = [{"id": t["id"], "answer": gold[t["id"]] if n < 3 else "wrong"} for n, t in enumerate(tasks)]
    write_units(ws / "stages/4_decide/predictions.jsonl", preds)
    assert not w.check(ws)
    report = evaluate(ws)
    assert report["n"] == 5 and report["answer_set_em"] == pytest.approx(0.6) and report["missing"] == 0
    assert set(report["by_kind"]) == {"complex_query_agg"}
    assert 0 <= report["reference"]["noisy_graph_answer"]["answer_set_em"] <= 1
