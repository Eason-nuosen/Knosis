"""本体标注的导入、GT 剔除与 join 发现评分（ontology-bench 标注 → 知识层 ontology/ 子目录）。"""

import json
from pathlib import Path

import pytest

import knosis.decision.bibench as bibench
import knosis.decision.relbench as relbench
from knosis import data_dir, load_dataset
from knosis.knowledge import ontology

ANNOTATIONS = Path("/Users/eason/Desktop/manage/projects/ontology-bench/annotations-claude")


def ds(name, source, **ext):
    return {"name": name, "source": source,
            "fields": [ontology.field(n, t) for n, t in (("Id", "Integer"), ("Amount", "Float"), ("region_id", "Integer"))],
            "custom_extensions": ontology.eob(ext)}


def mapping(concept, *expressions):
    return {"concept": concept, "object_mappings": [{"referent_mappings": [{"relationship": "id", "expression": e}
                                                                          for e in expressions]}]}


@pytest.fixture
def docs():
    """一份小本体：一条 pbi_gt join、一条 inferred join、一个 SQL 视图表、一个 relbench_gt join。"""
    model = ontology.semantic_model(
        "demo",
        [ds("sales", "Sales"), ds("budget", "SELECT k, v FROM raw UNPIVOT (v FOR k IN (a, b))"),
         ds("region", "Region")],
        [{**ontology.relationship("sales", ["region_id"], "region", ["Id"], origin="pbi_gt"), "name": "r1"},
         {**ontology.relationship("sales", ["Id"], "region", ["Id"], origin="inferred"), "name": "r2"},
         {**ontology.relationship("region", ["Id"], "sales", ["Amount"], origin="relbench_gt"), "name": "r3"}],
        provenance={"method": "llm"})
    model["metrics"] = [{"name": "total", "expression": {"dialects": [{"dialect": "ANSI_SQL", "expression": "SUM(sales.Amount)"}]},
                         "custom_extensions": ontology.eob({"origin": "annotator"})},
                        {"name": "budget_total", "expression": {"dialects": [{"dialect": "ANSI_SQL", "expression": "SUM(budget.Amount)"}]}}]
    model["custom_extensions"] = ontology.eob({
        "provenance": {"method": "llm"},
        "source": {"dataset": "bi-bench", "item": "1", "note": "Annotator-only evidence: query_metadata.json"},
        "pbi_transforms": [{"dataset": "budget", "op": "unpivot", "origin": "bibench_transformation_output"}],
    })
    return {"semantic_model": model,
            "ontology": {"version": ontology.VERSION, "name": "demo_ontology",
                         "ontology": [{"concept": c, "type": "Entity", "description": c} for c in ("Sale", "Budget")]},
            "mapping": {"name": "demo_mapping",
                        "concept_mappings": [mapping("Sale", "sales.Amount"), mapping("Budget", "budget.Amount")],
                        "custom_extensions": ontology.eob({
                            "provenance": {"method": "llm"},
                            "annotations": [{"target": "Sale", "note": "ok"},
                                            {"target": "Budget", "note": "GT unpivot of budget"}]})}}


def test_strip_gt_removes_pbi_gt_and_oracle(docs):
    assert not ontology.check_ontology(docs)
    stripped, report = ontology.strip_gt(docs)
    kept = {r["name"] for r in stripped["semantic_model"]["relationships"]}
    assert kept == {"r2", "r3"}  # pbi_gt 去掉，inferred / relbench_gt 保留
    assert [d["name"] for d in stripped["semantic_model"]["datasets"]] == ["sales", "region"]
    assert [m["name"] for m in stripped["semantic_model"]["metrics"]] == ["total"]
    assert [cm["concept"] for cm in stripped["mapping"]["concept_mappings"]] == ["Sale"]
    ext = ontology.eob_data(stripped["mapping"])
    assert [a["target"] for a in ext["annotations"]] == ["Sale"]
    root = ontology.eob_data(stripped["semantic_model"])
    assert root["provenance"]["method"] == "llm" and "relationship:1" in root["provenance"]["stripped"]
    assert root["source"]["note"].startswith("（提到被剔除")
    assert root["pbi_transforms"] == []
    assert report == {"relationship": 1, "dataset": 1, "metric": 1, "mapping": 1, "annotation": 1, "transform": 1, "note": 1}
    assert not ontology.check_ontology(stripped)


def test_strip_gt_does_not_touch_the_input(docs):
    before = json.dumps(docs, ensure_ascii=False, sort_keys=True)
    ontology.strip_gt(docs)
    assert json.dumps(docs, ensure_ascii=False, sort_keys=True) == before


def test_strip_gt_keeps_relbench_units_whole(tmp_path):
    model = ontology.semantic_model("relbench_demo", [ds("a", "a"), ds("b", "b")],
                                    [{**ontology.relationship("a", ["Id"], "b", ["Id"], origin="relbench_gt"), "name": "fk"}],
                                    provenance={"method": "llm"})
    stripped, report = ontology.strip_gt({"semantic_model": model})
    assert len(stripped["semantic_model"]["relationships"]) == 1 and not any(report.values())


