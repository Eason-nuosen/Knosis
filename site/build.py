"""Export demo workspaces to site/data.js for the Demo page of index.html.

One showcase case per data type (`case: True`): knowledge graph, flowcharts, derivation graph, rule / formula cards, outline, and one task's
full chain (task → knowledge used → result, from used_units and eval.json); the other benchmarks go under "more results". Also exports the atlas:
the knowledge graph obtained by merging each case's knowledge base into `ws/kb-atlas` with dataset prefixes and then consolidating (`--atlas`).

Usage: python site/build.py [--ws ws] [--atlas ws/kb-atlas]
Workspaces are not committed, so data.js must be regenerated on a machine that has ws/. Each demo's results table is filled from eval.json;
highlights are hand-written observations (site/notes.yaml). Numbers come only from local workspaces: single runs, very few tasks.
"""
import argparse
import json
from pathlib import Path

import yaml

from knosis.knowledge import layout, load_evidence, load_units, ontology_docs, scope_of
from knosis.knowledge import structure as st
from knosis.knowledge.skills import load_skills

ROOT = Path(__file__).resolve().parent.parent

# One demo per benchmark (2026-10-24, v0.5: explore → extract → refine ×2 → consolidate → decide, Codex gpt-6.1-sol / medium)
DEMOS = [
    {"key": "ngd", "dir": "v05-ngd", "modality": "噪声知识图谱", "title": "NGDBench NGD-Fin：含噪金融图问答",
     "task": "图里注入了节点类型、属性、边的噪声；人工核对的演示题集，dev 10 / 测试 20，dev 给正确答案作反馈，每次须答全部 dev 题。",
     "metrics": [("answer_set_em", "测试 EM"), ("answer_set_f1", "测试 F1"), ("em_noise_affected", "受噪声影响题 EM")]},
    {"key": "tab", "dir": "v05-tab", "modality": "单表", "title": "TabArena healthcare_insurance_expenses：医疗费用回归",
     "task": "回归医疗费用（训练 792 行、留 100 行作 dev、测试 446 行）；agent 可用 TabPFN 等工具。",
     "metrics": [("rmse", "RMSE"), ("mae", "MAE"), ("r2", "R²")]},
    {"key": "rel", "dir": "v05-rel", "modality": "多表 / 关系库", "title": "RelBench rel-f1 driver-top3：车手是否进前三",
     "task": "F1 多表关系库，按时间截断防泄漏；预测车手下一场是否进前三，val 划分作 dev。",
     "metrics": [("roc_auc", "AUROC")]},
    {"key": "bi", "dir": "v05-bi", "modality": "多表 + 本体", "title": "BI-Bench 项目 149612320：学校 BI 问答",
     "task": "多张 CSV 表上回答 BI 问题；agent 自己检验主键、包含依赖与粒度，可写成 OSI 本体。dev 1 / 测试 2。",
     "metrics": [("success", "测试成功率")]},
    {"key": "krama", "dir": "v05-krama", "modality": "多表 / 数据湖", "title": "KramaBench archeology：考古数据湖问答",
     "task": "考古数据湖上的数值问答，dev 3 / 测试 9。",
     "metrics": [("accuracy", "测试准确率")]},
    {"key": "burr", "dir": "v05-burr", "modality": "映射", "title": "Burr micro/basic：关系表 → 本体映射",
     "task": "Burr 的 basic 类 micro 场景：从关系表推断类、关系与属性映射，dev 约 1/4。",
     "metrics": [("mapping_based_cls_f1", "类 F1"), ("mapping_based_rel_f1", "关系 F1"), ("mapping_based_attr_f1", "属性 F1")]},
    {"key": "sr", "dir": "v05-sr", "modality": "方程", "title": "LLM-SRBench lsr_synth_matsci：材料科学符号回归",
     "task": "从数据点恢复方程，dev 2 / 测试 3，报告 NMSE 与 Acc₀.₁（含分布外）。",
     "metrics": [("acc_0.1", "测试 Acc₀.₁"), ("ood_acc_0.1", "OOD Acc₀.₁"), ("nmse_median", "NMSE 中位数")]},
    {"key": "newton", "dir": "v05-newton", "modality": "模拟器", "title": "NewtonBench m0_gravity：做实验发现定律",
     "task": "只能用 newton 工具做受控实验（GT 只在工具进程里），推断改写过的引力定律。dev 2 组 / 测试 4 组。",
     "metrics": [("ok_rate", "测试正确率"), ("rmsle_median", "RMSLE 中位数")]},
    {"key": "alpha", "dir": "v05-alpha", "modality": "时序", "title": "AlphaBench evaluate：A 股因子判断",
     "task": "给评估窗口之前的 CSI300 行情，判断因子信号与 IC；dev 10 / 测试 30。",
     "metrics": [("signal_accuracy", "信号准确率"), ("mean_ic_mae", "IC MAE"), ("mean_rankic_spearman", "RankIC Spearman")]},
    {"key": "sheet", "dir": "v05-sheet", "modality": "电子表格", "title": "SpreadsheetBench：真实论坛表格操作",
     "task": "Excel 论坛真实求助改写的指令，每条 3 个测试用例（同类表格、数据不同），交回改好的 xlsx；评测前 LibreOffice 重算公式。按指令切分 dev 5 / 测试 15。",
     "metrics": [("soft", "soft（用例通过率）"), ("hard", "hard（3 例全对）")]},
    {"key": "text", "dir": "v05-text", "modality": "文本", "title": "text：从 Knosis 自己的文档构造知识",
     "task": "语料是 Knosis 仓库 docs/ 下的 8 份设计文档，没有下游题目，只评知识层本身（来源能否定位回原文）。",
     "metrics": [("units", "知识单元"), ("span_resolvable", "来源可定位率"), ("quote_supported", "引文核对通过率")]},
    {"key": "appworld", "dir": "trace-appworld", "modality": "agent 轨迹", "title": "AppWorld 轨迹：从 agent 运行记录提取环境知识",
     "task": "6 条 AppWorld（Spotify 应用）ReAct 轨迹，统一成 ATIF；没有下游题目，从轨迹里提取关于 API 与数据的知识，引用到具体步骤。",
     "metrics": [("units", "知识单元"), ("cites_trace", "引用有效步骤"), ("trace_checked", "已与轨迹核对")]},
]
# showcase case per data type; the rest are "more results"
CASES = ["ngd", "tab", "bi", "newton", "burr", "alpha", "sheet", "text", "appworld"]
TEXT_FIELDS = ("question", "instruction", "expression", "signature", "factor", "files")

