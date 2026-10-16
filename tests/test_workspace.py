import json
import pickle
import subprocess

import networkx as nx
import pandas as pd
import pytest

from knosis import data_dir, load_dataset
from knosis import workspace as w
from knosis.cli import main
from knosis.knowledge import load_units, write_units
from knosis.workspace.export import export_ngdbench, export_tabarena


@pytest.fixture
def tab_data(tmp_path):
    root = tmp_path / "raw"
    d = root / "toy"
    d.mkdir(parents=True)
    pd.DataFrame({"x": range(8), "y": ["a", "b"] * 4}).to_parquet(d / "data.parquet")
    pd.DataFrame({"repeat": [0] * 8, "fold": [0] * 8, "row": range(8),
                  "split": ["train"] * 5 + ["test"] * 3}).to_parquet(d / "splits.parquet")
    (d / "meta.json").write_text(json.dumps({
        "target": "y", "problem_type": "binary", "categorical": [],
        "n_rows": 8, "n_features": 1, "description": "toy data",
    }))
    return root


@pytest.fixture
def ngd_data(tmp_path):
    root = tmp_path / "ngd"
    d = root / "NGDBenchV1_1/NGDFin"
    (d / "graph").mkdir(parents=True)
    (d / "query").mkdir()
    clean = nx.MultiDiGraph()
    clean.add_node("Account:1", label="Account", balance=10)
    clean.add_node("Person:2", label="Person")
    clean.add_edge("Person:2", "Account:1", label="Person_Own_Account")
    perturbed = clean.copy()
    perturbed.graph["noise_info"] = "hidden"
    perturbed.nodes["Account:1"].update(original_name="secret", noise_similarity=0.4)
    perturbed.edges["Person:2", "Account:1", 0].update(is_noise=True, relation="secret", noise_similarity=0.2)
    for name, graph in [("fin.gpickle", clean), ("fin_noise_now.gpickle", perturbed)]:
        with (d / "graph" / name).open("wb") as fh:
            pickle.dump(graph, fh)
    (d / "query/complex_query.json").write_text(json.dumps([
        {"nlp": f"question {i}", "query": f"MATCH {i}", "clean_answer": "SECRET",
         "noise_answer": "HIDDEN", "same_as_cleangraph": True} for i in range(12)
    ]))
    (d / "query/management.json").write_text('[{"nlp": "admin", "answer": "SECRET"}]')
    (d / "noise_info").mkdir()
    return root


def valid_unit(**changes):
    return {"id": "u1", "content": "Training schema", "form": "schema",
            "provenance": "data/train.parquet#col/x", "status": "observed", **changes}


def test_export_graph(ngd_data, tmp_path):
    ds = load_dataset("ngdbench", "ngd-fin", root=ngd_data)
    ws = tmp_path / "ws"
    first = export_ngdbench(ds, ws)
    second = export_ngdbench(ds, ws, write_data=False)
    assert first == second
    with (ws / "data/graph.gpickle").open("rb") as fh:
        graph = pickle.load(fh)
    assert not graph.graph
    assert set(graph.nodes["Account:1"]) == {"label", "balance"}
    assert set(graph.edges["Person:2", "Account:1", 0]) == {"label"}
    assert len(first["holdout"]) == 6 and len(first["tasks"]) == 6
    assert not set(first["holdout"]) & {t["id"] for t in first["tasks"]}
    for task in first["tasks"]:
        assert set(task) == {"id", "kind", "question", "cypher"}
    assert "SECRET" not in json.dumps(first)
    assert "2 个节点" in first["brief"]
    assert set(p.name for p in (ws / "data").iterdir()) == {"graph.gpickle"}


def test_export_table(tab_data, tmp_path):
    exported = export_tabarena(load_dataset("tabarena", "toy", root=tab_data), tmp_path)
    train = pd.read_parquet(tmp_path / "data/train.parquet")
    test = pd.read_parquet(tmp_path / "data/test_features.parquet")
    assert train["row_id"].tolist() == list(range(5))
    assert test["row_id"].tolist() == [5, 6, 7]
    assert "y" in train and "y" not in test
    assert exported["output"] == "predictions.csv" and not exported["holdout"]
    assert "answer" not in exported["tasks"][0]


