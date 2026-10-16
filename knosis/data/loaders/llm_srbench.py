"""LLM-SRBench：抗记忆的符号回归。parquet 里是题目元数据与真值表达式，数值在 HDF5。

    data/llm-srbench/{data/lsr_*.parquet, lsr_bench_data.hdf5}
"""

from __future__ import annotations

from pathlib import Path

from ..dataset import Dataset, Task, data_dir, read
from . import register

SPLITS = ("lsr_transform", "lsr_synth_chem_react", "lsr_synth_bio_pop_growth", "lsr_synth_phys_osc", "lsr_synth_matsci")

METRICS = {
    "symbolic_accuracy": "符号等价率（GPT-4o 裁判，先剥掉常数）",
    "nmse": "域内测试集 NMSE（越低越好）",
    "acc_tau": "最大相对误差 ≤ τ 的题目比例",
    "ood_nmse": "域外 NMSE，只有 LSR-Synth 有",
}


@register("llm-srbench", scenarios=SPLITS)
def load(scenario: str = "lsr_transform", root: str | Path | None = None) -> Dataset:
    base = Path(root or data_dir("llm-srbench"))
    parquet = next(base.rglob(f"{scenario}*.parquet"))
    files = {"problems": parquet, "hdf5": next(base.rglob("lsr_bench_data.hdf5"), base / "lsr_bench_data.hdf5")}
    group = "lsr_transform" if scenario == "lsr_transform" else f"lsr_synth/{scenario.removeprefix('lsr_synth_')}"

    tasks = []
    for row in read(parquet).to_dict("records"):
        row = {k: list(v) if hasattr(v, "tolist") else v for k, v in row.items()}
        tasks.append(Task(
            id=f"{scenario}/{row['name']}",
            input="\n".join(f"{s}: {d}" for s, d in zip(row["symbols"], row["symbol_descs"])),
            answer=row["expression"],
            kind="symbolic_regression",
            meta={**{k: v for k, v in row.items() if k != "expression"}, "hdf5_group": f"/{group}/{row['name']}"},
        ))
    return Dataset("llm-srbench", scenario, base, files=files, tasks=tasks, metrics=METRICS)
