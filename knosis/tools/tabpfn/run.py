"""TabPFN 预测与 OOF；重依赖只在真实推断路径导入。"""

from __future__ import annotations

import argparse
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
            "provenance": f"tool:tabpfn@0.1(command={args.command},model={args.model}) ; {source}#row/{row['row_id']}",
            "meta": {"score": row[column], **row},
        })
    return units


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("predict", "oof"):
        p = sub.add_parser(command)
        p.add_argument("--train", required=True)
        if command == "predict":
            p.add_argument("--test", required=True)
        else:
            p.add_argument("--folds", type=int, default=5)
        p.add_argument("--target", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--problem-type", choices=["auto", "classification", "regression"], default="auto")
        p.add_argument("--model", default="auto")
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
