import argparse
import json
import os
import pickle
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from knosis import tools
from knosis.cli import install_skill, main
from knosis.knowledge import check_units, load_units
from knosis.tools.tabpfn import run as tab
from knosis.tools.ultra import run as ultra


def test_registry_and_runner(tmp_path, monkeypatch, capsys):
    root = tmp_path / "tools"
    tool = root / "fake"
    tool.mkdir(parents=True)
    (tool / "TOOL.md").write_text(
        '---\nname: fake\nversion: "0.1"\nkind: skill\nmodality: [graph]\n'
        'stage: [explore]\nlicense: MIT\n---\nExample\n',
    )
    (tool / "run.py").write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('|'.join(sys.argv[2:]))\n",
    )
    monkeypatch.setattr(tools, "TOOLS_DIR", root)
    monkeypatch.setenv("KNOSIS_FAKE_PYTHON", sys.executable)
    assert tools.list_tools("graph")[0]["name"] == "fake"
    assert not tools.list_tools("table")
    output = tmp_path / "args.txt"
    assert tools.run_tool("fake", [str(output), "one", "two"]) == 0
    assert output.read_text() == "one|two"
    main(["tool", "list", "--modality", "graph"])
    assert "fake" in capsys.readouterr().out
    main(["tool", "card", "fake"])
    assert "Example" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        main(["tool", "run", "fake", "--", str(output), "three"])
    assert error.value.code == 0 and output.read_text() == "three"


