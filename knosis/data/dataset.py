"""Unified dataset object. Every loader returns a `Dataset`."""

from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# In a source checkout the default is the repo's data/; a pip-installed package has no repo, so it defaults to ~/.knosis/data.
REPO = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("KNOSIS_DATA_DIR") or
                (REPO / "data" if (REPO / "pyproject.toml").exists() else Path.home() / ".knosis/data"))
CARDS_DIR = Path(__file__).resolve().parent / "cards"


def data_dir(name: str) -> Path:
    return DATA_DIR / name


@dataclass
class Unit:
    """Raw units produced directly by a loader (currently only doc / chunk from the text entry). Knowledge-layer κ live in `knosis.knowledge`."""

    id: str
    content: str
    form: str = "prose"
    condition: str = ""
    provenance: str = ""
    status: str = "observed"
    meta: dict = field(default_factory=dict)


@dataclass
class Task:
    """One task. `input` is shown to the agent; `answer` is the GT (a value or file path), read only at evaluation."""

    id: str
    input: str
    answer: Any = None
    split: str = "test"
    kind: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Dataset:
    name: str
    scenario: str
    root: Path
    files: dict[str, Path] = field(default_factory=dict)  # named data files / directories, opened with `read(key)`
    schema: dict = field(default_factory=dict)            # structure: tables / relations / variables etc.
    tasks: list[Task] = field(default_factory=list)
    units: list[Unit] | None = None
    metrics: dict[str, str] = field(default_factory=dict)  # official metric name -> description

    def read(self, key: str | Path, **kw) -> Any:
        return read(self.files.get(key, key) if isinstance(key, str) else key, **kw)

    def describe(self) -> str:
        return card(self.name)

    def __repr__(self) -> str:
        return (
            f"<Dataset {self.name}/{self.scenario}: {len(self.tasks)} tasks, "
            f"files={list(self.files)}, units={None if self.units is None else len(self.units)}>"
        )


def card(name: str) -> str:
    return (CARDS_DIR / f"{name}.md").read_text(encoding="utf-8")


def read(path: str | Path, **kw) -> Any:
    """Open a file by its suffix; a directory returns all file paths under it."""
    path = Path(path)
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.is_file())
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(path, **kw)
    if suffix in (".csv", ".tsv"):
        import pandas as pd

        return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",", **kw)
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if suffix in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    if suffix in (".gpickle", ".pkl", ".pickle"):
        with path.open("rb") as fh:
            return pickle.load(fh)
    if suffix == ".graphml":
        import networkx as nx

        return nx.read_graphml(path, **kw)
    if suffix in (".h5", ".hdf5"):
        import h5py

        return h5py.File(path, "r", **kw)
    return path.read_text(encoding="utf-8", errors="replace")
