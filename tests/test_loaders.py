import json

import pandas as pd
import pytest

from knosis import Dataset, data_dir, describe, list_datasets, list_scenarios, load_dataset, read

ALL = {"ngdbench", "relbench", "burr", "newtonbench", "llm-srbench", "alphabench", "kramabench", "tabarena", "bibench", "spreadsheetbench", "text", "traces", "whoandwhen"}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_registry_and_cards():
    assert set(list_datasets()) == ALL
    for name in ALL:
        assert describe(name).startswith("# ")
        list_scenarios(name)


@pytest.mark.parametrize("name, leaks", [
    ("burr", ['"classes"', '"object_properties"', '"data_properties"']),
    ("newtonbench", ["return ", "mass1 * mass2", "/ distance ** 2", "M**1.5", "-1/log("]),
    ("llm-srbench", ["np.exp(", "sqrt(", "x**2"]),
    ("kramabench", ['"answer":', "def solve"]),
    ("whoandwhen", ["hc-", "ag-1", "mistake_step\": "]),
])
def test_cards_do_not_leak_gt(name, leaks):
    card = describe(name)
    for s in leaks:
        assert s not in card


def test_read_dispatch(tmp_path):
    assert read(write(tmp_path / "a.json", '{"x": 1}')) == {"x": 1}
    assert read(write(tmp_path / "a.jsonl", '{"x": 1}\n{"x": 2}\n')) == [{"x": 1}, {"x": 2}]
    assert read(write(tmp_path / "a.csv", "a,b\n1,2\n")).shape == (1, 2)
    assert read(write(tmp_path / "a.sql", "CREATE TABLE t (a INT);")).startswith("CREATE")
    assert len(read(tmp_path)) == 4


# ---------------------------------------------------------------- 每个 loader 一个最小目录


def test_ngdbench(tmp_path):
    d = tmp_path / "NGDBenchV1_1" / "NGDFin"
    write(d / "graph" / "fin.gpickle", "")
    write(d / "graph" / "fin_noise_2026.gpickle", "")
    write(d / "query" / "complex_query_agg.json", json.dumps([{"nlp": "q?", "query": "MATCH", "clean_answer": [1], "noise_answer": [2]}]))
    ds = load_dataset("ngdbench", "ngd-fin", root=tmp_path)
    assert set(ds.files) == {"clean", "perturbed"}
    assert ds.tasks[0].input == "q?" and ds.tasks[0].answer == [1]


def test_relbench(tmp_path):
    d = tmp_path / "rel-x"
    write(d / "manifest.yaml", "tables:\n  t:\n    pkey: id\n")
    (d / "db").mkdir()
    pd.DataFrame({"id": [1]}).to_parquet(d / "db" / "t.parquet")
    write(d / "tasks" / "y" / "manifest.yaml", "description: predict y\ntask_type: binary_classification\n")
    pd.DataFrame({"y": [0]}).to_parquet(d / "tasks" / "y" / "train.parquet")
    ds = load_dataset("relbench", "rel-x", root=tmp_path)
    assert ds.schema["tables"]["t"]["pkey"] == "id"
    assert ds.read("t").shape == (1, 1)
    assert [t.id for t in ds.tasks] == ["rel-x/y/train"]
    assert ds.read(ds.tasks[0].answer).shape == (1, 1)


def test_burr(tmp_path):
    d = tmp_path / "micro_benchmark" / "basic" / "table" / "person"
    write(d / "schema.sql", "CREATE TABLE person (id INT);")
    write(d / "mapping.json", "{}")
    ds = load_dataset("burr", "basic/table/person", root=tmp_path)
    assert "CREATE TABLE" in ds.schema["ddl"]
    assert ds.tasks[0].answer.name == "mapping.json"


def test_kramabench(tmp_path):
    write(tmp_path / "workload" / "legal.json", json.dumps([{"id": "legal-easy-1", "query": "q", "answer": 3, "answer_type": "numeric_exact"}]))
    ds = load_dataset("kramabench", "legal", root=tmp_path)
    assert ds.tasks[0].answer == 3
    assert ds.files["lake"] == tmp_path / "data" / "legal" / "input"


def test_newtonbench(tmp_path):
    write(tmp_path / "modules" / "m0_gravity" / "prompts.py", 'PARAM_DESCRIPTION = """- mass1: m"""')
    write(tmp_path / "modules" / "m0_gravity" / "laws.py", "")
    ds = load_dataset("newtonbench", "m0_gravity", root=tmp_path)
    assert len(ds.tasks) == 27
    assert ds.tasks[0].answer.endswith("laws.py::_ground_truth_law_easy_v0")
    assert "mass1" in ds.tasks[0].input


def test_llm_srbench(tmp_path):
    (tmp_path / "data").mkdir()
    pd.DataFrame({"name": ["P1"], "symbols": [["x", "y"]], "symbol_descs": [["in", "out"]],
                  "symbol_properties": [["V", "O"]], "expression": ["y = 2*x"]}).to_parquet(tmp_path / "data" / "lsr_transform-0.parquet")
    ds = load_dataset("llm-srbench", "lsr_transform", root=tmp_path)
    assert ds.tasks[0].answer == "y = 2*x"
    assert ds.tasks[0].meta["hdf5_group"] == "/lsr_transform/P1"
    assert "expression" not in ds.tasks[0].meta


