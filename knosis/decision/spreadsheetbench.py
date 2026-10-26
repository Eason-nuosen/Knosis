"""SpreadsheetBench 打分：移植上游 `evaluation/evaluation.py` 的单元格比较，评测前用 LibreOffice 重算公式。

交付 `predictions.jsonl`，每行 `{"id": 指令 id, "answer": {"<用例号>": "<输出 xlsx 路径>"}}`，
路径相对交付文件所在目录。每个用例：输出文件先经 LibreOffice 打开重算并另存（与上游 `open_spreadsheet.py` 一致，
公式的计算结果才会被 openpyxl `data_only=True` 读到），再在 `answer_position` 内逐格比较值：
数值保留 2 位小数，datetime 转 Excel 序列号取整，time 取到分钟，能转成数字的字符串按数字比，空串等于空，类型不同即不等。
与上游的两处不同：答案文件含 TODAY() / NOW() 时一起重算（缓存值是标注当天的，否则正确公式也判错）；
`answer_position` 的 sheet 名精确匹配不到时按去空格、忽略大小写匹配（上游数据里有 `Sheet 2` 对 `Sheet2`）。
指标：soft = 各指令用例通过率的平均，hard = 全部用例通过的指令占比。上游颜色比较已注释掉，这里同样不比颜色与格式。
"""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import answers, mean, register

SOFFICE = ("soffice", "libreoffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice")


def find_soffice() -> str | None:
    for candidate in [os.environ.get("KNOSIS_SOFFICE", ""), *SOFFICE]:
        if candidate and (shutil.which(candidate) or Path(candidate).is_file()):
            return shutil.which(candidate) or candidate
    return None


