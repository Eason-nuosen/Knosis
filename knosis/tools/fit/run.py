"""Symbolic expression fitting: curve_fit the free constants C0, C1, ..., evaluate on the validation set and diagnose residuals."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import curve_fit

from knosis import lang
from knosis.tools import write_result

FUNCTIONS = {name: getattr(np, name) for name in
             ("exp", "log", "sin", "cos", "tan", "sqrt", "abs", "tanh", "arcsin", "arccos", "arctan", "pi")}


def constants(expr) -> list[str]:
    return sorted(set(re.findall(r"\bC\d+\b", expr)), key=lambda c: int(c[1:]))


def evaluate(expr, frame, values: dict):
    with np.errstate(all="ignore"):
        result = eval(expr, {"np": np, **FUNCTIONS}, {**{c: frame[c].to_numpy(dtype=float) for c in frame}, **values})
    return np.broadcast_to(np.asarray(result, dtype=float), len(frame))


def substitute(expr, values: dict) -> str:
    return re.sub(r"\bC\d+\b", lambda m: f"{values[m.group()]:.6g}" if values[m.group()] >= 0 else f"({values[m.group()]:.6g})", expr)


def nmse(y, pred) -> float:
    return float(np.mean((y - pred) ** 2) / np.var(y))


def diagnostics(residual, frame) -> list[dict]:
    """Correlation of validation residuals with each input and its square, sorted by |Spearman| descending."""
    rows = []
    for column in frame:
        for name, x in ((column, frame[column].to_numpy(dtype=float)), (f"{column}^2", frame[column].to_numpy(dtype=float) ** 2)):
            pearson, spearman = stats.pearsonr(x, residual)[0], stats.spearmanr(x, residual)[0]
            rows.append({"term": name, "pearson": round(float(np.nan_to_num(pearson)), 4),
                         "spearman": round(float(np.nan_to_num(spearman)), 4)})  # correlation is undefined for constant residuals; record 0
    return sorted(rows, key=lambda r: -abs(r["spearman"]))


def fit(expr, data, target, init, split, seed) -> dict:
    names = constants(expr)
    inputs = data.drop(columns=[target, "row_id"], errors="ignore")
    order = np.random.default_rng(seed).permutation(len(data))
    cut = int(split * len(data))
    train, valid = order[:cut], order[cut:]
    y = data[target].to_numpy(dtype=float)
    result = {"expr": expr, "target": target, "constants": names, "n_constants": len(names),
              "n_train": len(train), "n_valid": len(valid),
              "ranges": {c: [float(inputs[c].iloc[train].min()), float(inputs[c].iloc[train].max())] for c in inputs}}
    try:
        values = {}
        if names:
            fitted, _ = curve_fit(lambda _, *p: evaluate(expr, inputs.iloc[train], dict(zip(names, p))), None, y[train],
                                  p0=[init.get(c, 1.0) for c in names], maxfev=20000)
            values = dict(zip(names, map(float, fitted)))
        pred_train, pred_valid = evaluate(expr, inputs.iloc[train], values), evaluate(expr, inputs.iloc[valid], values)
        if not (np.isfinite(pred_train).all() and np.isfinite(pred_valid).all()):
            raise FloatingPointError("predictions contain non-finite values")
    except (RuntimeError, ValueError, FloatingPointError, TypeError, ZeroDivisionError) as error:  # a failed fit is a result
        return {**result, "error": f"{type(error).__name__}: {error}"}
    relative = np.abs(pred_valid - y[valid]) / np.abs(y[valid])
    return {**result, "values": values, "fitted": substitute(expr, values),
            "train_nmse": nmse(y[train], pred_train), "val_nmse": nmse(y[valid], pred_valid),
            "val_max_rel_error": float(relative.max()), "val_acc_0.1": bool(relative.max() <= 0.1),
            "residual_correlations": diagnostics(y[valid] - pred_valid, inputs.iloc[valid])}


def verdict(result, accept, reject) -> str:
    if "error" in result:
        return "undetermined"
    return "support" if result["val_nmse"] <= accept else "refute" if result["val_nmse"] > reject else "undetermined"


def summary(result) -> str:
    if "error" in result:
        return f"fit failed: {result['error']}"
    top = ", ".join(f"{r['term']} ρ={r['spearman']:+.2f}" for r in result["residual_correlations"][:3])
    return (f"{result['target']} = {result['fitted']}\n"
            f"NMSE train {result['train_nmse']:.3g} / val {result['val_nmse']:.3g}, val max relative error {result['val_max_rel_error']:.3g}"
            f" (Acc0.1={result['val_acc_0.1']}), {result['n_constants']} constants\nresidual correlations: {top}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expr", required=True, help="expression with free constants C0, C1, ...")
    parser.add_argument("--init", default="", help="initial constant values, e.g. C0=1,C2=280; default 1.0")
    parser.add_argument("--split", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--unit", help="κ id to test; if given, write evidence.jsonl")
    parser.add_argument("--accept", type=float, default=1e-3)
    parser.add_argument("--reject", type=float, default=0.1)
    args = parser.parse_args(argv)
    started = time.monotonic()
    init = {k: float(v) for k, v in (item.split("=") for item in args.init.split(",") if item)}
    result = fit(args.expr, pd.read_parquet(args.data), args.target, init, args.split, args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "fit.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(summary(result))
    source = f"tool:fit@0.1(expr={args.expr},data={args.data})"
    units = []
    if "error" not in result:
        meta = {k: result[k] for k in ("values", "train_nmse", "val_nmse", "val_max_rel_error", "val_acc_0.1", "n_constants")}
        units.append({
            "id": f"fit/{args.target}", "form": "formula", "status": "inferred",
            "content": f"{args.target} = {result['fitted']}",
            "condition": lang.t(", ", "，").join(f"{c} ∈ [{lo:.4g}, {hi:.4g}]" for c, (lo, hi) in result["ranges"].items()),
            "provenance": source, "meta": {**meta, "residual_correlations": result["residual_correlations"][:5]},
        })
    if args.unit:
        note = summary(result).replace("\n", lang.t("; ", "；"))
        line = {"unit": args.unit, "verdict": verdict(result, args.accept, args.reject), "method": "tool", "source": source, "note": note}
        (out / "evidence.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    write_result(out, "fit", {k: v for k, v in vars(args).items()}, units, started)


if __name__ == "__main__":
    main()
