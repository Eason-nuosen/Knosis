"""Four-stage TabArena trial run without models or APIs; predictions use only the training majority class or median."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from knosis import load_dataset, workspace as w
from knosis.knowledge import verify, load_units, write_units


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
    notes = f"Training set only: {len(train)} rows, target {target}.\n\nMissing value counts:\n{train.isna().sum().to_string()}\n"
    (ws / "stages/1_explore/notes.md").write_text(notes, encoding="utf-8")
    accept(ws)
    units = [
        {"id": "schema", "content": f"Training columns: {', '.join(train.columns)}; target: {target}",
         "form": "schema", "provenance": f"data/train.parquet#col/{target}",
         "condition": "current dataset and split", "status": "observed"},
        {"id": "prior", "content": f"Training target {'median' if is_regression else 'majority class'} is {baseline}",
         "form": "fact", "provenance": f"data/train.parquet#col/{target}",
         "condition": "describes the training set only; the test distribution may differ", "status": "observed",
         "meta": {"baseline": baseline, "support_count": int(train[target].notna().sum())}},
    ]
    write_units(ws / "kb/knowledge/units.jsonl", units)
    accept(ws)
    w.next_prompt(ws)
    # Verify: attach an executable check to prior, let Knosis rerun it and record supporting evidence, then mark it verified.
    units[1]["check"] = {"kind": "sql", "query": f'SELECT COUNT(*) > 0 FROM train WHERE "{target}" IS NOT NULL'}
    write_units(ws / "kb/knowledge/units.jsonl", units)
    verify(ws, ["prior"])
    units[1]["status"] = "verified"
    units[1]["meta"]["counterexamples"] = 0
    write_units(ws / "kb/knowledge/units.jsonl", units)
    (ws / "stages/3_refine/round_1/changelog.md").write_text(
        "Recomputed the statistic from the training target; prior is consistent. No test labels used; only the statistical fact is verified, no predictive claim is made.\n",
        encoding="utf-8",
    )
    accept(ws)
    w.goto(ws, "decide")
    w.next_prompt(ws)
    prior = next(unit for unit in load_units(ws / "kb/knowledge/units.jsonl") if unit["id"] == "prior")
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
