"""Language of agent-facing text (prompts, briefs, data cards): English by default, Chinese with `KNOSIS_LANG=zh`."""

from __future__ import annotations

import os
from pathlib import Path


def zh() -> bool:
    return os.environ.get("KNOSIS_LANG", "en").lower().startswith("zh")


def t(en: str, cn: str) -> str:
    """Pick the English or Chinese version of a prompt fragment."""
    return cn if zh() else en


def localized(directory: Path) -> Path:
    """`<dir>` holds the English files, `<dir>_cn` the Chinese ones."""
    return directory.with_name(directory.name + "_cn") if zh() else directory
