import json
from pathlib import Path

import pandas as pd
import pytest

from knosis import load_dataset
from knosis import workspace as w
from knosis.cli import main
from knosis.knowledge import check_knowledge, check_units, ontology, write_units

SALES = Path(__file__).parent / "fixtures/sales_bi"  # ontology-bench 的 EOB v0.2 样例


def test_load_and_check_reference_example():
    docs = ontology.load_ontology(SALES)
    assert set(docs) == set(ontology.LAYERS)
    assert not ontology.check_ontology(docs)
    names = ontology.refs(docs)
    assert {"sales", "sales.Amount", "Product", "Product.key"} <= names


def test_check_catches_broken_references():
    docs = ontology.load_ontology(SALES)
    docs["semantic_model"]["relationships"][0]["from_columns"] = ["Nope"]
    docs["mapping"]["concept_mappings"][0]["object_mappings"][0]["referent_mappings"][0]["expression"] = "products.Missing"
    docs["mapping"]["concept_mappings"].append({"concept": "Ghost"})
    issues = ontology.check_ontology(docs)
    assert any("unknown field" in i for i in issues)
    assert any("products.Missing" in i for i in issues)
    assert any("unknown concept Ghost" in i for i in issues)


def test_units_view():
    units = ontology.ontology_units(ontology.load_ontology(SALES))
    assert not check_units(units)
    assert {u["meta"]["layer"] for u in units} == {"semantic_model", "ontology"}
    concept = next(u for u in units if u["id"] == "ontology/concept/Product")
    assert concept["about"] == ["Product"] and concept["status"] == "verified"  # provenance.method = human


def test_about_refs(tmp_path):
    knowledge = tmp_path
    ontology.write_ontology(knowledge / "kb/knowledge/ontology", ontology.load_ontology(SALES))
    unit = {"id": "u", "content": "金额是美元", "form": "fact", "provenance": "data/x.csv#col/Amount",
            "status": "observed", "about": ["sales.Amount", "MoneyUSD"]}
    write_units(knowledge / "kb/knowledge/units.jsonl", [unit])
    assert not check_knowledge(knowledge)
    write_units(knowledge / "kb/knowledge/units.jsonl", [{**unit, "about": ["sales.Nope"]}])
    assert any("sales.Nope" in i for i in check_knowledge(knowledge))


def test_from_tables_roundtrip(tmp_path):
    frames = {"Order Lines": pd.DataFrame({"OrderID": [1], "Amount": [2.5]}), "orders": pd.DataFrame({"OrderID": [1]})}
    rel = ontology.relationship("order_lines", ["OrderID"], "orders", ["OrderID"], confidence=0.9)
    model = ontology.from_tables("demo", frames, {"orders": ["OrderID"]}, [rel], provenance={"method": "tool"})
    assert [d["name"] for d in model["datasets"]] == ["order_lines", "orders"]
    assert model["datasets"][0]["source"] == "Order Lines"
    assert model["datasets"][0]["fields"][1]["datatype"] == "Float"
    ontology.write_ontology(tmp_path, {"semantic_model": model})
    docs = ontology.load_ontology(tmp_path)
    assert not ontology.check_ontology(docs)
    assert ontology.eob_data(docs["semantic_model"]["relationships"][0]) == {"confidence": 0.9}
    assert all(u["status"] == "inferred" for u in ontology.ontology_units(docs))


@pytest.fixture
def bibench_root(tmp_path):
    bench = tmp_path / "bi-bench"
    meta = tmp_path / "tools/data_management_tools/metadata/7"
    for path, text in {
        bench / "queries.json": json.dumps({"7": "total?"}),
        bench / "7/Sales.csv": "CountryId,Amount\n1,3\n",
        bench / "7/Country List.csv": "Id,Name\n1,A\n",
        bench / "gt/7.csv": "x\n3\n",
        meta / "_tables.csv": "ID,Name\n1,Sales\n2,Country List\n3,DateTableTemplate_x\n",
        meta / "_columns.csv": (
            "ID,TableID,ExplicitName,InferredName,ExplicitDataType,InferredDataType,Type,Expression\n"
            "10,1,RowNumber-1,,6,19,3,\n11,1,CountryId,,6,19,1,\n12,1,Amount,,8,19,1,\n"
            "13,1,Big,,1,11,2,[Amount] > 2\n20,2,Id,,6,19,1,\n21,2,,Name,1,2,1,\n30,3,Date,,9,19,1,\n"
        ),
        meta / "_relationships.csv": (
            "ID,FromTableID,FromColumnID,FromCardinality,ToTableID,ToColumnID,ToCardinality,IsActive,CrossFilteringBehavior\n"
            "1,2,20,1,1,11,2,True,2\n"
        ),
    }.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_from_bibench(bibench_root, tmp_path, capsys):
    model = ontology.from_bibench(load_dataset("bibench", "7", root=bibench_root))
    assert [d["name"] for d in model["datasets"]] == ["sales", "country_list"]
    sales = model["datasets"][0]
    assert [f["name"] for f in sales["fields"]] == ["CountryId", "Amount", "Big"]
    assert sales["fields"][2]["expression"]["dialects"][0] == {"dialect": "DAX", "expression": "[Amount] > 2"}
    assert sales["fields"][2]["datatype"] == "Boolean"
    assert model["datasets"][1]["fields"][1]["name"] == "Name"
    [rel] = model["relationships"]
    # Power BI 里 from 是 one 侧；Ossie 的 from 必须是 many 侧
    assert (rel["from"], rel["from_columns"], rel["to"], rel["to_columns"]) == ("sales", ["CountryId"], "country_list", ["Id"])
    assert ontology.eob_data(rel) == {"cardinality": "one-to-many", "active": True, "cross_filter": "both"}
    assert not ontology.check_ontology({"semantic_model": model})
    ontology.write_ontology(tmp_path / "onto", {"semantic_model": model})
    main(["ontology", "check", str(tmp_path / "onto")])
    assert capsys.readouterr().out.strip() == "OK"


