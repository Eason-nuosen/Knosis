import json

import numpy as np
import pandas as pd
import pytest
import yaml

import knosis.decision.relbench as scorer  # noqa: F401  register
import knosis.workspace.exporters.relbench  # noqa: F401  register
from knosis import data_dir, load_dataset
from knosis import workspace as w
from knosis.decision import evaluate
from knosis.knowledge import feedback, load_units


def write_task(d, name, task_type, target, splits, **spec):
    tdir = d / "tasks" / name
    tdir.mkdir(parents=True)
    (tdir / "manifest.yaml").write_text(yaml.safe_dump({
        "name": name, "task_type": task_type, "target_col": target, "time_col": "date", "description": f"predict {target}",
        **spec}))
    for split, frame in splits.items():
        frame.to_parquet(tdir / f"{split}.parquet", index=False)


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "rel-x"
    (d / "db").mkdir(parents=True)
    (d / "manifest.yaml").write_text(yaml.safe_dump({
        "name": "rel-x", "description": "toy", "val_timestamp": "2020-01-01", "test_timestamp": "2021-01-01",
        "tables": {"users": {"pkey": "uid"}, "events": {"pkey": "eid", "time_col": "date", "fkeys": {"uid": "users"}}}}))
    pd.DataFrame({"uid": [1, 2, 3]}).to_parquet(d / "db/users.parquet")
    pd.DataFrame({"eid": [1, 2, 3], "uid": [1, 2, 3],
                  "date": pd.to_datetime(["2019-06-01", "2020-06-01", "2021-06-01"])}).to_parquet(d / "db/events.parquet")
    t = lambda *days: pd.to_datetime(list(days))  # noqa: E731
    write_task(d, "a-churn", "binary_classification", "churn", {
        "train": pd.DataFrame({"date": t("2019-01-01", "2019-02-01", "2019-03-01"), "uid": [1, 2, 3], "churn": [0, 1, 1]}),
        "val": pd.DataFrame({"date": t("2020-02-01", "2020-02-01"), "uid": [1, 2], "churn": [1, 0]}),
        "test": pd.DataFrame({"date": t("2021-02-01", "2021-02-01", "2021-02-01"), "uid": [1, 2, 3], "churn": [1, 0, 1]})},
        entity_col="uid")
    write_task(d, "b-ltv", "regression", "ltv", {
        "train": pd.DataFrame({"date": t("2019-01-01", "2019-01-01"), "uid": [1, 2], "ltv": [1.0, 3.0]}),
        "val": pd.DataFrame({"date": t("2020-02-01"), "uid": [1], "ltv": [2.0]}),
        "test": pd.DataFrame({"date": t("2021-02-01", "2021-02-01"), "uid": [1, 2], "ltv": [2.0, 4.0]})}, entity_col="uid")
    write_task(d, "c-buy", "recommendation", "item", {
        "train": pd.DataFrame({"date": t("2019-01-01", "2019-01-01"), "uid": [1, 2], "item": [[7, 8], [7]]}),
        "val": pd.DataFrame({"date": t("2020-02-01"), "uid": [1], "item": [[8]]}),
        "test": pd.DataFrame({"date": t("2021-02-01", "2021-02-01"), "uid": [1, 2], "item": [[7, 9], [5]]})},
        src_entity_col="uid", dst_entity_col="item", eval_k=2)
    return tmp_path


def test_export_hides_future_and_labels(root, tmp_path):
    ws = w.init("relbench", "rel-x", tmp_path / "ws", root=root)
    events = pd.read_parquet(ws / "data/db/events.parquet")
    assert events["eid"].tolist() == [1, 2]  # 2021-06-01 is after the test cutoff, not exported
    assert pd.read_parquet(ws / "data/db/users.parquet").shape == (3, 1)
    test = pd.read_parquet(ws / "data/test_features.parquet")
    assert list(test.columns) == ["row_id", "date", "uid"]
    assert list(pd.read_parquet(ws / "data/dev_features.parquet").columns) == ["row_id", "date", "uid"]
    assert "churn" in pd.read_parquet(ws / "data/train.parquet")
    assert [t["id"] for t in load_units(ws / "tasks/dev.jsonl")] == ["val-0", "val-1"]
    assert "AUROC" in (ws / "BRIEF.md").read_text() and "churn" not in json.dumps(load_units(ws / "tasks/dev.jsonl"))


def finish(ws, rows):
    w.goto(ws, "decide")
    w.next_prompt(ws)
    pd.DataFrame(rows).to_csv(ws / "stages/4_decide/predictions.csv", index=False)
    assert not w.check(ws)
    return evaluate(ws)


def test_binary(root, tmp_path):
    ws = w.init("relbench", "rel-x", tmp_path / "ws", root=root)
    report = finish(ws, {"row_id": ["test-0", "test-1", "test-2"], "prediction": [0.9, 0.1, 0.6]})
    assert report["roc_auc"] == 1.0 and report["task"] == "a-churn"
    dev = ws / "stages/4_decide/dev.csv"
    pd.DataFrame({"row_id": ["val-0"], "prediction": [0.2]}).to_csv(dev, index=False)
    record = feedback.submit(ws, dev)
    assert record["items"] == [{"id": "val-0", "ok": False, "score": 0.2, "gold": 1}]


def test_regression_and_recommendation(root, tmp_path):
    ws = w.init("relbench", "rel-x", tmp_path / "ws", root=root, task="b-ltv")
    report = finish(ws, {"row_id": ["test-0", "test-1"], "prediction": [2.0, 3.0]})
    assert report["mae"] == 0.5 and report["reference"]["train_mean"]["mae"] == 1.0
    ws = w.init("relbench", "rel-x", tmp_path / "ws2", root=root, task="c-buy", limit=1, seed=0)
    [task] = load_units(ws / "tasks/dev.jsonl")
    assert task["id"] == "val-0"
    w.goto(ws, "decide")
    w.next_prompt(ws)
    [test] = load_units(ws / "tasks/tasks.jsonl")
    pred = {"test-0": "[9, 7]", "test-1": "[1, 5]"}[test["id"]]
    pd.DataFrame({"row_id": [test["id"]], "prediction": [pred]}).to_csv(ws / "stages/4_decide/predictions.csv", index=False)
    report = evaluate(ws)
    assert report["map@2"] == (1.0 if test["id"] == "test-0" else 0.5)


def test_average_precision():
    assert scorer.average_precision([9, 7], [7, 9], 2) == 1.0
    assert scorer.average_precision([1, 5], [5], 2) == 0.5
    assert scorer.average_precision([], [5], 2) == 0.0


def test_real_relbench(tmp_path):
    if not data_dir("relbench").exists():
        pytest.skip("no local data for relbench")
    ws = w.init("relbench", "rel-f1", tmp_path / "ws", task="driver-dnf", limit=50)
    test_ts = pd.Timestamp(load_dataset("relbench", "rel-f1").schema["test_timestamp"])
    assert pd.read_parquet(ws / "data/db/races.parquet")["date"].max() < test_ts
    w.goto(ws, "decide")
    w.next_prompt(ws)
    ids = [t["id"] for t in load_units(ws / "tasks/tasks.jsonl")]
    pd.DataFrame({"row_id": ids, "prediction": np.linspace(0, 1, len(ids))}).to_csv(
        ws / "stages/4_decide/predictions.csv", index=False)
    assert 0 <= evaluate(ws)["roc_auc"] <= 1
