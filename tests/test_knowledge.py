from copy import deepcopy

import pytest

from knosis.knowledge import check_units, load_units, write_units


def unit(**changes):
    return {"id": "u1", "content": "A fact", "form": "fact",
            "provenance": "tool:example@0.1()", "status": "observed", **changes}


def test_roundtrip(tmp_path):
    path = tmp_path / "kb/knowledge" / "units.jsonl"
    units = [unit(content="金融知识", meta={"score": 0.3})]
    write_units(path, units)
    assert load_units(path) == units
    write_units(path, [])
    assert load_units(path) == []


@pytest.mark.parametrize("key", ["id", "content", "form", "provenance", "status"])
def test_required(key):
    assert not check_units([unit()])
    bad = unit()
    del bad[key]
    assert check_units([bad])
    bad[key] = ""
    assert check_units([bad])


def test_duplicate_and_enums():
    assert check_units([unit(), unit()])
    assert not check_units([unit(), unit(id="u2")])
    assert check_units([unit(form="prose")])
    assert check_units([unit(status="guess")])
    for status in ("observed", "inferred", "verified", "retracted", "stale"):
        assert not check_units([unit(status=status)])


def test_sources(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.csv").touch()
    good = unit(provenance="tool:a@1() ; data/a.csv#row/0 ; data/a.csv#col/x")
    assert not check_units([good], root=tmp_path)
    assert check_units([unit(provenance="data/missing.csv#row/0")], root=tmp_path)
    assert check_units([unit(provenance="data/../outside")], root=tmp_path)
    assert not check_units([unit(provenance="data/a.csv#row/0")])


def test_derivation():
    child = unit(id="child", provenance="derived", derived_from=["u1"])
    assert not check_units([unit(), child])
    assert not check_units([child], known_ids={"u1"})
    assert check_units([child])
    assert check_units([unit(provenance="derived")])
    assert check_units([unit(provenance="derived ; tool:a@1()")])


def test_retraction_propagates_transitively():
    units = [unit(status="retracted"),
             unit(id="u2", provenance="derived", derived_from=["u1"], status="stale"),
             unit(id="u3", provenance="derived", derived_from=["u2"], status="stale")]
    assert not check_units(units)
    bad = deepcopy(units)
    bad[2]["status"] = "verified"
    assert check_units(bad)
    bad[1]["status"] = "observed"
    assert check_units(bad)
