import json

import numpy as np
import pandas as pd
import pytest

from knosis import tools
from knosis.knowledge import check_units, load_units
from knosis.tools.fit import run as fit


@pytest.fixture
def data(tmp_path):
    rng = np.random.default_rng(0)
    x, t = rng.uniform(0, 1, 200), rng.uniform(270, 300, 200)
    path = tmp_path / "train.parquet"
    pd.DataFrame({"y": 2.5 * x**2 + 0.3 * (t - 280) * np.exp(-x), "x": x, "t": t}).to_parquet(path)
    return path


def run(data, tmp_path, expr, *extra):
    out = tmp_path / "out"
    fit.main(["--data", str(data), "--target", "y", "--expr", expr, "--out", str(out), "--unit", "k-1", *extra])
    return out, json.loads((out / "fit.json").read_text()), load_units(out / "evidence.jsonl")


def test_recovers_law(data, tmp_path, capsys):
    out, result, evidence = run(data, tmp_path, "C0*x**2 + C1*(t-C2)*exp(-x)", "--init", "C2=250")
    assert result["values"]["C2"] == pytest.approx(280, rel=1e-6) and result["val_nmse"] < 1e-10
    assert result["val_acc_0.1"] is True and result["n_constants"] == 3 and result["n_valid"] == 40
    units = load_units(out / "units.jsonl")
    assert not check_units(units) and units[0]["form"] == "formula" and "280" in units[0]["content"]
    assert units[0]["provenance"].startswith("tool:fit@0.1(expr=") and "x ∈ [" in units[0]["condition"]
    assert evidence == [{**evidence[0], "unit": "k-1", "verdict": "support", "method": "tool"}]
    assert "NMSE" in capsys.readouterr().out


def test_missing_term_refuted_with_hint(data, tmp_path):
    _, result, evidence = run(data, tmp_path, "C0*x + C1")
    assert result["val_nmse"] > 0.1 and evidence[0]["verdict"] == "refute"
    assert result["residual_correlations"][0]["term"] in {"t", "t^2"}
    assert {"pearson", "spearman"} <= set(result["residual_correlations"][0])


def test_thresholds_and_failure(data, tmp_path):
    _, _, evidence = run(data, tmp_path, "C0*x + C1", "--reject", "10")
    assert evidence[0]["verdict"] == "undetermined"
    out, result, evidence = run(data, tmp_path, "C0*log(C1-t)")
    assert "error" in result and evidence[0]["verdict"] == "undetermined"
    assert load_units(out / "units.jsonl") == []


def test_subprocess_without_unit(data, tmp_path):
    out = tmp_path / "out"
    assert tools.run_tool("fit", ["--data", str(data), "--target", "y", "--expr", "C0*x**2 + C1*t", "--out", str(out)]) == 0
    assert not (out / "evidence.jsonl").exists()
    assert json.loads((out / "run.json").read_text())["tool"] == "fit"
