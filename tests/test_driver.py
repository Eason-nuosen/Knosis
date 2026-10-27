import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from knosis import workspace as w
from knosis.workspace import driver
from knosis.knowledge import write_units


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "raw/toy"
    root.mkdir(parents=True)
    pd.DataFrame({"x": range(4), "y": ["a", "b"] * 2}).to_parquet(root / "data.parquet")
    pd.DataFrame({"repeat": [0] * 4, "fold": [0] * 4, "row": range(4),
                  "split": ["train"] * 3 + ["test"]}).to_parquet(root / "splits.parquet")
    (root / "meta.json").write_text(json.dumps({
        "target": "y", "problem_type": "binary", "categorical": [], "n_rows": 4, "n_features": 1,
    }))
    return w.init("tabarena", "toy", tmp_path / "ws", root=root.parent)


def test_driver_retry_and_rounds(ws, monkeypatch):
    original = subprocess.run
    attempts, prompts = [], []

    def agent(command, **kwargs):
        if command[0] not in {"codex", "claude"}:
            return original(command, **kwargs)
        assert kwargs["env"]["KNOSIS_DEPTH"] == "1"
        state = w.status(ws)
        stage = state["stage"]
        attempts.append(stage)
        prompts.append(command)
        if stage == "explore" and attempts.count(stage) > 1:
            (ws / "stages/1_explore/notes.md").write_text("Inspected data.")
        elif stage == "extract":
            write_units(ws / "kb/knowledge/units.jsonl", [{
                "id": "schema", "content": "One feature", "form": "schema",
                "provenance": "data/train.parquet#col/x", "status": "observed",
            }])
        elif stage == "refine":
            (w.stage_dir(ws, state) / "changelog.md").write_text("Revalidated.")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(w.subprocess, "run", agent)
    w.run(ws)
    assert attempts == ["explore", "explore", "extract"]
    assert "验收未通过" in prompts[1][-1]
    assert w.status(ws)["stage"] == "refine"
    assert (ws / "stages/1_explore/agent.log").exists()
    w.run(ws, agent="claude", stages=["refine"], rounds=2)
    assert w.status(ws)["stage"] == "decide" and w.status(ws)["round"] == 3
    assert (ws / "stages/3_refine/round_2/kb/knowledge/units.jsonl").exists()
    records = [json.loads(line) for line in (ws / ".knosis/runs.jsonl").read_text().splitlines()]
    assert records[0]["issues"] and not records[1]["issues"]
    assert records[-1]["agent"] == "claude"


def test_driver_stops_after_two_failures(ws, monkeypatch):
    original = subprocess.run
    calls = []

    def agent(command, **kwargs):
        if command[0] != "codex":
            return original(command, **kwargs)
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(w.subprocess, "run", agent)
    with pytest.raises(RuntimeError, match="notes.md"):
        w.run(ws, stages=["explore"])
    assert len(calls) == 2 and w.status(ws)["stage"] == "explore"


def test_driver_nested_block(ws, monkeypatch):
    monkeypatch.setenv("KNOSIS_DEPTH", "1")
    with pytest.raises(RuntimeError, match="nested"):
        w.run(ws)


def test_driver_real_subprocess(ws, tmp_path, monkeypatch):
    script = tmp_path / "fake_agent.py"
    script.write_text(
        "import os\nfrom pathlib import Path\n"
        "assert os.environ['KNOSIS_DEPTH'] == '1'\n"
        "Path('stages/1_explore/notes.md').write_text('Inspected data.')\n"
        "print('done')\n",
    )
    monkeypatch.setattr(driver, "agent_command", lambda agent, path, prompt, model, effort: [sys.executable, str(script)])
    w.run(ws, stages=["explore"])
    assert w.status(ws)["stage"] == "extract"
    assert "done" in (ws / "stages/1_explore/agent.log").read_text()


def test_driver_cannot_skip_validation(ws, monkeypatch):
    original = subprocess.run

    def agent(command, **kwargs):
        if command[0] != "codex":
            return original(command, **kwargs)
        w.goto(ws, "decide")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(w.subprocess, "run", agent)
    with pytest.raises(RuntimeError, match="notes.md"):
        w.run(ws, stages=["explore"])
    assert w.status(ws)["stage"] == "explore"


def test_offline_trial(ws, tmp_path, monkeypatch):
    # examples/ 不在安装包里：从仓库根目录导入（CI 用安装好的包跑测试）。
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from examples.offline_trial import trial

    out = trial("toy", tmp_path / "trial", w.status(ws)["options"]["root"])
    assert w.status(out)["completed"]
    assert (out / "stages/2_extract/kb/knowledge/units.jsonl").exists()
    assert (out / "stages/3_refine/round_1/kb/knowledge/units.jsonl").exists()
    assert pd.read_csv(out / "stages/4_decide/predictions.csv").row_id.tolist() == [3]
