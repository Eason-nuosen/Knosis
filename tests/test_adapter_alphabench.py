import json

import numpy as np
import pandas as pd
import pytest

from knosis import data_dir, load_dataset
from knosis import workspace as w
from knosis.decision import alphabench as scorer
from knosis.knowledge import feedback, load_units, write_units
from knosis.workspace.exporters import alphabench  # noqa: F401  注册导出器


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "alphabench"
    raw = base / "benchmark/data/evaluate/raw"
    raw.mkdir(parents=True)
    (base / "benchmark/data/evaluate/pool").mkdir(parents=True)
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2021-01-04", periods=60)
    # 每类各 10 个：pos 均值 0.05，neg -0.05，noise 0
    means = {f"pos{i}": 0.05 for i in range(10)} | {f"neg{i}": -0.05 for i in range(10)} | {f"noise{i}": 0.0 for i in range(10)}
    ic = pd.DataFrame({n: m + rng.normal(0, 0.002, len(days)) for n, m in means.items()}, index=days).rename_axis("datetime")
    ic.to_csv(raw / "ic_table_csi300.csv")
    (ic * 1.2).to_csv(raw / "rankic_table_csi300.csv")
    pool = {n: f"Mean($close, {i + 2})" for i, n in enumerate(means)} | {"extra": "Std($volume, 5)"}
    (base / "benchmark/data/evaluate/pool/factor_pool.json").write_text(json.dumps(pool))
    qlib = base / "qlib_data/cn_data"
    calendar = pd.bdate_range("2020-12-01", "2021-02-26").strftime("%Y-%m-%d")
    (qlib / "calendars").mkdir(parents=True)
    (qlib / "calendars/day.txt").write_text("\n".join(calendar))
    (qlib / "instruments").mkdir()
    (qlib / "instruments/csi300.txt").write_text("SH600000\t2020-12-01\t2021-02-26\nSH600001\t2021-02-01\t2021-02-26\n")
    for name in ("sh600000", "sh600001"):
        (qlib / "features" / name).mkdir(parents=True)
        for field in ("close", "volume"):
            np.concatenate([[0], np.arange(len(calendar))]).astype("<f4").tofile(qlib / "features" / name / f"{field}.day.bin")
    return base


def export(root, tmp_path, **kw):
    return w.init("alphabench", "evaluate", tmp_path / "ws", root=root, dev=5, limit=15, start="2021-01-04", end="2021-03-31", **kw)


def test_stats_follow_upstream(root):
    ds = load_dataset("alphabench", "evaluate", root=root)
    stats = scorer.factor_stats(str(ds.files["ic"]), str(ds.files["rankic"]), "2021-01-04", "2021-03-31")
    assert (stats.loc[[f"pos{i}" for i in range(10)], "signal"] == "Positive").all()
    assert (stats.loc[[f"noise{i}" for i in range(10)], ["Performance", "Stability"]] == 1).all().all()
    assert set(stats.loc[[f"neg{i}" for i in range(10)], "Performance"]) == {1, 2, 3, 4, 5}
    assert stats.loc["pos0", "win_rate"] == 1.0


def test_export_hides_window_and_gt(root, tmp_path):
    ws = export(root, tmp_path)
    panel = pd.read_parquet(ws / "data/market.parquet")
    assert panel["datetime"].max() < pd.Timestamp("2021-01-04")
    assert set(panel["instrument"]) == {"SH600000"}  # 另一只股票只在窗口内进入指数
    members = pd.read_csv(ws / "data/csi300_members.csv")
    assert members["end"].max() < "2021-01-04"
    dev = load_units(ws / "tasks/dev.jsonl")
    assert len(dev) == 5 and all(set(t) == {"id", "factor", "expression"} for t in dev)
    text = (ws / "BRIEF.md").read_text()
    assert "Ref($close, -1)/$close - 1" in text and "`Std`" in text and "`$volume`" in text
    assert not list(ws.rglob("*ic_table*"))
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    assert len(tests) == 15 and not {t["id"] for t in tests} & {t["id"] for t in dev}


def test_score_and_feedback(root, tmp_path):
    ws = export(root, tmp_path, feedback="score")
    dev = load_units(ws / "tasks/dev.jsonl")
    path = ws / "stages/1_explore/dev.jsonl"
    guess = {"pos": ("Positive", 0.05), "neg": ("Negative", -0.05), "noi": ("Noise", 0.0)}
    write_units(path, [{"id": t["id"], "answer": {"signal": guess[t["factor"][:3]][0], "mean_ic": guess[t["factor"][:3]][1],
                                                  "scores": {"Performance": 1}}} for t in dev])
    record = feedback.submit(ws, path)
    assert record["metrics"]["signal_accuracy"] == 1.0 and record["metrics"]["mean_ic_mae"] < 0.01
    assert "Performance_accuracy" in record["metrics"] and "Stability_accuracy" not in record["metrics"]
    assert all(i["ok"] and "gold" not in i for i in record["items"])
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": t["id"], "answer": {"signal": "Noise"}} for t in tests])
    assert not w.check(ws)
    from knosis.decision import evaluate

    report = evaluate(ws)
    assert report["signal_accuracy"] == report["reference"]["all_noise_zero_ic"]["signal_accuracy"]
    assert "mean_ic_mae" not in report


def test_real_data(tmp_path):
    ds_dir = data_dir("alphabench")
    if not (ds_dir / "benchmark/data/evaluate/raw/ic_table_csi300.csv").exists() or not (ds_dir / "qlib_data/cn_data").exists():
        pytest.skip("no local AlphaBench IC tables / Qlib data")
    ws = w.init("alphabench", "evaluate", tmp_path / "ws", dev=10, limit=30)
    panel = pd.read_parquet(ws / "data/market.parquet")
    assert panel["datetime"].max() < pd.Timestamp("2021-01-01") and len(panel) > 100000
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/predictions.jsonl",
                [{"id": t["id"], "answer": {"signal": "Positive", "mean_ic": 0.02}} for t in tests])
    from knosis.decision import evaluate

    report = evaluate(ws)
    assert report["n"] == 30 and 0 <= report["signal_accuracy"] <= 1
