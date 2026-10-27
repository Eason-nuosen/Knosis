"""Exporters: turn a dataset into the agent-visible part of a workspace (data + BRIEF + tasks); GT stays in the raw data directory.

To add workspace support for a dataset: write `<name>.py` here, decorate
`export(ds, ws, write_data=True, **opts) -> dict` with `@register("<name>")`, and add it to the import list below. Returns:

    brief        BRIEF.md body
    tasks        test tasks (no answers), each with at least "id"; written to tasks/tasks.jsonl only at decide
    dev          dev tasks (no answers, disjoint from test), written to tasks/dev.jsonl at init for knowledge-layer feedback; may be empty
    holdout      task ids shown as examples in BRIEF
    output       decide deliverable file name: predictions.jsonl (one {id, answer} per line) or predictions.csv (row_id, prediction, ...);
                 None when there is no downstream prediction
    modalities   used to pick tools for TOOLS.md, e.g. ["graph"], ["table"], ["tables"]

The same `opts` must yield the same split (`write_data=False` regenerates tasks at decide).
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path
from string import Template
from typing import Callable

EXPORTERS: dict[str, Callable] = {}


def register(name: str):
    def deco(fn):
        EXPORTERS[name] = fn
        return fn

    return deco


def place(src, dst) -> None:
    """Put raw files into the workspace: hard link on the same filesystem (no extra space), otherwise copy.
    No symlinks: they expose the raw directory's location, and GT is often right next to it."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:  # cross-filesystem
        shutil.copy2(src, dst)


def render(template, **values):
    from .. import templates  # imported here: knosis.workspace imports this module first

    return Template((templates() / "briefs" / template).read_text(encoding="utf-8")).substitute(values)


def split(items, dev, limit=None, seed=0):
    """Shuffle with `seed` and split into dev and test; `limit` caps the test count. Output keeps the original order."""
    order = list(range(len(items)))
    random.Random(seed).shuffle(order)
    dev_idx, test_idx = set(order[:dev]), order[dev:]
    test_idx = set(test_idx[:limit] if limit is not None else test_idx)
    return [x for i, x in enumerate(items) if i in dev_idx], [x for i, x in enumerate(items) if i in test_idx]



from . import (  # noqa: E402,F401
    alphabench, bibench, burr, kramabench, llm_srbench, newtonbench, ngdbench, relbench, spreadsheetbench, tabarena, text,
    traces, whoandwhen,
)
