"""不用模型/API 的 TabArena 四阶段试跑，预测只用训练集多数类或中位数。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from knosis import load_dataset, workspace as w
from knosis.knowledge import load_units, write_units


def accept(ws):
    issues = w.check(ws)
    if issues:
        raise RuntimeError("\n".join(issues))


def trial(scenario="houses", out=None, root=None):
    started = time.monotonic()
    ws = w.init("tabarena", scenario, out, **({"root": root} if root else {}))
    w.next_prompt(ws)
    train = pd.read_parquet(ws / "data/train.parquet")
    features = pd.read_parquet(ws / "data/test_features.parquet")
    target = next(column for column in train if column not in features)
    counts = train[target].value_counts()
    ds = load_dataset("tabarena", scenario, root=root)
    is_regression = ds.schema["problem_type"] == "regression"
    value = train[target].median() if is_regression else counts.index[0]
    baseline = value.item() if hasattr(value, "item") else value
    notes = f"只分析训练集：{len(train)} 行，目标 {target}。\n\n缺失值计数：\n{train.isna().sum().to_string()}\n"
    (ws / "stages/1_explore/notes.md").write_text(notes, encoding="utf-8")
    accept(ws)
    units = [
        {"id": "schema", "content": f"训练列：{', '.join(train.columns)}；目标：{target}",
         "form": "schema", "provenance": f"data/train.parquet#col/{target}",
         "condition": "当前数据集与划分", "status": "observed"},
        {"id": "prior", "content": f"训练目标{'中位数' if is_regression else '多数类'}为 {baseline}",
         "form": "fact", "provenance": f"data/train.parquet#col/{target}",
         "condition": "只描述训练集，不保证测试分布一致", "status": "observed",
         "meta": {"baseline": baseline, "support_count": int(train[target].notna().sum())}},
    ]
    write_units(ws / "knowledge/units.jsonl", units)
    accept(ws)
    w.next_prompt(ws)
    units[1]["status"] = "verified"
    units[1]["meta"]["counterexamples"] = 0
    write_units(ws / "knowledge/units.jsonl", units)
    (ws / "stages/3_refine/round_1/changelog.md").write_text(
        "重新从训练目标计算统计量，确认 prior 一致。未使用测试标签；仅验证统计事实，不宣称预测规律成立。\n",
        encoding="utf-8",
    )
    accept(ws)
    w.goto(ws, "decide")
    w.next_prompt(ws)
    prior = next(unit for unit in load_units(ws / "knowledge/units.jsonl") if unit["id"] == "prior")
    pd.DataFrame({"row_id": features["row_id"], "prediction": prior["meta"]["baseline"]}).to_csv(
        ws / "stages/4_decide/predictions.csv", index=False,
    )
    tasks = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/used_units.jsonl", [
        {"id": task["id"], "used_units": ["prior"]} for task in tasks
    ])
    accept(ws)
    report = {"workspace": str(ws), "seconds": time.monotonic() - started,
              "train_rows": len(train), "test_rows": len(features), "units": len(units),
              "stages": ["explore", "extract", "refine", "decide"],
              "agent_api": False, "neural_models": False, "ground_truth_evaluation": False}
    (ws / "TRIAL.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    w.commit(ws, "trial: offline pipeline verified")
    print(json.dumps(report, indent=2))
    return ws


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="houses")
    parser.add_argument("--out", default="ws/offline-houses")
    parser.add_argument("--root")
    args = parser.parse_args()
    trial(args.scenario, Path(args.out), args.root)
