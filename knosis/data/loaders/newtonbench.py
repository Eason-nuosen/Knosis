"""NewtonBench：主动做实验、反推物理定律。没有数据文件，任务由源码定义，GT 是 laws.py 里的函数。

    data/newtonbench/modules/<m*_域>/{laws.py, prompts.py, core.py}
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
    "symbolic_accuracy": "符号等价率（LLM 裁判，忽略常数）",
    "rmsle": "5000 个留出样本上的 RMSLE（越低越好）",
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
