"""English is the default language of agent-facing text; Chinese (KNOSIS_LANG=zh) mirrors it file by file."""

import re
from pathlib import Path
from string import Template

import pytest

from knosis import describe, list_datasets
from knosis import workspace as w
from knosis.knowledge import consolidate, layout, view, write_units
from knosis.tools import card, list_tools

from test_consolidate import unit
from test_driver import ws  # noqa: F401

CJK = re.compile(r"[一-龥]")
PKG = Path(w.__file__).resolve().parents[1]


def pairs(en, cn, pattern="**/*.md"):
    files = sorted(p.relative_to(en) for p in en.glob(pattern))
    assert files == sorted(p.relative_to(cn) for p in cn.glob(pattern))
    return [(en / f, cn / f) for f in files]


@pytest.mark.parametrize("en, cn", [(PKG / "workspace/templates", PKG / "workspace/templates_cn"),
                                    (PKG / "data/cards", PKG / "data/cards_cn")])
def test_every_file_has_both_languages_with_the_same_placeholders(en, cn):
    for a, b in pairs(en, cn):
        text = a.read_text(encoding="utf-8")
        assert not CJK.search(text), a
        assert Template(text).get_identifiers() == Template(b.read_text(encoding="utf-8")).get_identifiers(), a


def test_english_by_default(ws):  # noqa: F811
    assert not CJK.search(w.next_prompt(ws))
    assert not CJK.search((ws / "BRIEF.md").read_text() + (ws / "AGENTS.md").read_text())
    write_units(layout(ws).units, [unit("a", content="orders.id is unique"), unit("b", content="orders.id has no nulls")])
    for step in ("dedup", "conflict", "organize", "structure", "compact"):
        assert not CJK.search(consolidate.prompt(ws, step)), step
    assert not CJK.search(consolidate.prompt(ws, "compact", topic="orders"))
    assert not CJK.search(view.prompt(ws, request="only orders"))
    for name in list_datasets():
        assert not CJK.search(describe(name)), name
    for tool in list_tools():
        assert not CJK.search(card(tool["name"])), tool["name"]


def test_chinese_on_request(ws, monkeypatch):  # noqa: F811
    monkeypatch.setenv("KNOSIS_LANG", "zh")
    assert CJK.search(w.next_prompt(ws)) and CJK.search(describe("traces")) and CJK.search(card("sql"))
