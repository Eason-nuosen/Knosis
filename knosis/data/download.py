"""Fetch a benchmark from upstream into data/<name>/. HF datasets use snapshot_download, OpenML suites are exported to parquet, the rest are git cloned."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .dataset import data_dir

SOURCES = {
    "ngdbench": ("hf", "FeifeiCS/NGDBench"),
    "relbench": ("hf", "stanford-star/relbench-v1"),
    "llm-srbench": ("hf", "nnheui/llm-srbench"),  # gated: accept the terms on HF and run `hf auth login` first
    "whoandwhen": ("hf", "Kevin355/Who_and_When@59b9fcba1aaed7bbf206b5f4d3c68b8face2f49c"),  # pinned revision, see the data card
    "tabarena": ("openml", 457),
    "burr": ("git", "https://github.com/HPI-Information-Systems/burr"),
    "newtonbench": ("git", "https://github.com/HKUST-KnowComp/NewtonBench"),
    "alphabench": ("git", "https://github.com/CityU-MLO/AlphaBench"),
    "kramabench": ("git", "https://github.com/mitdbg/KramaBench"),
    "bibench": ("git-lfs", "https://github.com/Hu-Chuxuan/bi-agent"),  # tables and GT are LFS files, about 4 GB
}


def download(name: str, include: list[str] | None = None) -> Path:
    """`include`: HF allow_patterns (e.g. ["rel-f1/*"]), or dataset names within an OpenML suite."""
    if name not in SOURCES:
        raise ValueError(f"{name} must be obtained manually, see `knosis describe {name}`")
    kind, src = SOURCES[name]
    dest = data_dir(name)
    if kind == "hf":
        from huggingface_hub import snapshot_download

        repo, _, revision = src.partition("@")
        snapshot_download(repo, repo_type="dataset", revision=revision or None, local_dir=dest, allow_patterns=include)
    elif kind == "openml":
        export_openml_suite(src, dest, include)
    else:
        subprocess.run(["git", "clone", "--depth", "1", src, str(dest)], check=True)
        if kind == "git-lfs":  # requires git-lfs (conda install -c conda-forge git-lfs)
            subprocess.run(["git", "-C", str(dest), "lfs", "pull"], check=True)
    return dest


def export_openml_suite(suite_id: int, dest: Path, include: list[str] | None = None) -> None:
    """Export each task as <dataset name>/{data.parquet, splits.parquet, meta.json}."""
    import openml
    import pandas as pd

    openml.config.set_root_cache_directory(str(dest / ".openml"))
    listing = openml.tasks.list_tasks(task_id=openml.study.get_suite(suite_id).tasks, output_format="dataframe")
    for task_id, name in zip(listing["tid"], listing["name"]):
        if include and name not in include:
            continue
        task = openml.tasks.get_task(int(task_id), download_splits=True)
        ds = task.get_dataset()
        out = dest / ds.name
        out.mkdir(parents=True, exist_ok=True)

        df, _, categorical, columns = ds.get_data(dataset_format="dataframe")
        df.to_parquet(out / "data.parquet")

        repeats, folds, _ = task.get_split_dimensions()
        splits = []
        for r in range(repeats):
            for f in range(folds):
                for split, rows in zip(("train", "test"), task.get_train_test_split_indices(fold=f, repeat=r)):
                    splits.append(pd.DataFrame({"repeat": r, "fold": f, "row": rows, "split": split}))
        pd.concat(splits).to_parquet(out / "splits.parquet")

        labels = getattr(task, "class_labels", None)
        problem = "regression" if not labels else "binary" if len(labels) == 2 else "multiclass"
        (out / "meta.json").write_text(json.dumps({
            "task_id": task_id,
            "dataset_id": ds.dataset_id,
            "target": task.target_name,
            "problem_type": problem,
            "class_labels": labels,
            "categorical": [c for c, is_cat in zip(columns, categorical) if is_cat and c != task.target_name],
            "n_rows": len(df),
            "n_features": len(df.columns) - 1,
            "repeats": repeats,
            "folds": folds,
            "description": ds.description or "",
            "url": f"https://www.openml.org/t/{task_id}",
        }, ensure_ascii=False, indent=1))
        print(f"  {ds.name}: {len(df)} rows, {repeats}x{folds} splits")