def annotation(root, name):
    """一个最小的标注单元：三个 yaml + report.md。"""
    model = ontology.semantic_model(
        name, [ds("sales", "Sales", raw={"path": "bi-bench/u1/Sales.csv"}),
               ds("plan", "SELECT * FROM raw UNPIVOT (v FOR k IN (a))"), ds("lookup", "Lookup")],
        [{**ontology.relationship("sales", ["Id"], "plan", ["Id"], origin="pbi_gt"), "name": "pbi"},
         {**ontology.relationship("sales", ["Id"], "lookup", ["Id"], origin="inferred"), "name": "inf"}],
        provenance={"method": "llm"})
    onto = {"version": ontology.VERSION, "name": f"{name}_ontology",
            "ontology": [{"concept": c, "type": "Entity", "description": c} for c in ("Sale", "Plan")]}
    map_ = {"version": ontology.VERSION, "name": f"{name}_mapping",
            "concept_mappings": [mapping("Sale", "sales.Amount"), mapping("Plan", "plan.Amount")]}
    ontology.write_ontology(root / name, {"semantic_model": model, "ontology": onto, "mapping": map_})
    (root / name / "report.md").write_text("# report\n")
    return root / name


def test_import_annotation_into_subdirectories(tmp_path):
    src = annotation(tmp_path / "ann", "101248502")
    report = ontology.import_annotation(src, tmp_path / "kb/knowledge/ontology")
    out = tmp_path / "kb/knowledge/ontology/101248502"
    assert sorted(p.name for p in out.iterdir()) == ["101248502.mapping.yaml", "101248502.ontology.yaml",
                                                     "101248502.semantic_model.yaml"]
    assert report == {"unit": "101248502", "dir": str(out), "stripped": False}
    docs = ontology.load_ontology(out)
    assert len(docs["semantic_model"]["relationships"]) == 2 and not ontology.check_ontology(docs)
    # 多个单元可共存
    ontology.import_annotation(annotation(tmp_path / "ann", "202"), tmp_path / "kb/knowledge/ontology")
    assert sorted(p.name for p in (tmp_path / "kb/knowledge/ontology").iterdir()) == ["101248502", "202"]


def test_import_annotation_with_strip(tmp_path):
    src = annotation(tmp_path / "ann", "u1")
    report = ontology.import_annotation(src, tmp_path / "onto", strip=True)
    assert report["stripped"] and report["counts"]["dataset"] == 2  # plan 是 SQL 视图；关系引用了它，sales 也按引用剔掉
    docs = ontology.load_ontology(tmp_path / "onto/u1")
    assert [d["name"] for d in docs["semantic_model"]["datasets"]] == ["sales", "lookup"]
    assert [r["name"] for r in docs["semantic_model"]["relationships"]] == ["inf"]
    assert [cm["concept"] for cm in docs["mapping"]["concept_mappings"]] == ["Sale"]
    assert not ontology.check_ontology(docs)


def test_bibench_join_scorer(tmp_path):
    """Power BI 的表名与 CSV 文件名只差空格标点；方向无关。"""
    root = tmp_path
    meta = tmp_path / "tools/data_management_tools/metadata/7"
    # loader 的 root 是 `bi-bench/` 目录，scorer 从 `bi-bench/<用例>/` 往上两级找 metadata
    for path, text in {
        root / "bi-bench/queries.json": json.dumps({"7": "q"}),
        root / "bi-bench/7/Sales.csv": "CountryId,Amount\n1,3\n",
        root / "bi-bench/7/Country List.csv": "Id,Name\n1,A\n",
        meta / "_tables.csv": "ID,Name\n1,Sales\n2,Country List\n3,Unrelated\n",
        meta / "_columns.csv": ("ID,TableID,ExplicitName,InferredName\n11,1,CountryId,\n12,1,Amount,\n"
                                "20,2,Id,\n21,2,Name,\n30,3,Id,\n"),
        meta / "_relationships.csv": ("ID,FromTableID,FromColumnID,FromCardinality,ToTableID,ToColumnID,ToCardinality\n"
                                      "1,2,20,1,1,11,2\n"),
    }.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    model = ontology.semantic_model(
        "bibench_7", [{"name": "sales", "source": "Sales", "fields": [ontology.field("CountryId", "Integer")],
                       "custom_extensions": ontology.eob({"raw": {"path": "bi-bench/7/Sales.csv"}})},
                      {"name": "country_list", "source": "Country List", "fields": [ontology.field("Id", "Integer")],
                       "custom_extensions": ontology.eob({"raw": {"path": "bi-bench/7/Country List.csv"}})},
                      {"name": "unrelated", "source": "Unrelated", "fields": [ontology.field("Id", "Integer")],
                       "custom_extensions": ontology.eob({"raw": {"path": "bi-bench/7/Unrelated.csv"}})}],
        # 写成反方向、且列数 / 表名大小写不同，仍然命中
        [{**ontology.relationship("sales", ["CountryId"], "country_list", ["Id"]), "name": "ok"},
         {**ontology.relationship("unrelated", ["Id"], "sales", ["Amount"]), "name": "wrong"}])
    ontology.write_ontology(tmp_path / "kb/knowledge/ontology/7", {"semantic_model": model})
    dsx = load_dataset("bibench", "7", root=root)
    report = bibench.join_report(tmp_path, dsx)
    assert report["reported"] and report["units"] == 1
    assert report["scores"]["7"]["7"] == {"n_pred": 2, "n_gold": 1, "n_hit": 1,
                                          "precision": 0.5, "recall": 1.0, "f1": pytest.approx(2 / 3)}
    assert not bibench.join_report(tmp_path / "empty", dsx)["reported"]


