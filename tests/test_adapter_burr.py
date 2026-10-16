import copy
import json

import pytest

from knosis import data_dir, load_dataset
from knosis import workspace as w
from knosis.decision import burr as scorer
from knosis.decision import evaluate
from knosis.knowledge import feedback, load_units, write_units
from knosis.workspace.exporters import burr  # noqa: F401  注册导出器


def mapping(table):
    return {
        "classes": [{"id": f"{table}/@@{table}.id@@", "class": table.title(), "name": table.title()},
                    {"id": "city/@@addr.city@@", "class": "City"}],
        "object_properties": [{"property": "livesIn", "belongsToClassMap": table.title(), "refersToClassMap": "City",
                               "join": [f"{table}.addr_id = addr.id"]}],
        "data_properties": [{"property": "name", "belongsToClassMap": table.title(), "type": "string", "column": f"{table}.name"}],
    }


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "burr"
    for table in ("person", "shop", "stadium", "company"):
        d = base / "micro_benchmark/basic/table" / table
        d.mkdir(parents=True)
        (d / "schema.sql").write_text(f"CREATE TABLE {table} (id INT, name VARCHAR(50));")
        (d / f"{table}.csv").write_text("id,name\n1,a\n")
        (d / "mapping.json").write_text(json.dumps(mapping(table)))
    return base


def test_group_export_and_feedback(root, tmp_path):
    ws = w.init("burr", "micro/basic", tmp_path / "ws", root=root)
    assert not list(ws.rglob("mapping.json"))
    assert (ws / "data/basic/table/person/schema.sql").exists() and (ws / "data/basic/table/person/person.csv").exists()
    dev = load_units(ws / "tasks/dev.jsonl")
    assert len(dev) == 1 and all(f.startswith(f"data/{dev[0]['id'].removeprefix('burr/')}/") for f in dev[0]["files"])
    assert "livesIn" not in (ws / "tasks/dev.jsonl").read_text() + (ws / "BRIEF.md").read_text()
    table = dev[0]["id"].rsplit("/", 1)[1]
    path = ws / "stages/1_explore/dev.jsonl"
    write_units(path, [{"id": dev[0]["id"], "answer": mapping(table)}])
    record = feedback.submit(ws, path)
    assert record["items"][0]["ok"] and record["items"][0]["gold"]["classes"]
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    assert len(tests) == 3
    preds = [{"id": t["id"], "answer": mapping(t["id"].rsplit("/", 1)[1])} for t in tests]
    preds[0]["answer"]["classes"][0]["class"] = "Human"          # 名字错，映射对
    preds[1]["answer"]["data_properties"][0]["column"] = "x.y"   # 映射错，名字对
    write_units(ws / "stages/4_decide/predictions.jsonl", preds)
    assert not w.check(ws)
    report = evaluate(ws)
    assert report["accuracy"] == pytest.approx(2 / 3)
    assert report["mapping_based_cls_f1"] == 1.0 and report["name_based_cls_f1"] < 1.0
    assert report["mapping_based_attr_f1"] < 1.0


def test_single_scenario_has_no_dev(root, tmp_path):
    ws = w.init("burr", "basic/table/person", tmp_path / "ws", root=root)
    assert load_units(ws / "tasks/dev.jsonl") == [] and w.status(ws)["feedback"]["mode"] == "none"
    assert (ws / "data/schema.sql").exists()


def test_compare_semantics():
    gold = mapping("person")
    pred = copy.deepcopy(gold)
    pred["object_properties"][0]["join"] = ["addr.id = person.addr_id"]   # join 两侧顺序无关
    pred["object_properties"][0]["property"] = "has_lives_in"             # 名字清洗
    pred["classes"][1]["id"] = "town/@@ADDR.CITY@@"                       # 只看模式里的列
    m = scorer.compare(gold, pred)
    assert m["mapping_based_rel_f1"] == 1.0 and m["mapping_based_cls_f1"] == 1.0 and m["name_based_rel_f1"] == 1.0
    moved = copy.deepcopy(gold)
    moved["data_properties"][0]["column"] = "x.y"
    m = scorer.compare(gold, moved)
    assert m["mapping_based_attr_f1"] == 0.0 and m["name_based_attr_f1"] == 1.0
    assert scorer.compare(gold, {})["mapping_based_cls_recall"] == 0.0
    assert scorer.compare({"classes": []}, {})["name_based_cls_f1"] == 1.0


def test_real_data(tmp_path):
    if not data_dir("burr").exists():
        pytest.skip("no local data for burr")
    ws = w.init("burr", "micro", tmp_path / "ws")
    ds = load_dataset("burr", "micro")
    gold = {t.id: scorer.gold_mapping(t.answer) for t in ds.tasks}
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tests = load_units(ws / "tasks/tasks.jsonl")
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": t["id"], "answer": gold[t["id"]]} for t in tests])
    assert not w.check(ws)
    assert evaluate(ws)["score"] == 1.0
    mondial = load_dataset("burr", "mondial")
    g = scorer.gold_mapping(mondial.tasks[0].answer)
    assert scorer.compare(g, g)["mapping_based_rel_f1"] == 1.0
