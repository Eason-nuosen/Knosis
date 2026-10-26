"""内化：让知识库保持正确、不重复、不自相矛盾、成体系。四步，各由 agent 判断内容，Knosis 检查不变式并留痕。

    knosis knowledge consolidate [--ws <工作区或知识库>] [--steps dedup,conflict,organize,structure]

- dedup 去重：说同一件事的单元合并为一条；被并掉的改为 `status: merged` + `merged_into`，作为别名保留（不删除）。
- conflict 矛盾处理：同一对象上互斥的断言，① 收窄条件，② 用新证据裁决（一方撤回），③ 环境变了按版本处理
  （旧的 stale + `superseded_by`）；暂时无法裁决的双方互记 `conflicts_with` 并标 contested（默认不被选取）。
- organize 构建知识体系：把零散的单跳知识串成「场景 → 数据间关系 → 具体对象」的脉络（`kb/outline.yaml`，只组织、
  不新增断言）；串联中归纳出的上位规律是新断言：`provenance: derived`，`derived_from` 至少两条，从 inferred 起步。
- structure 结构化：把同一批知识再组织成知识图谱（`kb/graph.json`，实体与关系）和流程图（`kb/flows/*.json`），
  每条边、每个步骤都引用单元；只组织、不改单元（格式与检查见 `structure`）。

候选（疑似重复、疑似矛盾）由 `candidates` 按内容相似度与共同锚定对象找出，只是提示。
每步验收：知识层检查不新增问题、没有单元被删除，以及该步自己的要求；不通过带着问题重试一次，仍不通过把
`kb/` 与 `evidence/` 恢复到这一步之前。通过后对比前后单元，把操作（合并、撤回、替换、收窄条件、归纳……）
追加到 `evidence/consolidate.jsonl`。
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from .layout import ACTIONS, data_root, layout
from .units import INACTIVE, load_units

STEPS = ("dedup", "conflict", "organize", "structure")
LAYERED = ("outline", "structure")  # 由 organize / structure 维护的部分；其他步骤不为它们的问题负责
GRAPH_COVERAGE, FLOW_COVERAGE = 0.6, 0.6


def min_bridges(n_datasets) -> int:
    return max(4, n_datasets)


def multi_note(base, step) -> str:
    """多个数据集合成的知识库：除了各自的脉络，还要找跨数据集的共通知识。"""
    from . import structure as st

    names = st.namespaces(base)
    if len(names) < 2:
        return ""
    listing = "、".join(f"`{k}/`（{v.get('benchmark')}）" for k, v in names.items())
    if step == "organize":
        return (f"\n## 跨数据集\n\n这个知识库由 {len(names)} 个数据集的知识合成，id 前缀是数据集：{listing}。除了各数据集自己的脉络，"
                "在顶层加一节「跨数据集的共通知识」：找出在多个数据集中都成立的方法、常见的坑与验证原则（例如判断粒度、防止泄漏、"
                "验证覆盖的边界），能归纳的写成归纳单元（`derived_from` 来自至少两个数据集），这一节至少引用三个数据集的单元。\n")
    return (f"\n## 跨数据集\n\n这个知识库由 {len(names)} 个数据集的知识合成，id 前缀是数据集：{listing}。知识图谱除了各数据集的对象，"
            f"还要建**跨数据集的共享实体**（type 用 concept / method / tool 等）：多个数据集里都出现的对象类型、做法、坑或验证原则，"
            f"实体的 `units` 同时引用这些数据集里说了这件事的单元，并用关系（如 applies_to、instance_of、generalizes）连到各数据集的实体。"
            f"至少 {min_bridges(len(names))} 个这样的实体；跨数据集的归纳单元（{', '.join(st.cross_induced(base)) or '目前没有'}）"
            "都要被图谱或流程图引用。\n")


# ------------------------------------------------------------------ 候选


def anchors(unit) -> set[str]:
    """锚定对象：来源里的数据位置与 `about`；只有文件、没有 `#` 位置的锚点太粗，不算。"""
    from .select import anchors as all_anchors

    return {a for a in all_anchors(unit) if "#" in a or not a.startswith("data/")}


def similarity(a, b) -> float:
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return m.ratio() if m.quick_ratio() >= 0.3 else 0.0


def candidates(base, limit=30) -> dict:
    """{"duplicates": [...], "conflicts": [...], "contested": [...]}，每对附相似度与共同锚点。"""
    from .evidence import by_unit, load_evidence

    units = [u for u in load_units(layout(base).units) if u.get("status") not in INACTIVE]
    pairs = []
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            # Knosis 自动生成的 usage 单元文字是同一个模板，评价对象不同就不是重复。
            if a.get("scope") == b.get("scope") == "usage" and a.get("meta", {}).get("of") != b.get("meta", {}).get("of"):
                continue
            shared = sorted(anchors(a) & anchors(b))
            score = similarity(a["content"], b["content"])
            if score >= 0.3 or shared:
                pairs.append({"a": a["id"], "b": b["id"], "similarity": round(score, 2), "shared": shared[:5],
                              "same_kind": (a.get("form"), a.get("scope")) == (b.get("form"), b.get("scope"))})
    dups = [p for p in pairs if p["similarity"] >= 0.6 or (p["similarity"] >= 0.45 and p["shared"] and p["same_kind"])]
    seen = {(p["a"], p["b"]) for p in dups}
    # 可能矛盾：锚定同一对象，或说的是相近的事（内容相似但没到重复）；来源只写工具的知识没有数据锚点，靠后者。
    related = [p for p in pairs if (p["shared"] or p["similarity"] >= 0.35) and (p["a"], p["b"]) not in seen]
    evidence = by_unit(load_evidence(base))
    disputed = [u["id"] for u in units if u.get("status") == "contested" or any(
        e["verdict"] == "refute" for e in evidence.get(u["id"], [])[-1:])]
    by_score = lambda p: (-p["similarity"], -len(p["shared"]))  # noqa: E731
    return {"duplicates": sorted(dups, key=by_score)[:limit], "conflicts": sorted(related, key=by_score)[:limit],
            "contested": disputed[:limit]}


def render_candidates(base, step) -> str:
    found = candidates(base)
    units = {u["id"]: u for u in load_units(layout(base).units)}
    show = lambda uid: f"`{uid}` [{units[uid].get('form')}/{units[uid].get('status')}] {units[uid]['content'][:160]}"  # noqa: E731
    lines = []
    for p in found["duplicates" if step == "dedup" else "conflicts"]:
        lines += [f"- 相似度 {p['similarity']}" + (f"，共同对象 {', '.join(p['shared'])}" if p["shared"] else ""),
                  f"  - {show(p['a'])}", f"  - {show(p['b'])}"]
    if step == "conflict" and found["contested"]:
        lines += ["", "有争议或最近一条证据为反驳的单元：", *[f"- {show(uid)}" for uid in found["contested"]]]
    return "\n".join(lines) or "（没有找到候选；仍可自己浏览知识库）"


# ------------------------------------------------------------------ 提示与验收


def resolve_base(path) -> tuple[Path, Path | None]:
    """（知识层根，数据根）：工作区两者相同；知识库没有数据根。"""
    path = Path(path).resolve()
    return path, data_root(path)


def history_ids(base) -> set[str]:
    from ..workspace import snapshots

    return {u["id"] for d in snapshots(base) for u in load_units(layout(d).units)} if data_root(base) else set()


def prompt(path, step) -> str:
    from . import check_knowledge
    from . import outline as ol
    from ..workspace import TEMPLATES

    base, root = resolve_base(path)
    lay = layout(base)
    before = [i for i in check_knowledge(base, history_ids(base), root=root) if not i.startswith(LAYERED)]
    note = ("（以下是整理前就有的问题，与本任务无关，可以保留：" + "；".join(before[:10]) + "）") if before else ""
    units = load_units(lay.units)
    values = {"base": base, "check_note": note, "n_units": sum(u.get("status") not in INACTIVE for u in units),
              "n_inactive": sum(u.get("status") in INACTIVE for u in units),
              "verify": ("可以查 `data/`、用工具或 `knosis knowledge verify` 取得新证据。" if root else
                         "知识库没有数据，只能依据已有证据与 `evidence/traces/` 里的轨迹判断；判断不了就标 contested。")}
    if step == "organize":
        items = ol.members(base)
        draft = ol.write_outline(base, ol.draft(base), "outline.draft.yaml")
        values |= {"draft": draft, "n_skills": sum(1 for i in items.values() if i.get("form") == "skill"),
                   "existing": ("已有大纲 `kb/outline.yaml`：在它的基础上更新，保留合理的结构，把「未归类」的新知识放进去，"
                                f"必要时拆分或合并节（`knosis knowledge outline --ws {base}` 看当前大纲与未归类单元）。"
                                if ol.load_outline(base) is not None else "还没有大纲，从草稿出发。")}
    elif step == "structure":
        from . import structure as st

        cov = st.coverage(base)
        values |= {"summary": st.summary(base), "graph_cov": f"{GRAPH_COVERAGE:.0%}", "flow_cov": f"{FLOW_COVERAGE:.0%}",
                   "n_objects": cov["objects"], "n_procedural": cov["procedural"],
                   "existing": ("已有知识图谱 / 流程图：在它们的基础上更新（补上新单元，去掉对已失效单元的引用），保留合理的结构。"
                                if st.graph_path(base).exists() else "还没有知识图谱与流程图，从头建。")}
    else:
        values["candidates"] = render_candidates(base, step)
    text = Template((TEMPLATES / "consolidate" / f"{step}.md").read_text(encoding="utf-8")).substitute(values)
    text += multi_note(base, step) if step in ("organize", "structure") else ""
    if root:
        text += ("\n内化由运行器验收并保存知识版本：不要运行 `knosis ws check`、`knosis ws goto`，不要切换阶段，"
                 "也不要写阶段目录里的 changelog。\n")
    return text


def step_issues(path, step, before_units, before_issues) -> list[str]:
    from . import check_knowledge
    from . import outline as ol

    base, root = resolve_base(path)
    now = load_units(layout(base).units)
    current = check_knowledge(base, history_ids(base), root=root)
    issues = sorted(set(i for i in current if not i.startswith(LAYERED)) - set(before_issues))
    ids = {u["id"] for u in now}
    issues += [f"{uid}: units must not be deleted (mark merged / retracted / stale instead)"
               for uid in before_units if uid not in ids]
    if step == "structure":
        from . import structure as st

        old = {uid: json.dumps(u, sort_keys=True, ensure_ascii=False) for uid, u in before_units.items()}
        issues += [f"{u['id']}: structure must not change units" for u in now
                   if old.get(u["id"]) != json.dumps(u, sort_keys=True, ensure_ascii=False)]
        if not st.graph_path(base).exists():
            issues.append(f"missing {st.graph_path(base)}")
        issues += [i for i in current if i.startswith("structure")]
        cov = st.coverage(base)
        if cov["objects"] and cov["graph"] < GRAPH_COVERAGE:
            issues.append(f"structure graph: cites {cov['graph']:.0%} of {cov['objects']} active object units; need {GRAPH_COVERAGE:.0%}")
        if cov["procedural"] and cov["n_flows"] == 0:
            issues.append("structure flows: the knowledge base has procedure / method units or skills but no flow")
        elif cov["procedural"] and cov["flows"] < FLOW_COVERAGE:
            issues.append(f"structure flows: cite {cov['flows']:.0%} of {cov['procedural']} procedure / method units and skills; need {FLOW_COVERAGE:.0%}")
        if cov.get("datasets", 0) >= 2:
            if cov["bridges"] < min_bridges(cov["datasets"]):
                issues.append(f"structure graph: {cov['bridges']} entities cite units from two or more datasets; need {min_bridges(cov['datasets'])}")
            missing = [u for u in st.cross_induced(base) if u not in st.cited(base)]
            issues += [f"structure: cross-dataset unit {u} is cited by neither the graph nor a flow" for u in missing]
    if step == "organize":
        outline = ol.load_outline(base)
        if outline is None:
            issues.append(f"missing {layout(base).outline}")
        else:
            left = ol.unplaced(outline, ol.members(base))
            issues += [i for i in current if i.startswith("outline")]
            issues += [f"outline: {len(left)} active units not placed: {', '.join(left[:20])}"] if left else []
        for unit in now:
            if unit["id"] in before_units:
                continue
            if unit.get("provenance", "").strip() != "derived" or len(unit.get("derived_from", [])) < 2:
                issues.append(f"{unit['id']}: induced units need provenance derived and at least two derived_from")
    return issues


# ------------------------------------------------------------------ 留痕


def actions(before: dict, after: dict, step) -> list[dict]:
    """对比内化前后的单元，得出操作记录。"""
    out = []
    for uid, unit in after.items():
        old = before.get(uid)
        if old is None:
            out.append({"op": "induce" if unit.get("derived_from") else "add", "unit": uid,
                        "from": unit.get("derived_from", [])})
            continue
        if unit.get("merged_into") and not old.get("merged_into"):
            out.append({"op": "merge", "unit": uid, "into": unit["merged_into"]})
        elif unit.get("superseded_by") and not old.get("superseded_by"):
            out.append({"op": "supersede", "unit": uid, "by": unit["superseded_by"]})
        elif unit.get("status") != old.get("status"):
            out.append({"op": "status", "unit": uid, "from": old.get("status"), "to": unit.get("status")})
        if set(unit.get("conflicts_with", [])) != set(old.get("conflicts_with", [])):
            out.append({"op": "conflict", "unit": uid, "with": unit.get("conflicts_with", [])})
        if unit.get("condition") != old.get("condition"):
            out.append({"op": "narrow" if step == "conflict" else "condition", "unit": uid})
        if unit.get("content") != old.get("content") and not unit.get("merged_into"):
            out.append({"op": "rewrite", "unit": uid})
    now = datetime.now(timezone.utc).isoformat()
    return [{"step": step, **a, "created": now} for a in out]


def log_actions(base, entries) -> None:
    if entries:
        path = Path(base) / ACTIONS
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)


# ------------------------------------------------------------------ 运行


def backup(base, tmp) -> None:
    for part in ("kb", "evidence"):
        if (Path(base) / part).exists():
            shutil.copytree(Path(base) / part, Path(tmp) / part, ignore=shutil.ignore_patterns("__pycache__"))


def restore(base, tmp) -> None:
    for part in ("kb", "evidence"):
        shutil.rmtree(Path(base) / part, ignore_errors=True)
        if (Path(tmp) / part).exists():
            shutil.copytree(Path(tmp) / part, Path(base) / part)


def run_step(path, step, agent="codex", model=None, effort=None) -> dict:
    from ..workspace.driver import agent_command
    from . import check_knowledge

    base, root = resolve_base(path)
    lay = layout(base)
    before = {u["id"]: u for u in load_units(lay.units)}
    before_issues = [i for i in check_knowledge(base, history_ids(base), root=root) if not i.startswith(LAYERED)]
    text, issues, started = prompt(base, step), [], time.monotonic()
    env = {**os.environ, "KNOSIS_DEPTH": "1"}
    with tempfile.TemporaryDirectory() as tmp:
        backup(base, tmp)
        for attempt in range(2):
            with (lay.kb / "consolidate.log").open("a", encoding="utf-8") as log:
                log.write(f"\n===== {step} attempt {attempt + 1} =====\n")
                log.flush()
                result = subprocess.run(agent_command(agent, base, text, model, effort), cwd=base, env=env,
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            issues = [f"{agent} exited with {result.returncode}"] if result.returncode else \
                step_issues(base, step, before, before_issues)
            if not issues:
                break
            text += "\n验收未通过，请修正：\n" + "\n".join(issues)
        if issues:
            restore(base, tmp)
            return {"step": step, "issues": issues, "restored": True, "seconds": round(time.monotonic() - started)}
    after = {u["id"]: u for u in load_units(lay.units)}
    done = actions(before, after, step)
    if step == "structure":
        from .structure import coverage

        done.append({"step": step, "op": "structure", **coverage(base), "created": datetime.now(timezone.utc).isoformat()})
    log_actions(base, done)
    ops = {}
    for a in done:
        ops[a["op"]] = ops.get(a["op"], 0) + 1
    return {"step": step, "issues": [], "actions": ops, "seconds": round(time.monotonic() - started)}


def run(path, steps=STEPS, agent="codex", model=None, effort=None) -> list[dict]:
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
    results = []
    for step in steps:
        if step not in STEPS:
            raise ValueError(f"unknown step: {step}; choose from {', '.join(STEPS)}")
        results.append(run_step(path, step, agent, model, effort))
        print(json.dumps(results[-1], ensure_ascii=False))
    return results