def test_score_knowledge_reports_inherited_snapshot(tmp_path):
    meta = tmp_path / "bibench/tools/data_management_tools/metadata/7"
    meta.mkdir(parents=True)
    (meta / "_tables.csv").write_text("ID,Name\n1,Sales\n")
    (meta / "_columns.csv").write_text("ID,TableID,ExplicitName,InferredName\n11,1,CountryId,\n")
    (meta / "_relationships.csv").write_text("ID,FromTableID,FromColumnID,FromCardinality,ToTableID,ToColumnID,ToCardinality\n")
    ontology.write_ontology(tmp_path / "ws/kb/knowledge/ontology", {"semantic_model": ontology.semantic_model(
        "w", [{"name": "sales", "source": "Sales", "fields": [ontology.field("CountryId", "Integer")]}] , [])})
    ontology.write_ontology(tmp_path / "ws/stages/0_inherit/kb/knowledge/ontology", {"semantic_model": ontology.semantic_model(
        "k", [{"name": "sales", "source": "Sales", "fields": [ontology.field("CountryId", "Integer")]}], [])})
    dsx = type("D", (), {"root": tmp_path / "bibench/bi-bench/7", "tasks": []})()
    result = bibench.score_knowledge(tmp_path / "ws", {}, dsx)
    assert result["ontology"]["reported"] and result["K_inherit"]["reported"]
    assert not bibench.score_knowledge(tmp_path / "nowhere", {}, dsx)["ontology"]["reported"]


def test_relbench_join_scorer(tmp_path):
    schema = {"tables": {"races": {"pkey": "raceId"}, "results": {"pkey": "resultId", "fkeys": {"raceId": "races"}},
                         "lap_times": {"pkey": "lapId", "fkeys": {"raceId": "races"}}}}
    model = ontology.semantic_model(
        "relbench_demo", [{"name": n, "source": n, "fields": [ontology.field("x", "Integer")]} for n in schema["tables"]],
        [{**ontology.relationship("results", ["raceId"], "races", ["raceId"]), "name": "a"}],
        provenance={"method": "llm"})
    ontology.write_ontology(tmp_path / "kb/knowledge/ontology", {"semantic_model": model})
    dsx = type("D", (), {"scenario": "rel-f1", "schema": schema})()
    report = relbench.db_report(tmp_path, dsx)
    assert report["scores"][""] == {"n_pred": 1, "n_gold": 2, "n_hit": 1,
                                    "precision": 1.0, "recall": 0.5, "f1": pytest.approx(2 / 3)}
    assert not relbench.db_report(tmp_path / "empty", dsx)["reported"]


# ---------------------------------------------------------------- 真实标注（本地有才跑）


def bi_units():
    root = ANNOTATIONS / "bi-bench"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


@pytest.mark.skipif(not bi_units(), reason="no local ontology-bench annotations")
def test_strip_all_real_bi_bench_units(tmp_path):
    totals = {}
    for unit in bi_units():
        docs, report = ontology.strip_gt(ontology.load_ontology(unit))
        assert ontology.check_ontology(docs) == [], unit.name
        for key, value in report.items():
            totals[key] = totals.get(key, 0) + value
        assert all(ontology.eob_data(r).get("origin") in (None, "inferred", "relbench_gt")
                   for r in docs["semantic_model"].get("relationships", []))
    assert len(bi_units()) == 83
    assert totals["relationship"] == 578  # 683 条 pbi_gt：105 条只连 transient 表，计入 dataset
    assert totals["dataset"] == 166


@pytest.mark.skipif(not bi_units() or not data_dir("bibench").is_dir(), reason="no local data")
@pytest.mark.parametrize("unit, case", [("101248502", "101248502"), ("159612708", "159612708")])
def test_real_annotation_scores_high_and_stripped_scores_low(tmp_path, unit, case):
    docs = ontology.load_ontology(ANNOTATIONS / "bi-bench" / unit)
    assert load_dataset("bibench", case).tasks  # 用例在本地
    meta = data_dir("bibench") / "tools/data_management_tools/metadata" / case
    gold = bibench.gold_pairs(meta, docs["semantic_model"], case)
    raw = bibench.score_pairs(bibench.pairs(docs["semantic_model"]), gold)
    stripped = ontology.strip_gt(docs)[0]
    after = bibench.score_pairs(bibench.pairs(stripped["semantic_model"]), gold)
    assert raw["recall"] > 0.9 and after["n_pred"] < raw["n_pred"] and after["recall"] < raw["recall"]