def test_install(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    install_skill(home=tmp_path)
    for folder in (".agents", ".codex", ".claude"):
        text = (tmp_path / folder / "skills/knosis/SKILL.md").read_text()
        assert "name: knosis" in text
    custom = tmp_path / "custom"
    monkeypatch.setenv("CODEX_HOME", str(custom))
    install_skill(codex=True, home=tmp_path)
    assert (custom / "skills/knosis/SKILL.md").exists()


@pytest.fixture
def graph_file(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_nodes_from(["a", "b", "c", "isolated"])
    graph.add_edge("a", "b", label="owns")
    graph.add_edge("a", "b", label="owns")
    graph.add_edge("b", "c", label="transfers")
    graph.add_edge("c", "a", label="owns")
    path = tmp_path / "graph.gpickle"
    with path.open("wb") as fh:
        pickle.dump(graph, fh)
    return path, graph


def test_triples(graph_file):
    _, graph = graph_file
    encoded = ultra.graph_to_triples(graph)
    assert encoded["entities"] == ["a", "b", "c", "isolated"]
    assert encoded["relations"] == ["owns", "transfers"]
    assert len(encoded["direct"]) == 4 and len(encoded["triples"]) == 8
    assert encoded["triples"][4:] == [(t, r + 2, h) for h, r, t in encoded["direct"]]
    simple = ultra.graph_to_triples(nx.DiGraph(graph))
    assert len(simple["edges"]) == 3


def test_ultra_scores_and_units(graph_file):
    _, graph = graph_file
    encoded = ultra.graph_to_triples(graph)
    scores, missing = ultra.score_edges(encoded, lambda h, r: np.array([0.1, 0.4, 0.3, 0.2]), topk=3)
    assert len(scores) == graph.number_of_edges()
    assert len(scores.loc[(scores.src == "a") & (scores.dst == "b")]) == 2
    assert not ((missing.src == "a") & (missing.dst == "b")).any()
    assert scores.iloc[0]["rank"] == 1
    assert len(ultra.score_edges(encoded, lambda h, r: np.arange(4), max_edges=1)[0]) == 1
    units = ultra.findings(scores, missing, "data/graph.gpickle", 2)
    assert not check_units(units)
    assert all(u["status"] == "inferred" and "score" in u["meta"] for u in units)
    empty = ultra.graph_to_triples(nx.MultiDiGraph())
    scores, missing = ultra.score_edges(empty, lambda h, r: [], topk=2)
    assert not ultra.findings(scores, missing, "data/graph.gpickle", 2)


def test_ultra_prepare_subprocess(graph_file, tmp_path):
    path, graph = graph_file
    before = path.read_bytes()
    out = tmp_path / "out"
    assert tools.run_tool("ultra", ["--graph", str(path), "--out", str(out), "--prepare-only"]) == 0
    assert len(pd.read_parquet(out / "triples.parquet")) == 2 * graph.number_of_edges()
    assert json.loads((out / "mapping.json").read_text())["inverse_relation_offset"] == 2
    assert json.loads((out / "run.json").read_text())["parameters"]["prepare_only"]
    assert load_units(out / "units.jsonl") == []
    assert path.read_bytes() == before
    assert not (out / "edge_scores.parquet").exists()


def test_ultra_inference_output_contract(graph_file, tmp_path, monkeypatch):
    path, graph = graph_file
    monkeypatch.setattr(ultra, "load_model", lambda *args: (lambda h, r: np.arange(4), "cpu"))
    out = tmp_path / "out"
    ultra.main(["--graph", str(path), "--out", str(out), "--ckpt", "fake.pth", "--topk", "2"])
    assert len(pd.read_parquet(out / "edge_scores.parquet")) == graph.number_of_edges()
    assert (out / "missing_candidates.parquet").exists()
    assert load_units(out / "units.jsonl")
    assert json.loads((out / "run.json").read_text())["parameters"]["device"] == "cpu"


@pytest.fixture
def table_files(tmp_path):
    train = tmp_path / "train.parquet"
    test = tmp_path / "test.parquet"
    pd.DataFrame({"row_id": range(12), "x": range(12), "z": range(12), "y": ["a", "b"] * 6}).to_parquet(train)
    pd.DataFrame({"row_id": [40, 41], "x": [1, 3], "z": [2, 4]}).to_parquet(test)
    return train, test


@pytest.mark.parametrize("command", ["predict", "oof"])
def test_tabpfn_prepare_subprocess(table_files, tmp_path, command):
    train, test = table_files
    out = tmp_path / "out"
    args = [command, "--train", str(train), "--target", "y", "--out", str(out),
            "--prepare-only", "--max-rows", "3", "--max-features", "1"]
    if command == "predict":
        args.extend(["--test", str(test)])
    before = train.read_bytes(), test.read_bytes()
    assert tools.run_tool("tabpfn", args) == 0
    record = json.loads((out / "run.json").read_text())
    assert record["parameters"]["problem_type"] == "classification"
    assert len(record["parameters"]["fit_row_ids"]) == 3
    assert len(pd.read_parquet(out / "input_summary.parquet")) == 1
    assert load_units(out / "units.jsonl") == []
    assert (train.read_bytes(), test.read_bytes()) == before
    assert not (out / "predictions.parquet").exists()


class Classifier:
    classes_ = np.array(["a", "b"])

    def predict(self, x):
        return np.array(["a"] * len(x))

    def predict_proba(self, x):
        return np.array([[0.8, 0.2]] * len(x))


class Regressor:
    def predict(self, x, output_type=None, quantiles=None):
        values = np.asarray(x["x"], dtype=float)
        return [values - 1, values + 2] if output_type == "quantiles" else values


@pytest.mark.parametrize("kind, model", [("classification", Classifier()), ("regression", Regressor())])
def test_tabpfn_prediction_contract(kind, model):
    result = tab.predict_rows(model, pd.DataFrame({"x": [2, 4]}), [8, 9], kind)
    assert result.row_id.tolist() == [8, 9]
    if kind == "classification":
        assert result["probability_a"].tolist() == [0.8, 0.8]
        assert (result.uncertainty > 0).all()
    else:
        assert result.uncertainty.tolist() == [3, 3]


@pytest.mark.parametrize("kind", ["classification", "regression"])
def test_oof_contract(table_files, monkeypatch, kind):
    pytest.importorskip("sklearn")
    train = pd.read_parquet(table_files[0])
    if kind == "regression":
        train["y"] = train["x"] + 1
    calls = []

    def fit(rows, target, features, requested, args):
        calls.append(set(rows.row_id))
        return (Classifier() if requested == "classification" else Regressor()), rows.row_id.tolist()

    monkeypatch.setattr(tab, "fit_model", fit)
    args = argparse.Namespace(folds=3, seed=0)
    result, sampled = tab.oof(train, "y", ["x", "z"], kind, args)
    assert set(result.row_id) == set(train.row_id) and len(result) == len(train)
    for fold in range(3):
        assert not set(result.loc[result.fold == fold, "row_id"]) & calls[fold]
    assert len(sampled) == 3
    if kind == "classification":
        assert set(result.true_probability) == {0.8, 0.2}
    else:
        assert result.residual.tolist() == [1] * 12
    args.command, args.train, args.topk, args.model = "oof", "data/train.parquet", 3, "auto"
    assert not check_units(tab.findings(result, args))


@pytest.mark.parametrize("command", ["predict", "oof"])
def test_tabpfn_inference_output_contract(table_files, tmp_path, monkeypatch, command):
    if command == "oof":
        pytest.importorskip("sklearn")
    monkeypatch.setattr(tab, "fit_model",
                        lambda rows, *args: (Classifier(), rows.row_id.tolist()))
    train, test = table_files
    out = tmp_path / "out"
    args = [command, "--train", str(train), "--target", "y", "--out", str(out)]
    if command == "predict":
        args += ["--test", str(test)]
    else:
        args += ["--folds", "3"]
    tab.main(args)
    filename = "predictions.parquet" if command == "predict" else "oof_predictions.parquet"
    result = pd.read_parquet(out / filename)
    assert len(result) == (2 if command == "predict" else 12)
    units = load_units(out / "units.jsonl")
    assert units and all(u["status"] == "inferred" for u in units)
    assert (out / "run.json").exists()


@pytest.fixture
def cv_file(tmp_path):
    rng = np.random.default_rng(0)
    x, g = rng.normal(size=60), rng.choice(["p", "q"], size=60)
    path = tmp_path / "cv.parquet"
    pd.DataFrame({"x": x, "noise": rng.normal(size=60), "g": g,
                  "y": 3 * x + 5 * (g == "p") * (x > 0) + rng.normal(scale=0.1, size=60)}).to_parquet(path)
    return path


CV_VARIANTS = ["--variant", "inter=add:xp=(g==\"p\")&(x>0)", "--variant", "lean=drop:noise",
               "--variant", "ps=subset:g==\"p\""]


def test_tabpfn_cv_prepare_subprocess(cv_file, tmp_path):
    out = tmp_path / "out"
    assert tools.run_tool("tabpfn", ["cv", "--train", str(cv_file), "--target", "y", "--out", str(out),
                                     "--prepare-only", *CV_VARIANTS]) == 0
    plan = pd.read_csv(out / "cv_plan.csv").set_index("variant")
    assert plan.n_features.to_dict() == {"base": 3, "inter": 4, "lean": 2, "ps": 3}
    assert plan.loc["ps", "n_rows"] == (pd.read_parquet(cv_file).g == "p").sum() and plan.loc["base", "n_rows"] == 60
    assert load_units(out / "units.jsonl") == [] and not (out / "cv.csv").exists()


def test_tabpfn_variant_encoding(cv_file):
    frame, features, mask = tab.build_variant(pd.read_parquet(cv_file), ["x", "noise", "g"], 'add:xp=(g=="p")&(x>0);drop:noise')
    assert features == ["x", "g", "xp"] and mask.all()
    assert frame.xp.dtype.kind == "i" and frame.g.dtype.kind == "i"


class LinearModel:
    """Fake model fitting x linearly only; adds xp when present, so the sign of Δ is easy to judge."""

    def fit(self, x, y):
        design = np.column_stack([x[[c for c in ("x", "xp") if c in x]], np.ones(len(x))])
        self.columns = [c for c in ("x", "xp") if c in x]
        self.coef = np.linalg.lstsq(design, y, rcond=None)[0]
        return self

    def predict(self, x):
        return np.column_stack([x[self.columns], np.ones(len(x))]) @ self.coef


def test_tabpfn_cv_contract(cv_file, tmp_path, monkeypatch):
    monkeypatch.setattr(tab, "fit_model", lambda rows, target, features, *a: (LinearModel().fit(rows[features], rows[target]), []))
    out = tmp_path / "out"
    tab.main(["cv", "--train", str(cv_file), "--target", "y", "--folds", "3", "--out", str(out), *CV_VARIANTS,
              "--unit", "inter=k-1", "--unit", "lean=k-2"])
    table = pd.read_csv(out / "cv.csv").set_index("variant")
    assert table.loc["base", "delta"] == 0 and table.loc["inter", "delta"] < 0
    assert table.loc["lean", "delta"] == 0  # the fake model ignores noise
    ps = table.loc["ps"]
    assert ps.n_rows < 60 and ps.base_mean != table.loc["base", "mean"]
    units = load_units(out / "units.jsonl")
    assert [u["id"] for u in units] == ["tabpfn/cv/inter", "tabpfn/cv/lean", "tabpfn/cv/ps"] and not check_units(units)
    assert units[0]["provenance"].startswith("tool:tabpfn@0.2(cv,variant=inter")
    evidence = load_units(out / "evidence.jsonl")
    assert [(e["unit"], e["verdict"]) for e in evidence] == [("k-1", "support"), ("k-2", "undetermined")]
    assert all(e["method"] == "tool" and "id" not in e and "RMSE" in e["note"] for e in evidence)


def test_tabpfn_cv_real(cv_file, tmp_path, monkeypatch):
    pytest.importorskip("tabpfn")
    model = Path(os.environ.get("KNOSIS_TABPFN_MODEL", "/Users/eason/Desktop/optiver/cache/tabpfn-v3-regressor-v3_default.ckpt"))
    if not model.exists():
        pytest.skip("no local TabPFN regression weights")
    out = tmp_path / "out"
    tab.main(["cv", "--train", str(cv_file), "--target", "y", "--folds", "3", "--out", str(out), "--model", str(model),
              "--device", "cpu", *CV_VARIANTS[:2], "--unit", "inter=k-1"])
    table = pd.read_csv(out / "cv.csv")
    assert len(table) == 2 and np.isfinite(table["mean"]).all()
    assert load_units(out / "evidence.jsonl")[0]["unit"] == "k-1"
