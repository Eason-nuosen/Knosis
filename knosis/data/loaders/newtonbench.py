"""NewtonBench: run experiments actively to infer physical laws. No data files; tasks are defined in source and GT is the functions in laws.py.

    data/newtonbench/modules/<m*_domain>/{laws.py, prompts.py, core.py}
"""

from __future__ import annotations

import re
from itertools import product
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

DOMAINS = (
    "m0_gravity", "m1_coulomb_force", "m2_magnetic_force", "m3_fourier_law",
    "m4_snell_law", "m5_radioactive_decay", "m6_underdamped_harmonic", "m7_malus_law",
    "m8_sound_speed", "m9_hooke_law", "m10_be_distribution", "m11_heat_transfer",
)
DIFFICULTIES = ("easy", "medium", "hard")
VERSIONS = ("v0", "v1", "v2")
COMPLEXITIES = ("vanilla_equation", "simple_system", "complex_system")

METRICS = {
    "symbolic_accuracy": "symbolic equivalence rate (LLM judge, constants ignored)",
    "rmsle": "RMSLE on 5000 held-out samples (lower is better)",
}


@register("newtonbench", scenarios=DOMAINS)
def load(scenario: str = "m0_gravity", root: str | Path | None = None) -> Dataset:
    base = Path(root or data_dir("newtonbench"))
    mdir = base / "modules" / scenario
    files = {p.stem: p for p in sorted(mdir.glob("*.py"))}

    prompts = files["prompts"].read_text() if "prompts" in files else ""
    m = re.search(r'PARAM_DESCRIPTION\s*=\s*"""(.*?)"""', prompts, re.DOTALL)
    params = m.group(1).strip() if m else ""

    tasks = [
        Task(
            id=f"{scenario}/{d}/{v}/{c}",
            input=params,
            answer=f"{files.get('laws', mdir / 'laws.py')}::_ground_truth_law_{d}_{v}",
            kind=c,
            meta={"difficulty": d, "version": v, "complexity": c},
        )
        for d, v, c in product(DIFFICULTIES, VERSIONS, COMPLEXITIES)
    ]
    return Dataset("newtonbench", scenario, mdir, files=files, schema={"params": params}, tasks=tasks, metrics=METRICS)


def upstream(scenario: str, root: str | Path | None = None):
    """Import the upstream module `modules.<scenario>` (GT law and simulator); for the environment side only (experiment tool, scorer).

    Upstream evaluation imports openai at import time; Knosis does no LLM symbolic judging, so it is replaced with a stub and symbolic checks are disabled.
    """
    import importlib
    import sys
    import types

    base = str(Path(root or data_dir("newtonbench")).resolve())
    loaded = sys.modules.get("modules")
    if loaded and str(Path(list(loaded.__path__)[0]).parent) != base:  # upstream package names are the generic modules / utils; clear them before switching roots
        for name in [n for n in sys.modules if n.split(".")[0] in ("modules", "utils")]:
            del sys.modules[name]
    if sys.path[:1] != [base]:
        sys.path.insert(0, base)
    stub = types.ModuleType("utils.call_llm_api")
    stub.call_llm_api = None
    sys.modules.setdefault("utils.call_llm_api", stub)
    module = importlib.import_module(f"modules.{scenario}")
    core = importlib.import_module(f"modules.{scenario}.core")
    shared = importlib.import_module("modules.common.evaluation").evaluate_law

    def without_judge(*args, **kw):
        return shared(*args, **{**kw, "symbolic_check": False})

    core.shared_evaluate_law = without_judge
    return module
