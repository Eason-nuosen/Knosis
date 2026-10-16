import pandas as pd
import pytest

from knosis import tools
from knosis.knowledge import check_units, load_units, ontology
from knosis.tools.joins import run as joins
from knosis.tools.profile import run as profile
from knosis.tools.sql import run as sql


@pytest.fixture
def lake(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    pd.DataFrame({"OrderID": [1, 2, 3, 4], "CustID": [10, 10, 11, 12], "Amount": [1.5, 2.0, 3.0, 4.0],
                  "Flag": [True] * 4}).to_csv(d / "orders.csv", index=False)
    pd.DataFrame({"Id": [10, 11, 12, 13], "Name": ["a", "b", "c", "d"]}).to_csv(d / "Customer List.csv", index=False)
    pd.DataFrame({"Country": ["x", "y"], "2019": [1, 2], "2020": [3, 4], "2021": [5, 6], "2022": [7, 8]}).to_csv(
        d / "wide.csv", index=False)
    (d / "_meta.csv").write_text("ignored\n1\n")
    return tmp_path


def test_read_tables(lake):
    tables = tools.read_tables([lake / "data"])
    assert set(tables) == {"orders", "Customer_List", "wide"}
    assert tools.table_name(lake / "3 items.csv") == "_3_items"


def test_sql(lake, monkeypatch, capsys):
    monkeypatch.chdir(lake)
    out = lake / "out"
    sql.main(["--tables", "data", "--out", str(out), "--query",
              "SELECT c.Name, SUM(o.Amount) AS total FROM orders o JOIN Customer_List c ON o.CustID = c.Id "
              "WHERE c.Name != 'a;b' GROUP BY c.Name ORDER BY c.Name"])
    assert pd.read_csv(out / "result.csv").to_dict("list") == {"Name": ["a", "b", "c"], "total": [3.5, 3.0, 4.0]}
    assert load_units(out / "units.jsonl") == []
    sql.main(["--tables", "data", "--out", str(out), "--list"])
    assert "Customer_List" in pd.read_csv(out / "result.csv")["table"].tolist()
    assert list(sql.statements("SELECT 1; SELECT ';'; ")) == ["SELECT 1;", " SELECT ';';"]


def test_profile(lake, monkeypatch):
    monkeypatch.chdir(lake)
    out = lake / "out"
    profile.main(["--tables", "data", "--out", str(out)])
    units = {u["id"]: u for u in load_units(out / "units.jsonl")}
    assert not check_units(list(units.values()), root=lake)
    assert units["profile/orders"]["meta"]["key_candidates"] == ["OrderID", "Amount"]
    assert "profile/orders/Flag/constant" in units
    assert "profile/wide/wide" in units
    assert len(pd.read_csv(out / "profile.csv")) == 11


def test_joins(lake, monkeypatch):
    monkeypatch.chdir(lake)
    out = lake / "out"
    joins.main(["--tables", "data", "--out", str(out), "--ontology", str(out / "onto"), "--name", "lake"])
    found = pd.read_csv(out / "joins.csv")
    top = found.iloc[0]
    assert (top.from_table, top.from_column, top.to_table, top.to_column) == ("orders", "CustID", "Customer_List", "Id")
    assert not ((found.from_column == "Amount") | (found.from_column == "Flag")).any()
    units = load_units(out / "units.jsonl")
    assert units and not check_units(units, root=lake)
    docs = ontology.load_ontology(out / "onto")
    assert not ontology.check_ontology(docs)
    rels = docs["semantic_model"]["relationships"]
    assert any(r["from"] == "orders" and r["to"] == "customer_list" for r in rels)
    keys = {d["name"]: d.get("primary_key") for d in docs["semantic_model"]["datasets"]}
    assert keys["orders"] == ["OrderID"] and keys["customer_list"] == ["Id"]


def test_tools_markdown_by_modality():
    text = tools.tools_markdown(["table"])
    assert "## sql" in text and "## tabpfn" in text and "## ultra" not in text and "## joins" not in text