def test_workspace_snapshots_and_forks_ontology(tmp_path):
    root = tmp_path / "raw/toy"
    root.mkdir(parents=True)
    pd.DataFrame({"x": range(6), "y": ["a", "b"] * 3}).to_parquet(root / "data.parquet")
    pd.DataFrame({"repeat": 0, "fold": 0, "row": range(6), "split": ["train"] * 4 + ["test"] * 2}).to_parquet(root / "splits.parquet")
    (root / "meta.json").write_text(json.dumps({"target": "y", "problem_type": "binary", "categorical": [], "n_rows": 6, "n_features": 1}))
    ws = w.init("tabarena", "toy", tmp_path / "ws", root=root.parent)
    w.goto(ws, "extract")
    model = ontology.from_tables("toy", {"train": pd.read_parquet(ws / "data/train.parquet")}, {"train": ["row_id"]})
    ontology.write_ontology(ws / "kb/knowledge/ontology", {"semantic_model": model})
    write_units(ws / "kb/knowledge/units.jsonl", [{"id": "u", "content": "x 是整数", "form": "fact", "status": "observed",
                                                 "provenance": "data/train.parquet#col/x", "about": ["train.x"]}])
    assert not w.check(ws)
    assert (ws / "stages/2_extract/kb/knowledge/ontology/toy.semantic_model.yaml").exists()
    write_units(ws / "kb/knowledge/units.jsonl", [{"id": "u", "content": "x", "form": "fact", "status": "observed",
                                                 "provenance": "data/train.parquet#col/x", "about": ["train.zzz"]}])
    w.next_prompt(ws)
    (ws / "stages/3_refine/round_1/changelog.md").write_text("bad ref")
    assert any("train.zzz" in i for i in w.check(ws))
    assert (w.fork(ws, tmp_path / "k0", "K_0") / "kb/knowledge/ontology/toy.semantic_model.yaml").exists()
    assert not (w.fork(ws, tmp_path / "none", "none") / "kb/knowledge/ontology").exists()


@pytest.mark.parametrize("name, scenario, convert", [
    ("bibench", "101248502", ontology.from_bibench), ("relbench", "rel-f1", ontology.from_relbench),
])
def test_real_conversion(name, scenario, convert):
    from knosis import data_dir

    if not data_dir(name).exists():
        pytest.skip(f"no local data for {name}")
    model = convert(load_dataset(name, scenario))
    assert model["datasets"] and model["relationships"]
    assert not ontology.check_ontology({"semantic_model": model})


def test_units_status_from_element_origin():
    model = ontology.semantic_model("demo", [{"name": "t", "source": "t", "fields": [ontology.field("a", "Integer")]}],
                                    [ontology.relationship("t", ["a"], "t", ["a"], origin="pbi_gt"),
                                     {**ontology.relationship("t", ["a"], "t", ["a"]), "name": "inferred_join",
                                      "custom_extensions": ontology.eob({"origin": "inferred"})}],
                                    provenance={"method": "converted"})
    units = ontology.ontology_units({"semantic_model": model})
    status = {u["id"]: u["status"] for u in units}
    assert status == {"ontology/dataset/t": "observed", "ontology/join/t_a_to_t": "observed",
                      "ontology/join/inferred_join": "inferred"}
    model["relationships"][1]["custom_extensions"] = ontology.eob({"origin": "human"})
    assert ontology.ontology_units({"semantic_model": model})[2]["status"] == "verified"


def test_sql_source_is_replaced_by_a_marker():
    model = ontology.semantic_model("demo", [{"name": "t", "source": "SELECT a FROM raw UNPIVOT (v FOR k IN (b))",
                                              "fields": [ontology.field("a", "Integer")]}])
    [unit] = ontology.ontology_units({"semantic_model": model})
    assert "（SQL 视图）" in unit["content"] and "UNPIVOT" not in unit["content"]
