"""Text entry: a directory of documents → doc / chunk units (+ triples etc. from an optional extractor).

The only entry that produces units at load time. A real extractor (e.g. AutoSchemaKG) is passed in as a function:
`extractor(doc_id, text) -> Iterable[Unit]`。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable, Iterable

from ..dataset import Dataset, Unit
from . import register

SUFFIXES = (".txt", ".md", ".markdown", ".rst", ".html", ".json", ".jsonl", ".csv", ".tsv")

METRICS = {
    "duplicate_rate": "collapsed duplicate documents / documents read",
    "provenance_resolvable": "fraction of units whose π resolves back to the source text",
}


def chunk(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    """Chunk by characters, breaking at paragraph boundaries where possible. Returns (start, end)."""
    spans, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        brk = text.rfind("\n\n", start, end)
        if end < len(text) and brk > start + size // 2:
            end = brk
        spans.append((start, end))
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return spans


@register("text")
def load(path: str | Path, chunk_chars: int = 2000, overlap: int = 200, dedup: bool = True,
         extractor: Callable[[str, str], Iterable[Unit]] | None = None,
         suffixes: Iterable[str] = SUFFIXES, root: str | Path | None = None) -> Dataset:
    """`path` is the corpus directory; relative paths are resolved against `root` (default: current directory)."""
    root = (Path(root or ".").expanduser() / Path(path).expanduser()).resolve()
    units, docs, seen, duplicates = [], [], {}, {}

    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in suffixes:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        doc_id = p.relative_to(root).as_posix()
        digest = hashlib.sha1(re.sub(r"\W+", " ", text.lower()).strip().encode()).hexdigest()
        if dedup and digest in seen:
            duplicates.setdefault(seen[digest], []).append(doc_id)
            continue
        seen[digest] = doc_id
        docs.append(doc_id)

        units.append(Unit(id=f"doc/{doc_id}", content=text, form="doc", provenance=f"text:{doc_id}"))
        for i, (s, e) in enumerate(chunk(text, chunk_chars, overlap)):
            units.append(Unit(id=f"chunk/{doc_id}#{i}", content=text[s:e], form="chunk", provenance=f"text:{doc_id}#{s}-{e}"))
        if extractor:
            units.extend(extractor(doc_id, text))

    schema = {"documents": docs, "duplicates": duplicates, "schema_free": True}
    return Dataset("text", root.name, root, files={"corpus": root}, schema=schema, units=units, metrics=METRICS)