NOTES_FILE = Path(__file__).with_name("notes.yaml")


def jsonl(path):
    path = Path(path)
    return load_units(path) if path.exists() else []


def eob(item):
    for ext in item.get("custom_extensions") or []:
        if ext.get("vendor_name") == "EOB":
            try:
                return json.loads(ext["data"])
            except (TypeError, ValueError):
                return {}
    return {}


def ontology(base):
    docs = ontology_docs(base)
    if not docs:
        return None
    out = {"concepts": [], "datasets": [], "relationships": []}
    for doc in docs.values():
        for c in (doc.get("ontology") or {}).get("ontology") or []:
            out["concepts"].append({k: c.get(k) for k in ("concept", "type", "description")})
        model = doc.get("semantic_model") or {}
        for d in model.get("datasets") or []:
            out["datasets"].append({"name": d.get("name"), "primary_key": d.get("primary_key"),
                                    "fields": [x.get("name") for x in d.get("fields") or []]})
        for r in model.get("relationships") or []:
            data = eob(r)
            out["relationships"].append({"name": r.get("name"), "from": r.get("from"), "to": r.get("to"),
                                         "from_columns": r.get("from_columns"), "to_columns": r.get("to_columns"),
                                         "cardinality": data.get("cardinality"), "condition": data.get("condition")})
    return out


def feedback(base):
    out = []
    for f in sorted(layout(base).feedback.glob("*.json")):
        rec = json.loads(f.read_text())
        metrics, items = rec.get("metrics") or {}, rec.get("items") or []
        main = next(((k, v) for k, v in metrics.items() if isinstance(v, (int, float)) and k not in ("missing", "n")
                     and not k.startswith("n_")), (None, None))
        out.append({"id": rec.get("id"), "stage": rec.get("stage"), "round": rec.get("round"), "mode": rec.get("mode"),
                    "metric": main[0], "value": main[1], "n": len(items), "ok": sum(1 for i in items if i.get("ok"))})
    return out


def checks(base, units):
    out = [{"unit": u["id"], "kind": "sql", "file": None} for u in units
           if isinstance(u.get("check"), dict) and u["check"].get("kind") == "sql"]
    used = {}
    for u in units:
        if isinstance(u.get("check"), dict) and u["check"].get("path"):
            used.setdefault(Path(u["check"]["path"]).name, []).append(u["id"])
    for f in sorted(layout(base).checks.glob("*.py")):
        for uid in used.get(f.name, [None]):
            out.append({"unit": uid, "kind": "python", "file": f.name})
    return out