def test_workspace_flow(tab_data, tmp_path):
    ws = w.init("tabarena", "toy", tmp_path / "ws", root=tab_data)
    assert w.status(ws)["stage"] == "explore"
    assert not (ws / "tasks/tasks.jsonl").exists()
    assert "SECRET" not in (ws / ".knosis/state.json").read_text()
    assert "notes.md" in w.next_prompt(ws)
    assert w.check(ws)
    (ws / "stages/1_explore/notes.md").write_text("Training data has one feature.")
    assert not w.check(ws) and w.status(ws)["stage"] == "extract"
    assert w.check(ws)
    write_units(ws / "knowledge/units.jsonl", [valid_unit()])
    assert not w.check(ws) and w.status(ws)["stage"] == "refine"
    assert load_units(ws / "stages/2_extract/units.jsonl") == [valid_unit()]
    assert "round_1" in w.next_prompt(ws)
    assert w.check(ws)
    (ws / "stages/3_refine/round_1/changelog.md").write_text("Validated schema.")
    assert not w.check(ws) and w.status(ws)["round"] == 2
    w.goto(ws, "decide")
    assert "predictions.csv" in w.next_prompt(ws)
    assert len(load_units(ws / "tasks/tasks.jsonl")) == 1
    pd.DataFrame({"row_id": [5, 6, 7], "prediction": ["a", "a", "b"]}).to_csv(
        ws / "stages/4_decide/predictions.csv", index=False,
    )
    assert not w.check(ws) and w.status(ws)["completed"]
    count = subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=ws, text=True).strip()
    assert count == "6"
    empty = w.fork(ws, tmp_path / "none", "none")
    assert not load_units(empty / "knowledge/units.jsonl")
    assert not list((empty / "stages").rglob("*.*"))
    assert not (empty / "tasks/tasks.jsonl").exists()
    assert w.status(empty)["stage"] == "decide"
    assert subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=empty, text=True).strip() == "1"
    baseline = w.fork(ws, tmp_path / "baseline", "K_0")
    assert load_units(baseline / "knowledge/units.jsonl") == [valid_unit()]
    assert not list((baseline / "stages/3_refine").rglob("units.jsonl"))
    final = w.fork(ws, tmp_path / "final")
    assert (final / "stages/3_refine/round_1/units.jsonl").exists()


def test_history_retracted_parent(tab_data, tmp_path):
    ws = w.init("tabarena", "toy", tmp_path / "ws", root=tab_data)
    write_units(ws / "stages/2_extract/units.jsonl", [valid_unit(status="retracted")])
    write_units(ws / "knowledge/units.jsonl", [
        valid_unit(id="child", provenance="derived", derived_from=["u1"], status="verified"),
    ])
    w.goto(ws, "refine")
    w.next_prompt(ws)
    (ws / "stages/3_refine/round_1/changelog.md").write_text("Removed parent.")
    assert any("inactive parent" in issue for issue in w.check(ws))


@pytest.mark.parametrize("rows, values", [
    ([5, 6], ["a", "b"]), ([5, 6, 9], ["a", "b", "a"]),
    ([5, 6, 7, 7], ["a"] * 4), ([5, 6, 7], ["a", None, "b"]),
])
def test_table_prediction_rejected(tab_data, tmp_path, rows, values):
    ws = w.init("tabarena", "toy", tmp_path / "ws", root=tab_data)
    w.goto(ws, "decide")
    w.next_prompt(ws)
    pd.DataFrame({"row_id": rows, "prediction": values}).to_csv(
        ws / "stages/4_decide/predictions.csv", index=False,
    )
    assert w.check(ws)


def test_graph_predictions(ngd_data, tmp_path):
    ws = w.init("ngdbench", "ngd-fin", tmp_path / "ws", root=ngd_data)
    assert not list((ws / "tasks").iterdir())
    assert "- [complex_query] question 1\n" not in (ws / "BRIEF.md").read_text()
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tasks = load_units(ws / "tasks/tasks.jsonl")
    path = ws / "stages/4_decide/predictions.jsonl"
    write_units(path, [{"id": "unknown", "answer": None}])
    assert w.check(ws)
    write_units(path, [{"id": t["id"], "answer": None} for t in tasks])
    assert not w.check(ws)


def test_cli(tab_data, tmp_path, capsys):
    ws = tmp_path / "ws"
    main(["ws", "init", "tabarena", "toy", "--root", str(tab_data), "--out", str(ws)])
    main(["ws", "status", str(ws)])
    assert '"stage": "explore"' in capsys.readouterr().out
    main(["ws", "next", str(ws)])
    with pytest.raises(SystemExit) as error:
        main(["ws", "check", str(ws)])
    assert error.value.code == 1
    main(["ws", "goto", str(ws), "decide"])
    assert w.status(ws)["stage"] == "decide"


@pytest.mark.parametrize("name, scenario", [("ngdbench", "ngd-fin"), ("tabarena", "houses")])
def test_real_exports(name, scenario, tmp_path):
    if not data_dir(name).exists():
        pytest.skip(f"no local data for {name}")
    ws = w.init(name, scenario, tmp_path / "ws")
    assert not (ws / "tasks/tasks.jsonl").exists()
    if name == "ngdbench":
        with (ws / "data/graph.gpickle").open("rb") as fh:
            graph = pickle.load(fh)
        assert {k for *_, attrs in graph.edges(data=True) for k in attrs} == {"label"}
    else:
        target = load_dataset(name, scenario).schema["target"]
        assert target not in pd.read_parquet(ws / "data/test_features.parquet")
