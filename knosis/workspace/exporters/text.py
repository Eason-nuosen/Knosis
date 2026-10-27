"""Text corpus: knowledge construction only, no downstream tasks; evaluation checks whether the knowledge layer locates back to the source text."""

from __future__ import annotations

from pathlib import Path

from . import place, register, render


@register("text")
def export(ds, ws: Path, write_data=True, **opts) -> dict:
    """Put the corpus into `data/` as is (including duplicate documents: duplicates are part of the data for the agent to judge)."""
    files = ds.schema["documents"] + [d for dups in ds.schema["duplicates"].values() for d in dups]
    if write_data:
        for doc in files:
            place(ds.root / doc, Path(ws) / "data" / doc)
    sizes = {doc: len((ds.root / doc).read_text(encoding="utf-8")) for doc in sorted(files)}
    listing = "\n".join(f"- `data/{doc}`：{n} 字符" for doc, n in list(sizes.items())[:50])
    if len(sizes) > 50:
        listing += f"\n- ……共 {len(sizes)} 个文件"
    return {
        "brief": render("text.md", name=ds.scenario, n_files=len(sizes), n_chars=sum(sizes.values()), listing=listing),
        "tasks": [], "dev": [], "holdout": [], "output": None, "modalities": ["text"],
    }
