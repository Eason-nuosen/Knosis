"""SpreadsheetBench：loader、导出器、打分器（含 LibreOffice 重算）。"""

import json
import shutil

import openpyxl
import pytest

from knosis import load_dataset
from knosis.decision import spreadsheetbench as sb
from knosis import workspace as w


def book(path, rows, sheet="Sheet1"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    wb.save(path)


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "sb/all_data_912_v0.1"
    items = []
    for i in range(4):
        sid = f"{i}-1" if i else 7  # 上游有整数 id
        folder = base / f"spreadsheet/{sid}"
        folder.mkdir(parents=True)
        for n in (1, 2, 3):
            book(folder / f"{n}_{sid}_input.xlsx", [["a", "b", "sum"], [n, 2, None]])
            book(folder / f"{n}_{sid}_answer.xlsx", [["a", "b", "sum"], [n, 2, n + 2]])
        items.append({"id": sid, "instruction": "put a+b in C2", "spreadsheet_path": f"spreadsheet/{sid}",
                      "instruction_type": "Cell-Level Manipulation", "answer_position": "'Sheet1'!C2"})
    (base / "dataset.json").write_text(json.dumps(items))
    return tmp_path / "sb"


def test_ranges():
    assert sb.cells("BD2:308")[:2] == ["BD2", "BD3"] and sb.cells("a1：b1") == ["A1", "B1"]
    assert len(sb.cells("A:B", 3)) == 6
    assert sb.regions("Sheet3'!A1:B2,'S 4'!C1", "x") == [("Sheet3", "A1:B2"), ("S 4", "C1")]
    assert sb.regions("A1", "  DATA ") == [("  DATA ", "A1")]
    assert sb.same(3, "3.001") and sb.same("", None) and not sb.same(3, "x")


def test_load_export_and_score(root, tmp_path):
    ds = load_dataset("spreadsheetbench", "all", root=root)
    assert [t.id for t in ds.tasks][0] == "7" and len(ds.tasks[0].answer) == 3
    ws = w.init("spreadsheetbench", "all", tmp_path / "ws", root=root, dev=1, limit=2)
    dev = [json.loads(l) for l in (ws / "tasks/dev.jsonl").read_text().splitlines()]
    assert len(dev) == 1 and (ws / dev[0]["inputs"][0]).exists()
    tid = dev[0]["id"]
    out = ws / "stages/1_explore/outputs" / tid
    out.mkdir(parents=True)
    for n in (1, 2):  # 用例 1 写公式（需重算），用例 2 写错值，用例 3 不交
        wb = openpyxl.load_workbook(ws / f"data/{tid}/{n}_input.xlsx")
        wb.active["C2"] = "=A2+B2" if n == 1 else 99
        wb.save(out / f"{n}_output.xlsx")
    pred = ws / "stages/1_explore/dev_predictions.jsonl"
    pred.write_text(json.dumps({"id": tid, "answer": {"1": f"outputs/{tid}/1_output.xlsx",
                                                      "2": f"outputs/{tid}/2_output.xlsx"}}) + "\n")
    state = w.status(ws)
    if sb.find_soffice() is None:
        pytest.skip("LibreOffice not installed")
    result = sb.score(ws, state, ds, pred, [tid])
    cases = result["items"][0]["cases"]
    assert [c["ok"] for c in cases] == [True, False, False] and "missing" in cases[2]["detail"]
    assert result["metrics"]["soft"] == pytest.approx(1 / 3) and result["metrics"]["hard"] == 0
    assert "expected 4" in result["items"][0]["gold"][0]["diff"]
    assert result["reference"]["unchanged_input"]["soft"] == 0