def test_alphabench(tmp_path):
    gen = tmp_path / "benchmark" / "data" / "generate"
    write(gen / "T1_Text2Alpha.json", json.dumps({"easy": ["moving average"], "hard": ["momentum"]}))
    write(gen / "T1_Stability.json", json.dumps([{"base_prompt": "ratio", "factor_gt": "Mean($close, 5)"}]))
    write(gen / "tags_system.json", json.dumps({"Tag": "desc"}))
    write(tmp_path / "benchmark" / "data" / "evaluate" / "pool" / "factor_pool.json", json.dumps({"f1": "$close"}))
    ds = load_dataset("alphabench", root=tmp_path)
    by_id = {t.id: t for t in ds.tasks}
    assert set(by_id) == {"generate/T1_Stability/all/0", "generate/T1_Text2Alpha/easy/0",
                          "generate/T1_Text2Alpha/hard/0", "evaluate/f1"}
    assert by_id["generate/T1_Stability/all/0"].answer == "Mean($close, 5)"
    assert "factor_gt" not in by_id["generate/T1_Stability/all/0"].meta
    assert len(load_dataset("alphabench", "evaluate", root=tmp_path).tasks) == 1


def test_bibench(tmp_path):
    bench = tmp_path / "bi-bench"
    write(bench / "queries.json", json.dumps({"1": "total sales per year?", "2-1": "count orders?"}))
    write(bench / "1" / "Sales.csv", "year,amount\n2020,3\n")
    write(bench / "gt" / "1_1.csv", "year,amount\n2020,3\n")
    write(bench / "gt" / "1_2.csv", "amount,year\n3,2020\n")
    write(bench / "gt" / "2-1.csv", "n\n5\n")
    meta = tmp_path / "tools" / "data_management_tools"
    write(meta / "metadata" / "1" / "query_metadata.json", json.dumps({"tables": ["Sales.csv"]}))
    assert len(load_dataset("bibench", root=tmp_path).tasks) == 2
    ds = load_dataset("bibench", "1", root=tmp_path)
    assert [p.name for p in ds.tasks[0].answer] == ["1_1.csv", "1_2.csv"]
    assert ds.tasks[0].meta["oracle"] == {"tables": ["Sales.csv"]}
    assert ds.read("Sales").shape == (1, 2)
    assert load_dataset("bibench", "2-1", root=tmp_path).tasks[0].answer[0].name == "2-1.csv"


def test_tabarena(tmp_path):
    d = tmp_path / "toy"
    d.mkdir()
    pd.DataFrame({"x": [1, 2, 3, 4], "y": ["a", "b", "a", "b"]}).to_parquet(d / "data.parquet")
    pd.DataFrame({"repeat": 0, "fold": [0, 0, 0, 0, 1, 1, 1, 1], "row": [0, 1, 2, 3, 0, 1, 2, 3],
                  "split": ["train", "train", "train", "test", "train", "test", "train", "train"]}).to_parquet(d / "splits.parquet")
    write(d / "meta.json", json.dumps({"target": "y", "problem_type": "binary", "categorical": [], "n_rows": 4, "n_features": 1}))
    ds = load_dataset("tabarena", "toy", root=tmp_path)
    assert [t.id for t in ds.tasks] == ["toy/r0f0", "toy/r0f1"]
    assert ds.tasks[0].meta["test"] == [3] and ds.tasks[0].answer == ["b"]
    assert ds.tasks[1].answer == ["b"]


def test_text(tmp_path):
    write(tmp_path / "a.md", "Hello world.\n\nSecond paragraph.")
    write(tmp_path / "copy.txt", "hello   WORLD. second paragraph")
    ds = load_dataset("text", tmp_path, chunk_chars=12, overlap=2,
                      extractor=lambda doc_id, text: [])
    assert ds.schema["documents"] == ["a.md"]
    assert ds.schema["duplicates"] == {"a.md": ["copy.txt"]}
    chunks = [u for u in ds.units if u.form == "chunk"]
    assert len(chunks) > 1 and chunks[0].provenance.startswith("text:a.md#0-")


# ---------------------------------------------------------------- 本地真实数据（有就跑）


@pytest.mark.parametrize("name, scenario", [
    ("ngdbench", "ngd-fin"), ("relbench", "rel-f1"), ("burr", "mondial"), ("kramabench", "wildfire"),
    ("newtonbench", "m0_gravity"), ("alphabench", None), ("llm-srbench", "lsr_synth_matsci"),
    ("tabarena", "houses"), ("bibench", "101248502"),
])
def test_real_data(name, scenario):
    if not data_dir(name).exists():
        pytest.skip(f"no local data for {name}")
    ds = load_dataset(name, scenario)
    assert isinstance(ds, Dataset) and ds.tasks
