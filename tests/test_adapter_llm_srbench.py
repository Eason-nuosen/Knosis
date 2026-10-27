import json

import h5py
import numpy as np
import pandas as pd
import pytest

import knosis.decision.llm_srbench  # noqa: F401  register scorer
import knosis.workspace.exporters.llm_srbench  # noqa: F401  register exporter
from knosis import data_dir
from knosis import workspace as w
from knosis.decision import evaluate
from knosis.knowledge import feedback, load_units, write_units


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "srb"
    (base / "data").mkdir(parents=True)
    names = [f"P{i}" for i in range(5)]
    pd.DataFrame({"name": names, "symbols": [["y", "x", "t"]] * 5, "symbol_descs": [["out", "in", "time"]] * 5,
                  "symbol_properties": [["O", "V", "V"]] * 5,
                  "expression": [f"{i + 1}*x + t" for i in range(5)]}).to_parquet(base / "data/lsr_synth_matsci-0.parquet")
    rng = np.random.default_rng(0)
    with h5py.File(base / "lsr_bench_data.hdf5", "w") as h5:
        for i, name in enumerate(names):
            for split in ("train", "test", "ood_test"):
                x, t = rng.uniform(1, 2, (2, 20))
                h5[f"lsr_synth/matsci/{name}/{split}"] = np.stack([(i + 1) * x + t, x, t], axis=1)
    return base


def test_export_hides_gt(root, tmp_path):
    ws = w.init("llm-srbench", "lsr_synth_matsci", tmp_path / "ws", root=root)
    dev = load_units(ws / "tasks/dev.jsonl")
    assert len(dev) == 1
    train = pd.read_parquet(ws / "data/P0/train.parquet")
    assert list(train.columns) == ["y", "x", "t"] and len(train) == 20
    assert sorted(p.name for p in (ws / "data/P0").iterdir()) == ["train.parquet"]
    text = (ws / "BRIEF.md").read_text() + json.dumps(dev) + (ws / ".knosis/state.json").read_text()
    assert "*x + t" not in text
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tasks = load_units(ws / "tasks/tasks.jsonl")
    assert len(tasks) == 4 and not {t["id"] for t in tasks} & {d["id"] for d in dev}


def test_score_and_feedback(root, tmp_path):
    ws = w.init("llm-srbench", "lsr_synth_matsci", tmp_path / "ws", root=root)
    [dev] = load_units(ws / "tasks/dev.jsonl")
    k = int(dev["name"][1:]) + 1
    path = ws / "stages/1_explore/dev_predictions.jsonl"
    write_units(path, [{"id": dev["id"], "answer": f"{k}*x + t"}])
    record = feedback.submit(ws, path)
    [item] = record["items"]
    assert item["ok"] and item["nmse"] < 1e-10 and item["ood_ok"] and item["gold"] == f"{k}*x + t"
    write_units(path, [{"id": dev["id"], "answer": "np.log(-x) + "}])
    assert not feedback.submit(ws, path)["items"][0]["ok"]
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tasks = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/predictions.jsonl",
                [{"id": t["id"], "answer": f"{int(t['name'][1:]) + 1}*x + t" if n else "x"} for n, t in enumerate(tasks)])
    assert not w.check(ws)
    report = evaluate(ws)
    assert report["acc_0.1"] == 0.75 and report["ood_acc_0.1"] == 0.75 and report["missing"] == 0


def test_real_data(tmp_path):
    if not data_dir("llm-srbench").exists():
        pytest.skip("no local data for llm-srbench")
    ws = w.init("llm-srbench", "lsr_synth_bio_pop_growth", tmp_path / "ws")
    dev = load_units(ws / "tasks/dev.jsonl")
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": d["id"], "answer": "0*t"} for d in dev])
    record = feedback.submit(ws, path)
    assert len(record["items"]) == len(dev) and not any(i["ok"] for i in record["items"])
