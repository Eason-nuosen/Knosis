"""Loader registry. To add a dataset: write a module in this directory, decorate its `load` with `@register`, and add a `cards/<name>.md`."""

from __future__ import annotations

from typing import Callable, Iterable

LOADERS: dict[str, Callable] = {}


def register(name: str, scenarios: Iterable[str] | Callable[[], Iterable[str]] = ()):
    def deco(fn):
        fn.scenarios = scenarios
        LOADERS[name] = fn
        return fn

    return deco


from . import (  # noqa: E402,F401
    alphabench, bibench, burr, kramabench, llm_srbench, newtonbench, ngdbench, relbench, spreadsheetbench, tabarena, text,
    traces, whoandwhen,
)
