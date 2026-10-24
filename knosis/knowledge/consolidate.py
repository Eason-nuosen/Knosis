"""内化：让知识库保持正确、不重复、不自相矛盾、成体系。三步，各由 agent 判断内容，Knosis 检查不变式并留痕。

    knosis knowledge consolidate [--ws <工作区或知识库>] [--steps dedup,conflict,organize]

- dedup 去重：说同一件事的单元合并为一条；被并掉的改为 `status: merged` + `merged_into`，作为别名保留（不删除）。
- conflict 矛盾处理：同一对象上互斥的断言，① 收窄条件，② 用新证据裁决（一方撤回），③ 环境变了按版本处理
  （旧的 stale + `superseded_by`）；暂时无法裁决的双方互记 `conflicts_with` 并标 contested（默认不被选取）。
- organize 构建知识体系：把零散的单跳知识串成「场景 → 数据间关系 → 具体对象」的脉络（`kb/outline.yaml`，只组织、
  不新增断言）；串联中归纳出的上位规律是新断言：`provenance: derived`，`derived_from` 至少两条，从 inferred 起步。

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

STEPS = ("dedup", "conflict", "organize")


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
    before = [i for i in check_knowledge(base, history_ids(base), root=root) if not i.startswith("outline")]
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
    else:
        values["candidates"] = render_candidates(base, step)
    text = Template((TEMPLATES / "consolidate" / f"{step}.md").read_text(encoding="utf-8")).substitute(values)
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
    issues = sorted(set(i for i in current if not i.startswith("outline")) - set(before_issues))
    ids = {u["id"] for u in now}
    issues += [f"{uid}: units must not be deleted (mark merged / retracted / stale instead)"
               for uid in before_units if uid not in ids]
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
    before_issues = [i for i in check_knowledge(base, history_ids(base), root=root) if not i.startswith("outline")]
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