def fmt(v):
    if isinstance(v, float):
        return f"{v:.3g}" if v and abs(v) < 1e-3 else f"{v:.3f}".rstrip("0").rstrip(".")
    return str(v)


def scalars(report, keys):
    """The requested metrics from eval.json (top level or the metrics section); missing ones are skipped."""
    flat = {**report, **(report.get("metrics") or {})}
    return [[label, fmt(flat[k])] for k, label in keys if isinstance(flat.get(k), (int, float))]


def runtime(base):
    runs = jsonl(Path(base) / ".knosis/runs.jsonl")
    return {"minutes": round(sum(r.get("seconds", 0) for r in runs) / 60, 1),
            "consolidate": [{k: r.get(k) for k in ("step", "issues", "actions", "seconds")}
                            for r in runs if r.get("stage") == "consolidate"]}


def task_text(task):
    for k in TEXT_FIELDS:
        if task.get(k):
            v = task[k]
            return v if isinstance(v, str) else ", ".join(map(str, v))
    return str(task.get("id"))


def short(v, n=360):
    text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + " …"


def case(ws, report, graph_units):
    """Full chain of one task: among correct tasks using 2 to 10 units, the one whose units the knowledge graph cites most; without per-task correctness, the one with the smallest error."""
    ws = Path(ws)
    tasks = {str(t["id"]): t for t in jsonl(ws / "tasks/tasks.jsonl")}
    used = {str(r["id"]): r.get("used_units", []) for r in jsonl(ws / "stages/4_decide/used_units.jsonl")}
    items = {str(i["id"]): i for i in report.get("items", [])}
    if not tasks or not used:
        return None
    preds = {str(r["id"]): r.get("answer") for r in jsonl(ws / "stages/4_decide/predictions.jsonl")}
    pool = [t for t in used if t in tasks and 2 <= len(used[t]) <= 12]
    if any(items.get(t, {}).get("ok") for t in pool):
        pool = [t for t in pool if items.get(t, {}).get("ok")]
        best = max(pool, key=lambda t: (sum(u in graph_units for u in used[t]), -abs(len(used[t]) - 6)))
    elif any("error" in items.get(t, {}) for t in pool):
        best = min(pool, key=lambda t: abs(items[t].get("error") or 1e9))
    else:
        return None
    item = items.get(best, {})
    return {"id": best, "text": short(task_text(tasks[best]), 600), "answer": short(preds.get(best), 400),
            "ok": item.get("ok"), "error": item.get("error"), "used": used[best]}


def unit_story(units, evidence, graph_units):
    """Without tasks: the verified unit cited by the knowledge graph with the most evidence, along with its provenance and evidence."""
    count = {}
    for e in evidence:
        count[e["unit"]] = count.get(e["unit"], 0) + (e["verdict"] == "support")
    pool = [u for u in units if u.get("status") == "verified" and u["id"] in graph_units] or \
           [u for u in units if u.get("status") == "verified"]
    if not pool:
        return None
    best = max(pool, key=lambda u: (count.get(u["id"], 0), len(u.get("derived_from", []))))
    return {"unit": best["id"]}


def structure(base):
    graph = st.load_graph(base)
    return {"graph": graph, "flows": st.load_flows(base) if st.flows_dir(base).is_dir() else [],
            "derivation": st.derivation(base), "cards": st.cards(base), "coverage": st.coverage(base)}


def atlas(path):
    """Atlas: entities colored by the dataset prefix of the units citing them; entities cited by units from several datasets are "bridges"."""
    path = Path(path)
    graph = st.load_graph(path) if path.exists() else None
    if not graph:
        return None
    units = {u["id"]: u for u in jsonl(layout(path).units)}
    ns = st.unit_namespaces(path)
    for e in graph["entities"]:
        own = set().union(*[ns.get(u, set()) for u in e.get("units", [])] or [set()])
        near = set().union(*[ns.get(u, set()) for r in graph["relations"] if e["id"] in (r["src"], r["dst"])
                             for u in r.get("units", [])] or [set()])
        e["datasets"] = sorted(own or near)  # a bridge only if its own cited units span two or more datasets; without own citations, colored by its neighbors
        e["bridge"] = len(own) >= 2
    brief = {uid: {k: u.get(k) for k in ("content", "form", "status", "scope")} for uid, u in units.items()}
    return {"graph": graph, "units": brief, "flows": st.load_flows(path) if st.flows_dir(path).is_dir() else [],
            "coverage": st.coverage(path), "merged": sum(u.get("status") == "merged" for u in units.values()),
            "induced": [{"id": uid, "content": units[uid]["content"], "datasets": sorted(ns.get(uid, ()))}
                        for uid in st.cross_induced(path)]}


