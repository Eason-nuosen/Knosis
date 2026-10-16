import json
import subprocess
import sys

import pytest

import knosis.decision.newtonbench  # noqa: F401  注册打分器
import knosis.workspace.exporters.newtonbench  # noqa: F401  注册导出器
from knosis import data_dir
from knosis import workspace as w
from knosis.decision import evaluate
from knosis.knowledge import feedback, load_units, write_units

FILES = {
    "modules/common/evaluation.py": '''
import numpy as np
def extract_formula_from_function(f):
    return f.__doc__
def evaluate_law(llm_function_str, gt_law, test_data, symbolic_check=True, **kw):
    assert not symbolic_check
    scope = {}
    exec(llm_function_str, scope)
    x = test_data["x"]
    y, p = np.array([gt_law(v) for v in x]), np.array([scope["discovered_law"](v) for v in x])
    return {"rmsle": float(np.sqrt(np.mean((np.log1p(abs(p)) - np.log1p(abs(y))) ** 2))), "error": None}
''',
    "modules/m0_gravity/__init__.py": '''
from .core import run_experiment_for_module, evaluate_law
from .prompts import get_task_prompt, FUNCTION_SIGNATURE, PARAM_DESCRIPTION
''',
    "modules/m0_gravity/core.py": '''
import numpy as np
from modules.common.evaluation import evaluate_law as shared_evaluate_law
from .laws import get_ground_truth_law
def run_experiment_for_module(noise_level, difficulty="easy", system="vanilla_equation", law_version=None, **kw):
    return get_ground_truth_law(difficulty, law_version)[0](kw["x"]) * (1 + noise_level)
def evaluate_law(code, desc, difficulty="easy", law_version=None, judge_model_name="x", trial_info=None):
    law = get_ground_truth_law(difficulty, law_version)[0]
    return shared_evaluate_law(llm_function_str=code, gt_law=law, test_data={"x": np.random.uniform(1, 9, 50)},
                               parameter_mapping={"x": "x"}, param_description=desc, symbolic_check=True)
''',
    "modules/m0_gravity/laws.py": '''
K = {"easy": 2.0, "medium": 3.0, "hard": 5.0}
V = {"v0": 1, "v1": 2, "v2": 3}
def get_ground_truth_law(difficulty, version):
    k = K[difficulty] * V[version]
    def law(x):
        """SECRET_LAW"""
        return k * x ** 2
    return law, version
''',
    "modules/m0_gravity/prompts.py": '''
PARAM_DESCRIPTION = """- x: the input"""
FUNCTION_SIGNATURE = "def discovered_law(x):"
def get_task_prompt(system, is_code_assisted=False, noise_level=0.0):
    return f"apparatus for {system}, noise {noise_level}"
''',
}


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "newton"
    for name, text in FILES.items():
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_text(text)
    return base


def law(task_id, k=None):
    _, difficulty, version, _ = task_id.split("/")
    k = k or {"easy": 2.0, "medium": 3.0, "hard": 5.0}[difficulty] * {"v0": 1, "v1": 2, "v2": 3}[version]
    return f"def discovered_law(x):\n    return {k} * x ** 2"


def test_export_groups_and_hides_gt(root, tmp_path):
    ws = w.init("newtonbench", "m0_gravity", tmp_path / "ws", root=root)
    dev = load_units(ws / "tasks/dev.jsonl")
    assert len(dev) == 6
    assert "SECRET_LAW" not in (ws / "BRIEF.md").read_text() and "apparatus for complex_system" in (ws / "BRIEF.md").read_text()
    assert "newton" in (ws / "TOOLS.md").read_text()
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    assert len(tests) == 21
    pairs = lambda tasks: {(t["difficulty"], t["version"]) for t in tasks}  # noqa: E731
    assert not pairs(dev) & pairs(tests)
    assert not any(p.suffix == ".py" for p in ws.rglob("*") if ".git" not in p.parts)


def test_tool_score_and_feedback(root, tmp_path):
    ws = w.init("newtonbench", "m0_gravity", tmp_path / "ws", root=root, noise=0.5)
    task = load_units(ws / "tasks/dev.jsonl")[0]["id"]
    out = subprocess.run([sys.executable, "-m", "knosis", "tool", "run", "newton", "--", "--task", task,
                          "--inputs", '[{"x": 2}]', "--out", "stages/1_explore/newton/001"],
                         cwd=ws, capture_output=True, text=True, check=True).stdout
    k = float(law(task).split("return ")[1].split(" *")[0])
    assert json.loads(out) == [pytest.approx(k * 4 * 1.5)]
    assert json.loads((ws / "stages/1_explore/newton/001/experiments.json").read_text())[0]["input"] == {"x": 2}
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": task, "answer": law(task)}, {"id": load_units(ws / "tasks/dev.jsonl")[1]["id"], "answer": law(task, 99)}])
    record = feedback.submit(ws, path)
    assert [i["ok"] for i in record["items"]] == [True, False] and record["items"][0]["gold"] == "SECRET_LAW"
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": t["id"], "answer": law(t["id"])} for t in tests])
    assert not w.check(ws)
    assert evaluate(ws)["ok_rate"] == 1.0


def test_real_data(tmp_path):
    if not data_dir("newtonbench").exists():
        pytest.skip("no local data for newtonbench")
    ws = w.init("newtonbench", "m0_gravity", tmp_path / "ws")
    dev = load_units(ws / "tasks/dev.jsonl")
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": d["id"], "answer": "def discovered_law(mass1, mass2, distance):\n    return 6.674e-5 * mass1 * mass2 / distance ** 2"} for d in dev])
    record = feedback.submit(ws, path)
    assert len(record["items"]) == 6 and all(i["rmsle"] >= 0 for i in record["items"])
    from knosis.tools.newton.run import experiment

    assert experiment("m0_gravity/easy/v0/vanilla_equation", [{"mass1": 1, "mass2": 2, "distance": 3}], 0.0)[0] > 0