def recalc(files, outdir) -> dict[Path, Path]:
    """用 LibreOffice 打开并另存为 xlsx（重算公式、写入缓存值）；返回 {原文件: 重算后的文件}，失败的不在其中。
    每次用独立的用户配置目录，多个进程可以同时跑。"""
    soffice, outdir = find_soffice(), Path(outdir)
    if soffice is None:
        raise RuntimeError("LibreOffice not found (set KNOSIS_SOFFICE); SpreadsheetBench scoring needs it to recalculate formulas")
    out = {}
    with tempfile.TemporaryDirectory() as profile:
        for i, src in enumerate(files):
            target = outdir / str(i)
            target.mkdir(parents=True, exist_ok=True)
            subprocess.run([soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--calc",
                            "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(target), str(src)],
                           capture_output=True, timeout=180)
            made = target / (Path(src).stem + ".xlsx")
            if made.exists():
                out[Path(src)] = made
    return out


def excel_serial(dt) -> float:
    delta = dt - datetime.datetime(1899, 12, 30)
    return delta.days + delta.seconds / 86400.0


def transform(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    if isinstance(v, datetime.datetime):
        return round(excel_serial(v), 0)
    if isinstance(v, datetime.time):
        return str(v)[:-3]
    if isinstance(v, str):
        try:
            return round(float(v), 2)
        except ValueError:
            return v
    return v


def same(a, b) -> bool:
    a, b = transform(a), transform(b)
    if a in ("", None) and b in ("", None):
        return True
    return type(a) is type(b) and a == b


def col_num(name) -> int:
    n = 0
    for c in name:
        n = n * 26 + ord(c) - 64
    return n


def col_name(n) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def cells(rng, max_row=None) -> list[str]:
    """区域 → 单元格名。兼容上游数据里的几种写法：小写列名、全角冒号、整列（`A:G`，行数取 `max_row`）、
    终点缺列名（`BD2:308` 视为同一列）。"""
    rng = rng.upper().replace("：", ":")
    if ":" not in rng:
        return [rng]
    parse = lambda x: ("".join(ch for ch in x if ch.isalpha()), "".join(ch for ch in x if ch.isdigit()))  # noqa: E731
    (c1, r1), (c2, r2) = parse(rng.split(":")[0]), parse(rng.split(":")[1])
    c2, r1, r2 = c2 or c1, int(r1 or 1), int(r2 or max_row or 1)
    return [f"{col_name(c)}{r}" for c in range(col_num(c1), col_num(c2) + 1) for r in range(r1, r2 + 1)]


def regions(position, default_sheet) -> list[tuple[str, str]]:
    """`answer_position` → [(sheet, 区域)]；上游数据里 sheet 名的引号有时只剩一边。"""
    out = []
    for part in position.split(","):
        if "!" in part:
            sheet, rng = part.split("!", 1)
            sheet = sheet.strip().strip("'")
        else:  # 默认取第一个 sheet，名字原样保留（有的 sheet 名带首尾空格）
            sheet, rng = default_sheet, part
        out.append((sheet, rng.strip().strip("'").replace("$", "")))
    return out


def sheet_name(name, names):
    """sheet 名精确匹配；上游有的 answer_position 写的名字与文件不一致（如 `Sheet 2` 对 `Sheet2`），
    精确匹配不到时按去空格、忽略大小写匹配唯一的一个。"""
    if name in names:
        return name
    key = lambda x: x.replace(" ", "").lower()  # noqa: E731
    hits = [n for n in names if key(n) == key(name)]
    return hits[0] if len(hits) == 1 else None


VOLATILE = ("TODAY(", "NOW(")


def volatile(path) -> bool:
    """答案文件里有 TODAY() / NOW()：缓存值是标注当天算的，评测时要与输出在同一天重算才可比。"""
    import openpyxl

    wb = openpyxl.load_workbook(path)
    return any(isinstance(c.value, str) and any(f in c.value.upper() for f in VOLATILE)
               for ws in wb.worksheets for row in ws.iter_rows() for c in row)


def compare(gold_file, proc_file, position) -> tuple[bool, str, str]:
    """(是否一致, 不含正确值的说明, 含正确值的说明)。"""
    import openpyxl

    try:
        gold = openpyxl.load_workbook(gold_file, data_only=True)
        proc = openpyxl.load_workbook(proc_file, data_only=True)
    except Exception as error:  # noqa: BLE001 — 打不开就是错
        return False, f"cannot open output: {type(error).__name__}", f"cannot open output: {error}"
    for sheet, rng in regions(position, gold.sheetnames[0]):
        g, p = sheet_name(sheet, gold.sheetnames), sheet_name(sheet, proc.sheetnames)
        if p is None:
            return False, f"worksheet {sheet!r} not found", f"worksheet {sheet!r} not found"
        if g is None:
            return False, f"answer worksheet {sheet!r} missing upstream", ""
        wg, wp = gold[g], proc[p]
        for name in cells(rng, wg.max_row):
            if not same(wg[name].value, wp[name].value):
                return (False, f"{sheet}!{name} differs (output {wp[name].value!r})",
                        f"{sheet}!{name}: expected {wg[name].value!r}, output {wp[name].value!r}")
    return True, "", ""


def score_cases(task, outputs: dict, scratch) -> list[dict]:
    """`outputs`：{用例号: 输出文件路径或 None}。"""
    given = {n: Path(p) for n, p in outputs.items() if p and Path(p).is_file()}
    golds = [g for g in task.answer if volatile(g)] if given else []
    fixed = recalc(list(given.values()) + golds, scratch) if given else {}
    rows = []
    for n, gold in zip(task.meta["cases"], task.answer):
        src = given.get(n)
        if src is None:
            rows.append({"case": n, "ok": False, "detail": "missing output file", "gold": ""})
            continue
        ok, detail, full = compare(fixed.get(Path(gold), gold), fixed.get(src, src), task.meta["answer_position"])
        if src not in fixed:
            detail += "（LibreOffice 重算失败，按原文件比较）"
        rows.append({"case": n, "ok": ok, "detail": detail, "gold": full})
    return rows


@register("spreadsheetbench")
def score(ws, state, ds, path, ids) -> dict:
    tasks = {t.id: t for t in ds.tasks}
    preds = answers(path) if path and Path(path).exists() else {}
    items, reference = [], []
    with tempfile.TemporaryDirectory() as scratch:
        for i, tid in enumerate(ids):
            task = tasks[tid]
            answer = preds.get(tid) or {}
            outputs = {int(k): (Path(path).parent / v) for k, v in answer.items()} if isinstance(answer, dict) else {}
            rows = score_cases(task, outputs, Path(scratch) / str(i))
            soft = mean(rows, "ok") if rows else 0.0
            items.append({"id": tid, "kind": task.kind, "ok": all(r["ok"] for r in rows) and bool(rows), "soft": soft,
                          "cases": [{k: r[k] for k in ("case", "ok", "detail")} for r in rows],
                          "gold": [{"case": r["case"], "diff": r["gold"]} for r in rows if not r["ok"]]})
            # 参照：原样交回输入表格（有的题答案区本来就有部分正确值）
            reference.append(mean([{"ok": compare(g, p, task.meta["answer_position"])[0]}
                                   for g, p in zip(task.answer, task.meta["inputs"])], "ok"))
    by_kind = {}
    for kind in ("cell", "sheet"):
        rows = [r for r in items if r["kind"] == kind]
        if rows:
            by_kind[kind] = {"n": len(rows), "soft": mean(rows, "soft"), "hard": mean(rows, "ok")}
    return {"metrics": {"soft": mean(items, "soft"), "hard": mean(items, "ok"), "missing": sum(t not in preds for t in ids),
                        "by_kind": by_kind},
            "items": items, "reference": {"unchanged_input": {"soft": sum(reference) / max(1, len(reference))}}}