def load(base, traces=None):
    lay = layout(base)
    units = [{**u, "scope": scope_of(u), "scope_inferred": "scope" not in u,
              "level": "meta" if scope_of(u) in ("method", "usage") else "object"} for u in jsonl(lay.units)]
    evidence = [{k: e.get(k) for k in ("id", "unit", "verdict", "method", "source", "note", "created", "inherited")}
                for e in load_evidence(base)]
    skills = [{k: v for k, v in s.items() if k != "path"} for s in load_skills(base)]
    outline = yaml.safe_load(lay.outline.read_text()) if lay.outline.exists() else None
    trace_dir = traces if traces is not None and traces.is_dir() else lay.traces
    return {"units": units, "evidence": evidence, "skills": skills, "outline": outline, "ontology": ontology(base),
            "feedback": feedback(base), "checks": checks(base, units), "actions": jsonl(lay.actions),
            "traces": sorted(p.name for p in trace_dir.glob("*.json")) if trace_dir.is_dir() else []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=str(ROOT / "ws"))
    ap.add_argument("--atlas", default=str(ROOT / "ws/kb-atlas"))
    ap.add_argument("--translate", action="store_true", help="translate Chinese text missing from the cache with Codex (for the English version)")
    args = ap.parse_args()
    notes = yaml.safe_load(NOTES_FILE.read_text()) if NOTES_FILE.exists() else {}
    out = []
    for demo in DEMOS:
        meta = {k: v for k, v in demo.items() if k not in ("dir", "metrics")}
        ws = Path(args.ws) / demo["dir"]
        if not (ws / ".knosis/state.json").exists():
            print(f"skip {demo['key']}: {ws} missing")
            continue
        state = json.loads((ws / ".knosis/state.json").read_text())
        ev = ws / ".knosis/eval.json"
        report = json.loads(ev.read_text()) if ev.exists() else {}
        rows = scalars(report, demo["metrics"])
        data = load(ws, traces=ws / "data/traces") | {
            "state": {k: state.get(k) for k in ("benchmark", "scenario", "options", "created", "completed")},
            "results": {"cols": ["指标", "K_final"], "rows": rows} if rows else None,
            "runtime": runtime(ws)} | structure(ws)
        graph_units = st.cited(ws)
        data["case"] = case(ws, report, graph_units) or unit_story(data["units"], data["evidence"], graph_units)
        out.append({**meta, "is_case": demo["key"] in CASES, "highlights": notes.get(demo["key"], []), **data})
        print(f"{demo['key']:6} units={len(data['units'])} evidence={len(data['evidence'])} skills={len(data['skills'])}"
              f" actions={len(data['actions'])} outline={'y' if data['outline'] else 'n'}"
              f" results={len(data['results']['rows']) if data.get('results') else 0}"
              f" graph={data['coverage']['entities']}/{data['coverage']['relations']} flows={data['coverage']['n_flows']}"
              f" case={(data.get('case') or {}).get('id') or (data.get('case') or {}).get('unit')}")
    big = atlas(args.atlas)
    print(f"atlas: {big['coverage'] if big else 'missing'}")
    import translate

    strings = translate.collect(out, big)
    en = translate.translate(strings) if args.translate else {k: v for k, v in translate.load_cache().items() if k in set(strings)}
    print(f"english: {len(en)}/{len(strings)} strings translated")
    target = Path(__file__).with_name("data.js")
    text = ("window.KNOSIS_DEMOS = " + json.dumps(out, ensure_ascii=False, default=str) + ";\n"
            + "window.KNOSIS_ATLAS = " + json.dumps(big, ensure_ascii=False, default=str) + ";\n"
            + "window.KNOSIS_EN = " + json.dumps(en, ensure_ascii=False) + ";\n")
    # The page is public: local absolute paths become repo-relative, and the home directory is written as ~.
    target.write_text(text.replace(f"{ROOT}/", "").replace(str(ROOT), ".").replace(str(Path.home()), "~"))
    print(f"wrote {target} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
