"""噪声断言（noise.jsonl）打分与 nl 模式导出。"""

import json
import pickle
from pathlib import Path

import networkx as nx
import pytest

from knosis import data_dir, load_dataset
from knosis import workspace as w
from knosis.decision import evaluate, graph_qa
from knosis.knowledge import load_units, write_units
from knosis.workspace.exporters.ngdbench import export as export_ngdbench


@pytest.fixture
def noisy_root(tmp_path):
    """clean / perturbed 配对图：1 个节点标签错、1 个节点属性错、1 条边新增、1 条边改标、1 条边删除。"""
    d = tmp_path / "NGDBenchV1_1/NGDFin"
    (d / "graph").mkdir(parents=True)
    (d / "query").mkdir()
    clean = nx.MultiDiGraph()
    clean.add_node("Account:1", label="Account", balance=10)
    clean.add_node("Account:2", label="Account", balance=20)
    clean.add_node("Person:3", label="Person", name="ann")
    clean.add_edge("Person:3", "Account:1", 0, label="Owns")
    clean.add_edge("Person:3", "Account:2", 0, label="Owns")
    perturbed = clean.copy()
    perturbed.nodes["Account:1"].update(label="Person")  # node_label
    perturbed.nodes["Account:2"].update(balance=99)  # node_attr.balance
    perturbed.add_edge("Person:3", "Account:2", 1, label="Owns")  # added
    perturbed.edges["Person:3", "Account:2", 0]["label"] = "Transfers"  # relabel
    perturbed.remove_edge("Person:3", "Account:1", 0)  # deleted
    for name, graph in [("fin.gpickle", clean), ("fin_noise_x.gpickle", perturbed)]:
        with (d / "graph" / name).open("wb") as fh:
            pickle.dump(graph, fh)
    (d / "query/complex_query.json").write_text(json.dumps([
        {"nlp": f"question {i}", "query": f"MATCH {i}", "clean_answer": i, "noise_answer": i,
         "same_as_cleangraph": True} for i in range(8)
    ] + [{"nlp": "", "query": "MATCH empty", "clean_answer": 0, "noise_answer": 0,
          "same_as_cleangraph": True}]))
    return tmp_path


def test_score_knowledge(noisy_root, tmp_path):
    ds = load_dataset("ngdbench", "ngd-fin", root=noisy_root)
    truth = graph_qa.noise_truth(ds.files["clean"], ds.files["perturbed"])
    assert truth["node_label"] == {"Account:1"}
    assert truth["node_attr"] == {"Account:1", "Account:2"}
    assert truth["node_attr_field"] == {("Account:1", "label"), ("Account:2", "balance")}
    assert truth["added"] == {("Person:3", "Account:2", "1")} and truth["relabel"] == {("Person:3", "Account:2", "0")}
    assert truth["deleted"] == {("Person:3", "Account:1", "Owns")}

    ws = tmp_path / "ws"
    (ws / "stages/4_decide").mkdir(parents=True)
    assert graph_qa.score_knowledge(ws, {}, ds) == {"noise": {"reported": False}}
    write_units(ws / "stages/4_decide/noise.jsonl", [
        {"kind": "node_label", "node": "Account:1"},
        {"kind": "node_label", "node": "Account:2"},  # 错：Account:2 的标签没变
        {"kind": "node_attr", "node": "Account:2", "field": "balance"},
        {"kind": "node_attr", "node": "Account:1"},
        {"kind": "edge", "src": "Person:3", "dst": "Account:2", "key": 0, "type": "relabel"},
        {"kind": "edge", "src": "Person:3", "dst": "Account:2", "key": 1},
        {"kind": "missing_edge", "src": "Person:3", "dst": "Account:1", "label": "Owns"},
        {"kind": "missing_edge", "src": "Person:3", "dst": "Account:9", "label": "Owns"},
    ])
    noise = graph_qa.score_knowledge(ws, {}, ds)["noise"]
    assert noise["reported"] and noise["node_label"] == {
        "n_asserted": 2, "n_true": 1, "precision": 0.5, "recall": 1.0, "f1": pytest.approx(2 / 3)}
    assert noise["node_attr"]["precision"] == 1.0 and noise["node_attr"]["recall"] == 1.0
    assert noise["node_attr_field"]["n_asserted"] == 1 and noise["node_attr_field"]["recall"] == 0.5
    assert noise["edge"]["n_asserted"] == 2 and noise["edge"]["recall"] == 1.0 and noise["edge"]["precision"] == 1.0
    assert noise["edge_added"]["n_asserted"] == 0 and noise["edge_relabel"]["precision"] == 1.0
    assert noise["missing_edge"] == {"n_asserted": 2, "n_true": 1, "precision": 0.5, "recall": 1.0,
                                     "f1": pytest.approx(2 / 3)}


