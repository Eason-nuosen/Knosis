"""TabPFN 预测、OOF 与特征变体交叉验证；重依赖只在真实推断路径导入。"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from knosis.tools import write_result


def problem_type(target, requested):
    if requested != "auto":
        return requested
    return "regression" if pd.api.types.is_numeric_dtype(target) else "classification"


def fit_model(train, target, features, kind, args):
    from tabpfn import TabPFNClassifier, TabPFNRegressor

    selected = train.sample(n=min(len(train), args.max_rows), random_state=args.seed)
    cls = TabPFNClassifier if kind == "classification" else TabPFNRegressor
    model = cls(device=args.device, model_path=args.model, random_state=args.seed)
    model.fit(selected[features], selected[target])
    return model, selected["row_id"].tolist()


def predict_rows(model, features, row_ids, kind):
    result = pd.DataFrame({"row_id": list(row_ids), "prediction": model.predict(features)})
    if kind == "classification":
        probabilities = np.asarray(model.predict_proba(features))
        for i, label in enumerate(model.classes_):
            result[f"probability_{label}"] = probabilities[:, i]
        result["uncertainty"] = -(probabilities * np.log(np.clip(probabilities, 1e-12, 1))).sum(axis=1)
    else:
        lower, upper = model.predict(features, output_type="quantiles", quantiles=[0.1, 0.9])
        result["lower"] = lower
        result["upper"] = upper
        result["uncertainty"] = np.asarray(upper) - np.asarray(lower)
    return result


def oof(train, target, features, kind, args):
    from sklearn.model_selection import KFold, StratifiedKFold

    splitter = (StratifiedKFold if kind == "classification" else KFold)(
        n_splits=args.folds, shuffle=True, random_state=args.seed,
    )
    results, sampled = [], []
    for fold, (fit_ids, valid_ids) in enumerate(splitter.split(train, train[target])):
        valid = train.iloc[valid_ids]
        model, ids = fit_model(train.iloc[fit_ids], target, features, kind, args)
        sampled.append({"fold": fold, "fit_row_ids": ids})
        result = predict_rows(model, valid[features], valid["row_id"], kind)
        result["fold"] = fold
        result["truth"] = valid[target].to_numpy()
        if kind == "classification":
            result["true_probability"] = [
                result.iloc[i].get(f"probability_{label}", 0.0) for i, label in enumerate(valid[target])
            ]
            result["suspicion"] = 1 - result["true_probability"]
        else:
            result["residual"] = result["truth"] - result["prediction"]
            result["suspicion"] = result["residual"].abs()
        results.append(result)
    return pd.concat(results, ignore_index=True), sampled


def findings(result, args):
    column = "suspicion" if args.command == "oof" else "uncertainty"
    source = args.train if args.command == "oof" else args.test
    units = []
    for i, row in enumerate(result.sort_values(column, ascending=False).head(args.topk).to_dict("records")):
        units.append({
            "id": f"tabpfn/{args.command}/{i}", "form": "finding", "status": "inferred",
            "content": f"row {row['row_id']}: {'可疑标签' if args.command == 'oof' else '预测不确定性较高'}",
            "condition": "模型注解，需在训练数据上验证；不使用测试 GT",
            "provenance": f"tool:tabpfn@0.2(command={args.command},model={args.model}) ; {source}#row/{row['row_id']}",
            "meta": {"score": row[column], **row},
        })
    return units


# ---------------------------------------------------------------- cv：特征变体对比


def parse_spec(spec):
    """`drop:a,b;add:name=expr;subset:query` → [(op, arg)]；空串即基线特征。"""
    return [tuple(part.split(":", 1)) for part in spec.split(";") if part.strip()]


def build_variant(train, features, spec):
    """返回 (编码后的全量帧, 特征, 行掩码)。新列在全部行上算，类别编码在子集前做，各折一致。"""
    frame, features, mask = train.copy(), list(features), np.ones(len(train), dtype=bool)
    for op, arg in parse_spec(spec):
        if op == "drop":
            features = [f for f in features if f not in arg.split(",")]
        elif op == "add":
            name, expr = arg.split("=", 1)
            values = frame.eval(expr)
            frame[name] = values.astype(int) if values.dtype == bool else values
            features.append(name)
        elif op == "subset":
            mask &= frame.eval(arg).to_numpy(dtype=bool)
        else:
            raise ValueError(f"未知变体操作：{op}")
    for f in features:
        if pd.api.types.is_bool_dtype(frame[f]):
            frame[f] = frame[f].astype(int)
        elif not pd.api.types.is_numeric_dtype(frame[f]):
            frame[f] = frame[f].astype("category").cat.codes
    return frame, features, mask


def fold_scores(truth, pred, kind, classes):
    """回归返回 (RMSE,)，分类返回 (log loss, accuracy)；pred 为预测值或按 classes 对齐的概率。"""
    if kind == "regression":
        return (float(np.sqrt(np.mean((np.asarray(truth) - pred) ** 2))),)
    from sklearn.metrics import log_loss

    return (float(log_loss(truth, pred, labels=classes)), float(np.mean(classes[pred.argmax(axis=1)] == np.asarray(truth))))


def cv_predict(frame, target, features, mask, folds, kind, classes, args):
    """同一折划分下，在 mask 行上做 OOF；返回与全表对齐的预测（分类为按 classes 对齐的概率）。"""
    pred = np.zeros((len(frame), len(classes)) if kind == "classification" else len(frame))
    for k in range(args.folds):
        fit_rows, valid_rows = (folds != k) & mask, (folds == k) & mask
        model, _ = fit_model(frame[fit_rows], target, features, kind, args)
        if kind == "classification":
            proba = np.asarray(model.predict_proba(frame.loc[valid_rows, features]))
            pred[np.ix_(valid_rows, np.searchsorted(classes, model.classes_))] = proba
        else:
            pred[valid_rows] = model.predict(frame.loc[valid_rows, features])
    return pred


def compare(name, spec, frame, features, mask, folds, pred, base_pred, kind, classes, args):
    """各折在同一批行上比较变体与基线；Δ = 变体 − 基线，配对标准差取折间 Δ 的样本标准差。"""
    truth = frame[args.target].to_numpy()
    rows = []
    for k in range(args.folds):
        idx = (folds == k) & mask
        rows.append((fold_scores(truth[idx], pred[idx], kind, classes), fold_scores(truth[idx], base_pred[idx], kind, classes)))
    own = np.array([r[0] for r in rows])
    base = np.array([r[1] for r in rows])
    deltas = own[:, 0] - base[:, 0]
    record = {"variant": name, "spec": spec, "n_rows": int(mask.sum()), "n_features": len(features),
              "metric": "rmse" if kind == "regression" else "log_loss",
              "mean": own[:, 0].mean(), "std": own[:, 0].std(ddof=1), "base_mean": base[:, 0].mean(),
              "delta": deltas.mean(), "delta_std": deltas.std(ddof=1), "folds": args.folds}
    if kind == "classification":
        record.update(accuracy=own[:, 1].mean(), base_accuracy=base[:, 1].mean())
    return record


def verdict(record):
    """指标越低越好：改进超过 1 个配对标准差为 support，变差超过为 refute。"""
    if -record["delta"] > record["delta_std"]:
        return "support"
    if record["delta"] > record["delta_std"]:
        return "refute"
    return "undetermined"


def cv_units(records, args):
    units, evidence = [], []
    targets = dict(u.split("=", 1) for u in args.unit)
    for r in records[1:]:
        metric = r["metric"].upper() if r["metric"] == "rmse" else "log loss"
        scope = "" if r["n_rows"] == records[0]["n_rows"] else f"在 {r['n_rows']} 行子集上"
        note = (f"{metric} {r['base_mean']:.4g} → {r['mean']:.4g}，Δ={r['delta']:+.4g}±{r['delta_std']:.4g}"
                f"（{args.folds} 折配对）" + (f"；accuracy {r['base_accuracy']:.3f} → {r['accuracy']:.3f}" if "accuracy" in r else ""))
        source = f"tool:tabpfn@0.2(cv,variant={r['variant']},metric={r['metric']},folds={args.folds},seed={args.seed})"
        units.append({
            "id": f"tabpfn/cv/{r['variant']}", "form": "finding", "status": "inferred",
            "content": f"变体 {r['variant']}（{r['spec']}）{scope}使 {metric} 从 {r['base_mean']:.4g} 变为 {r['mean']:.4g}"
                       f"（Δ={r['delta']:+.4g}±{r['delta_std']:.4g}，{args.folds} 折）",
            "condition": f"TabPFN 交叉验证，目标 {args.target}，基线在同一批行上评估；模型注解，需在数据上验证",
            "provenance": f"{source} ; {args.train}",
            "meta": r,
        })
        if r["variant"] in targets:
            evidence.append({"unit": targets[r["variant"]], "verdict": verdict(r), "method": "tool",
                             "source": source, "note": note})
    return units, evidence


def cv(train, kind, features, args, out, started):
    from sklearn.model_selection import KFold, StratifiedKFold

    variants = {"base": "", **dict(v.split("=", 1) for v in args.variant)}
    built = {name: build_variant(train, features, spec) for name, spec in variants.items()}
    params = {**vars(args), "problem_type": kind, "n_train": len(train), "features": features}
    if args.prepare_only:
        pd.DataFrame([{"variant": name, "spec": spec, "n_rows": int(built[name][2].sum()), "n_features": len(built[name][1]),
                       "features": ",".join(built[name][1])} for name, spec in variants.items()]).to_csv(out / "cv_plan.csv", index=False)
        return write_result(out, "tabpfn", params, [], started)
    splitter = (StratifiedKFold if kind == "classification" else KFold)(n_splits=args.folds, shuffle=True, random_state=args.seed)
    folds = np.empty(len(train), dtype=int)
    for k, (_, valid) in enumerate(splitter.split(train, train[args.target])):
        folds[valid] = k
    classes = np.sort(train[args.target].unique()) if kind == "classification" else None
    preds = {}
    for name, (frame, feats, mask) in built.items():
        preds[name] = cv_predict(frame, args.target, feats, mask, folds, kind, classes, args)
    records = [compare(name, spec, *built[name], folds, preds[name], preds["base"], kind, classes, args)
               for name, spec in variants.items()]
    table = pd.DataFrame(records)
    table.to_csv(out / "cv.csv", index=False)
    print(table.drop(columns=["spec"]).to_string(index=False))
    units, evidence = cv_units(records, args)
    if args.unit:
        (out / "evidence.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in evidence), encoding="utf-8")
    write_result(out, "tabpfn", params, units, started)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("predict", "oof", "cv"):
        p = sub.add_parser(command)
        p.add_argument("--train", required=True)
        if command == "predict":
            p.add_argument("--test", required=True)
        else:
            p.add_argument("--folds", type=int, default=5)
        if command == "cv":
            p.add_argument("--variant", action="append", default=[], help="NAME=SPEC，可重复；base 为基线")
            p.add_argument("--unit", action="append", default=[], help="VARIANT=UNITID，可重复；写 evidence.jsonl")
        p.add_argument("--target", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--problem-type", choices=["auto", "classification", "regression"], default="auto")
        p.add_argument("--model", default=os.environ.get("KNOSIS_TABPFN_MODEL", "auto"))
        p.add_argument("--device", default="auto")
        p.add_argument("--max-rows", type=int, default=10000)
        p.add_argument("--max-features", type=int, default=500)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--topk", type=int, default=50)
        p.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    started = time.monotonic()
    train = pd.read_parquet(args.train)
    test = pd.read_parquet(args.test) if args.command == "predict" else None
    kind = problem_type(train[args.target], args.problem_type)
    features = [c for c in train if c not in {"row_id", args.target}]
    if len(features) > args.max_features:
        indices = sorted(np.random.default_rng(args.seed).choice(len(features), args.max_features, replace=False))
        features = [features[i] for i in indices]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "cv":
        if "row_id" not in train:
            train["row_id"] = range(len(train))
        return cv(train, kind, features, args, out, started)
    params = {**vars(args), "problem_type": kind, "n_train": len(train), "features": features}
    if args.prepare_only:
        selected = train.sample(n=min(len(train), args.max_rows), random_state=args.seed)
        params["fit_row_ids"] = selected["row_id"].tolist()
        pd.DataFrame({"feature": features, "dtype": [str(train[c].dtype) for c in features],
                      "missing": [int(train[c].isna().sum()) for c in features]}).to_parquet(
            out / "input_summary.parquet", index=False,
        )
        units = []
    else:
        if args.command == "predict":
            model, params["fit_row_ids"] = fit_model(train, args.target, features, kind, args)
            result = predict_rows(model, test[features], test["row_id"], kind)
            filename = "predictions.parquet"
        else:
            result, params["folds_sampled"] = oof(train, args.target, features, kind, args)
            filename = "oof_predictions.parquet"
        result.to_parquet(out / filename, index=False)
        units = findings(result, args)
    if test is not None:
        params["n_test"] = len(test)
    write_result(out, "tabpfn", params, units, started)


if __name__ == "__main__":
    main()