def test_nl_mode(noisy_root):
    ds = load_dataset("ngdbench", "ngd-fin", root=noisy_root)
    ws = Path(noisy_root) / "nl"
    out = export_ngdbench(ds, ws, write_data=False, dev=2, question="nl")
    assert all("cypher" not in task for task in out["tasks"] + out["dev"])
    assert all(task["question"] for task in out["tasks"] + out["dev"])
    assert "自己把问题转成对 `data/graph.gpickle` 的查询" in out["brief"]
    assert "Cypher 的 `RETURN`" not in out["brief"]
    assert "噪声断言" in out["brief"] and "secret" not in out["brief"].lower()
    cypher = export_ngdbench(ds, ws, write_data=False, dev=2)
    assert all(task["cypher"] for task in cypher["tasks"])
    assert "Cypher 的 `RETURN`" in cypher["brief"]


def test_noise_split(noisy_root, tmp_path):
    ds = load_dataset("ngdbench", "ngd-fin", root=noisy_root)
    ws = w.init("ngdbench", "ngd-fin", tmp_path / "ws", root=noisy_root, dev=0, limit=8)
    w.goto(ws, "decide")
    w.next_prompt(ws)
    tasks = [task["id"] for task in load_units(ws / "tasks/tasks.jsonl")]
    assert len(tasks) == 3  # nl 为空的题不进
    gold = {task.id: task.answer for task in ds.tasks}
    write_units(ws / "stages/4_decide/predictions.jsonl", [{"id": t, "answer": gold[t]} for t in tasks])
    report = evaluate(ws)
    assert report["n_noise_unaffected"] == 3 and report["n_noise_affected"] == 0
    assert report["em_noise_unaffected"] == 1.0
    assert report["reference"]["noisy_graph_answer"]["em_noise_unaffected"] == 1.0


@pytest.mark.skipif(not (data_dir("ngdbench") / "NGDBenchV1_1/NGDFin").is_dir(), reason="NGD-Fin 原始数据不在")
def test_score_knowledge_real(tmp_path):
    ds = load_dataset("ngdbench", "ngd-fin")
    truth = graph_qa.noise_truth(ds.files["clean"], ds.files["perturbed"])
    assert [len(truth["added"]), len(truth["relabel"])] == [5497, 5513]
    assert len(truth["node_label"]) == 1008 and len(truth["node_attr"]) == 2803
    added, relabel = sorted(truth["added"])[:2], sorted(truth["relabel"])[:2]
    deleted = sorted(truth["deleted"])[:2]  # (src, dst, label)，同一条边多个 key 只算一次
    ws = tmp_path / "ws"
    (ws / "stages/4_decide").mkdir(parents=True)
    rows = [{"kind": "edge", "src": u, "dst": v, "key": k, "type": "added"} for u, v, k in added]
    rows += [{"kind": "edge", "src": u, "dst": v, "key": k, "type": "relabel"} for u, v, k in relabel]
    rows += [{"kind": "missing_edge", "src": u, "dst": v, "label": label} for u, v, label in deleted]
    rows += [{"kind": "edge", "src": "nope:1", "dst": "nope:2", "key": 0}]  # 假断言
    write_units(ws / "stages/4_decide/noise.jsonl", rows)
    noise = graph_qa.score_knowledge(ws, {}, ds)["noise"]
    assert noise["edge"]["precision"] == pytest.approx(4 / 5) and noise["edge"]["recall"] == pytest.approx(4 / 11010)
    assert noise["edge_added"]["n_asserted"] == 2 and noise["edge_relabel"]["n_asserted"] == 2
    assert noise["missing_edge"]["precision"] == 1.0 and noise["missing_edge"]["n_true"] == 1807
