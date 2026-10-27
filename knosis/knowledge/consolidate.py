"""Consolidation: keep the knowledge base correct, non-duplicated, non-contradictory and organized. Four steps; the agent judges content
in each, Knosis checks invariants and keeps a log.

    knosis knowledge consolidate [--ws <workspace or knowledge base>] [--steps dedup,conflict,organize,structure]
    knosis knowledge compact [--ws <workspace or knowledge base>] [--topic <topic>]

- dedup: units saying the same thing are merged into one; the absorbed ones become `status: merged` + `merged_into`, kept as aliases (not deleted).
- conflict: mutually exclusive assertions on the same object are (1) narrowed by condition, (2) decided by new evidence (one side retracted), or
  (3) versioned if the environment changed (old one stale + `superseded_by`); pairs that cannot be decided yet record each other in
  `conflicts_with` and are marked contested (not selected by default).
- organize: link scattered single-hop knowledge into a "scenario -> relations between data -> specific objects" hierarchy (`kb/outline.yaml`,
  organizes only, adds no assertions); higher-level patterns induced along the way are new assertions: `provenance: derived`, at least two
  `derived_from`, starting as inferred.
- structure: organize the same knowledge into a knowledge graph (`kb/graph.json`, entities and relations) and flowcharts (`kb/flows/*.json`),
  each edge and step citing units; organizes only, does not change units (format and checks: `structure`).
- compact (not a default step; run on its own as the knowledge base grows): the agent decides which units can be stated together; the rest of
  each group merge into the main unit (merged, kept as aliases); the active unit count must drop and every inactive unit must point to an
  active one. With `topic`, only units related to the topic are compacted: Knosis lists units matching the topic terms, the agent finds the rest.

Candidates (suspected duplicates and conflicts) come from `candidates` by content similarity and shared anchors; they are only hints.
Acceptance per step: no new knowledge-layer issues, no units deleted, plus the step's own requirements; on failure retry once with the issues,
and if it still fails restore `kb/` and `evidence/` to before the step. On success, diff units before and after and append the operations
(merge, retract, supersede, narrow condition, induce, ...) to `evidence/consolidate.jsonl`.
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

from ..lang import t
from .layout import ACTIONS, data_root, layout
from .units import INACTIVE, load_units, resolve

STEPS = ("dedup", "conflict", "organize", "structure")
EXTRA = ("compact",)  # not a default step
LAYERED = ("outline", "structure")  # maintained by organize / structure; other steps are not responsible for their issues
GRAPH_COVERAGE, FLOW_COVERAGE = 0.6, 0.6


def min_bridges(n_datasets) -> int:
    return max(4, n_datasets)


def multi_note(base, step) -> str:
    """A knowledge base merged from several datasets: besides each one's hierarchy, look for knowledge shared across datasets."""
    from . import structure as st

    names = st.namespaces(base)
    if len(names) < 2:
        return ""
    listing = t(", ".join(f"`{k}/` ({v.get('benchmark')})" for k, v in names.items()),
                "、".join(f"`{k}/`（{v.get('benchmark')}）" for k, v in names.items()))
    if step == "organize":
        return t(f"\n## Across datasets\n\nThis knowledge base combines knowledge from {len(names)} datasets; the id prefix is the dataset: {listing}. "
                 "Besides each dataset's own hierarchy, add a top-level section \"Knowledge shared across datasets\": find methods, common pitfalls and "
                 "verification principles that hold in several datasets (e.g. judging granularity, preventing leakage, the limits of verification coverage), "
                 "write those that can be induced as induced units (`derived_from` from at least two datasets); this section cites units from at least "
                 "three datasets.\n",
                 f"\n## 跨数据集\n\n这个知识库由 {len(names)} 个数据集的知识合成，id 前缀是数据集：{listing}。除了各数据集自己的脉络，"
                 "在顶层加一节「跨数据集的共通知识」：找出在多个数据集中都成立的方法、常见的坑与验证原则（例如判断粒度、防止泄漏、"
                 "验证覆盖的边界），能归纳的写成归纳单元（`derived_from` 来自至少两个数据集），这一节至少引用三个数据集的单元。\n")
    induced = ', '.join(st.cross_induced(base))
    return t(f"\n## Across datasets\n\nThis knowledge base combines knowledge from {len(names)} datasets; the id prefix is the dataset: {listing}. "
             f"Besides each dataset's objects, the knowledge graph must also contain **entities shared across datasets** (type concept / method / tool etc.): "
             f"object types, practices, pitfalls or verification principles that appear in several datasets; the entity's `units` cite the units in each of "
             f"these datasets that say this, and relations (e.g. applies_to, instance_of, generalizes) connect it to each dataset's entities. "
             f"At least {min_bridges(len(names))} such entities; the cross-dataset induced units ({induced or 'none yet'}) "
             "must all be cited by the graph or a flowchart.\n",
             f"\n## 跨数据集\n\n这个知识库由 {len(names)} 个数据集的知识合成，id 前缀是数据集：{listing}。知识图谱除了各数据集的对象，"
             f"还要建**跨数据集的共享实体**（type 用 concept / method / tool 等）：多个数据集里都出现的对象类型、做法、坑或验证原则，"
             f"实体的 `units` 同时引用这些数据集里说了这件事的单元，并用关系（如 applies_to、instance_of、generalizes）连到各数据集的实体。"
             f"至少 {min_bridges(len(names))} 个这样的实体；跨数据集的归纳单元（{induced or '目前没有'}）"
             "都要被图谱或流程图引用。\n")


# ------------------------------------------------------------------ candidates


def anchors(unit) -> set[str]:
    """Anchors: data locations in provenance and `about`; file-only anchors without a `#` location are too coarse and do not count."""
    from .select import anchors as all_anchors

    return {a for a in all_anchors(unit) if "#" in a or not a.startswith("data/")}


def similarity(a, b) -> float:
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return m.ratio() if m.quick_ratio() >= 0.3 else 0.0


def candidates(base, limit=30) -> dict:
    """{"duplicates": [...], "conflicts": [...], "contested": [...]}, each pair with similarity and shared anchors."""
    from .evidence import by_unit, load_evidence

    units = [u for u in load_units(layout(base).units) if u.get("status") not in INACTIVE]
    pairs = []
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            # Knosis-generated usage units share one text template; different targets mean they are not duplicates.
            if a.get("scope") == b.get("scope") == "usage" and a.get("meta", {}).get("of") != b.get("meta", {}).get("of"):
                continue
            shared = sorted(anchors(a) & anchors(b))
            score = similarity(a["content"], b["content"])
            if score >= 0.3 or shared:
                pairs.append({"a": a["id"], "b": b["id"], "similarity": round(score, 2), "shared": shared[:5],
                              "same_kind": (a.get("form"), a.get("scope")) == (b.get("form"), b.get("scope"))})
    dups = [p for p in pairs if p["similarity"] >= 0.6 or (p["similarity"] >= 0.45 and p["shared"] and p["same_kind"])]
    seen = {(p["a"], p["b"]) for p in dups}
    # Possible conflicts: same anchored object, or similar claims (similar content short of duplicate); tool-only provenance has no data anchors and relies on the latter.
    related = [p for p in pairs if (p["shared"] or p["similarity"] >= 0.35) and (p["a"], p["b"]) not in seen]
    evidence = by_unit(load_evidence(base))
    disputed = [u["id"] for u in units if u.get("status") == "contested" or any(
        e["verdict"] == "refute" for e in evidence.get(u["id"], [])[-1:])]
    by_score = lambda p: (-p["similarity"], -len(p["shared"]))  # noqa: E731
    return {"duplicates": sorted(dups, key=by_score)[:limit], "conflicts": sorted(related, key=by_score)[:limit],
            "contested": disputed[:limit]}


def topic_terms(topic) -> list[str]:
    """Topic terms: the whole phrase plus the pieces split on whitespace and commas (Chinese topics often lack spaces, so the whole phrase is a term too)."""
    import re

    parts = [t for t in re.split(r"[\s,，、;；]+", topic.strip()) if len(t) >= 2]
    return list(dict.fromkeys([topic.strip(), *parts]))


def topic_units(base, topic) -> list[dict]:
    """Active units related to the topic, sorted by number of matched terms; only a starting point, the agent must find the rest."""
    terms = [t.lower() for t in topic_terms(topic)]
    hits = []
    for u in load_units(layout(base).units):
        if u.get("status") in INACTIVE:
            continue
        blob = " ".join(str(u.get(k, "")) for k in ("id", "content", "condition", "about", "provenance")).lower()
        n = sum(t in blob for t in terms)
        if n:
            hits.append((n, u))
    return [u for _, u in sorted(hits, key=lambda h: -h[0])]


def render_unit(u) -> str:
    return f"- `{u['id']}` [{u.get('form')}/{u.get('scope', '')}/{u.get('status')}] {u['content'][:200]}"


def compact_values(base, topic=None) -> dict:
    units = [u for u in load_units(layout(base).units) if u.get("status") not in INACTIVE]
    if topic:
        found = topic_units(base, topic)
        listing = "\n".join(render_unit(u) for u in found[:80]) or t(
            "(no unit directly matches the topic terms; use select with a few other phrasings)",
            "（主题词没有直接命中的单元；用 select 换几个说法再找）")
        return {"goal": t(f"Compact the knowledge related to the topic \"{topic}\" into fewer, more general units; leave other knowledge untouched.",
                          f"把与主题「{topic}」有关的知识压缩成更少、更概括的单元，其余知识不动。"),
                "scope": t(f"Topic: **{topic}**. {len(found)} active units directly match the topic terms ({', '.join(topic_terms(topic))})"
                           f"{' (only the first 80 listed)' if len(found) > 80 else ''}:\n\n{listing}\n\n"
                           "The topic terms are only a literal match: first judge which units are really related to the topic (synonymous phrasings and "
                           "related objects count too), drop the unrelated ones, then add the ones that were missed.",
                           f"主题：**{topic}**。主题词（{'、'.join(topic_terms(topic))}）直接命中的活跃单元 {len(found)} 条"
                           f"{'（只列前 80 条）' if len(found) > 80 else ''}：\n\n{listing}\n\n"
                           "主题词只是字面匹配：先判断哪些真与主题有关（同义说法、相关对象也算），去掉无关的，再补上漏掉的。"),
                "topic_rule": t("\n6. Only touch units related to the topic; leave unrelated units alone even if they could be compacted.",
                                "\n6. 只动与主题有关的单元；与主题无关的单元即使能压缩也不要动。")}
    pairs = candidates(base, limit=40)
    lines = [t(f"- similarity {p['similarity']}: `{p['a']}` / `{p['b']}`" + (f", shared objects {', '.join(p['shared'])}" if p["shared"] else ""),
               f"- 相似度 {p['similarity']}：`{p['a']}` / `{p['b']}`" + (f"，共同对象 {', '.join(p['shared'])}" if p["shared"] else ""))
             for p in pairs["duplicates"] + pairs["conflicts"]]
    by_kind = {}
    for u in units:
        by_kind.setdefault(f"{u.get('scope', '?')}/{u.get('form')}", []).append(u)
    groups = "\n".join(t(f"- {k}: {len(v)}", f"- {k}：{len(v)} 条") for k, v in sorted(by_kind.items(), key=lambda kv: -len(kv[1])))
    listing = "\n".join(render_unit(u) for u in units[:200])
    return {"goal": t("Make the knowledge base smaller without losing information; you decide what to compact and how.",
                      "让知识库在不丢信息的前提下变小，由你判断压缩哪些、怎么压缩。"),
            "scope": t(f"All active units, by scope / form:\n\n{groups}\n\nUnit pairs with similar content or anchored to the same object (hints only):\n\n"
                       f"{chr(10).join(lines) or '(none)'}\n\nActive units{' (only the first 200 listed)' if len(units) > 200 else ''}:\n\n{listing}",
                       f"全部活跃单元，按粒度 / 形式：\n\n{groups}\n\n内容相近或锚定同一对象的单元对（只是提示）：\n\n"
                       f"{chr(10).join(lines) or '（没有）'}\n\n活跃单元{'（只列前 200 条）' if len(units) > 200 else ''}：\n\n{listing}"),
            "topic_rule": ""}


def render_candidates(base, step) -> str:
    found = candidates(base)
    units = {u["id"]: u for u in load_units(layout(base).units)}
    show = lambda uid: f"`{uid}` [{units[uid].get('form')}/{units[uid].get('status')}] {units[uid]['content'][:160]}"  # noqa: E731
    lines = []
    for p in found["duplicates" if step == "dedup" else "conflicts"]:
        lines += [t(f"- similarity {p['similarity']}" + (f", shared objects {', '.join(p['shared'])}" if p["shared"] else ""),
                    f"- 相似度 {p['similarity']}" + (f"，共同对象 {', '.join(p['shared'])}" if p["shared"] else "")),
                  f"  - {show(p['a'])}", f"  - {show(p['b'])}"]
    if step == "conflict" and found["contested"]:
        lines += ["", t("Units that are contested or whose latest evidence refutes them:", "有争议或最近一条证据为反驳的单元："),
                  *[f"- {show(uid)}" for uid in found["contested"]]]
    return "\n".join(lines) or t("(no candidates found; you can still browse the knowledge base yourself)", "（没有找到候选；仍可自己浏览知识库）")


# ------------------------------------------------------------------ prompts and acceptance


def resolve_base(path) -> tuple[Path, Path | None]:
    """(knowledge layer root, data root): the same for a workspace; a knowledge base has no data root."""
    path = Path(path).resolve()
    return path, data_root(path)


def history_ids(base) -> set[str]:
    from ..workspace import snapshots

    return {u["id"] for d in snapshots(base) for u in load_units(layout(d).units)} if data_root(base) else set()


def prompt(path, step, topic=None) -> str:
    from . import check_knowledge
    from . import outline as ol
    from ..workspace import templates

    base, root = resolve_base(path)
    lay = layout(base)
    before = [i for i in check_knowledge(base, history_ids(base), root=root) if not i.startswith(LAYERED)]
    note = t("(the following issues existed before this step and are unrelated to this task; they may stay: " + "; ".join(before[:10]) + ")",
             "（以下是整理前就有的问题，与本任务无关，可以保留：" + "；".join(before[:10]) + "）") if before else ""
    units = load_units(lay.units)
    values = {"base": base, "check_note": note, "n_units": sum(u.get("status") not in INACTIVE for u in units),
              "n_inactive": sum(u.get("status") in INACTIVE for u in units),
              "verify": (t("You can query `data/`, use tools or `knosis knowledge verify` to get new evidence.",
                           "可以查 `data/`、用工具或 `knosis knowledge verify` 取得新证据。") if root else
                         t("The knowledge base has no data: judge only from existing evidence and the traces in `evidence/traces/`; "
                           "if you cannot decide, mark it contested.",
                           "知识库没有数据，只能依据已有证据与 `evidence/traces/` 里的轨迹判断；判断不了就标 contested。"))}
    if step == "organize":
        items = ol.members(base)
        draft = ol.write_outline(base, ol.draft(base), "outline.draft.yaml")
        values |= {"draft": draft, "n_skills": sum(1 for i in items.values() if i.get("form") == "skill"),
                   "existing": (t("An outline `kb/outline.yaml` already exists: update it, keep the sensible structure, put the new \"unclassified\" "
                                  f"knowledge into it, and split or merge sections where needed (`knosis knowledge outline --ws {base}` shows the "
                                  "current outline and the unclassified units).",
                                  "已有大纲 `kb/outline.yaml`：在它的基础上更新，保留合理的结构，把「未归类」的新知识放进去，"
                                  f"必要时拆分或合并节（`knosis knowledge outline --ws {base}` 看当前大纲与未归类单元）。")
                                if ol.load_outline(base) is not None else t("There is no outline yet; start from the draft.", "还没有大纲，从草稿出发。"))}
    elif step == "structure":
        from . import structure as st

        cov = st.coverage(base)
        values |= {"summary": st.summary(base), "graph_cov": f"{GRAPH_COVERAGE:.0%}", "flow_cov": f"{FLOW_COVERAGE:.0%}",
                   "n_objects": cov["objects"], "n_procedural": cov["procedural"],
                   "existing": (t("A knowledge graph / flowcharts already exist: update them (add the new units, remove references to inactive units), "
                                  "keeping the sensible structure.",
                                  "已有知识图谱 / 流程图：在它们的基础上更新（补上新单元，去掉对已失效单元的引用），保留合理的结构。")
                                if st.graph_path(base).exists() else
                                t("There is no knowledge graph or flowchart yet; build them from scratch.", "还没有知识图谱与流程图，从头建。"))}
    elif step == "compact":
        values |= compact_values(base, topic)
    else:
        values["candidates"] = render_candidates(base, step)
    text = Template((templates() / "consolidate" / f"{step}.md").read_text(encoding="utf-8")).substitute(values)
    text += multi_note(base, step) if step in ("organize", "structure") else ""
    if root:
        text += t("\nThe runner accepts the consolidation and saves the knowledge version: do not run `knosis ws check` or `knosis ws goto`, "
                  "do not switch stages, and do not write the changelog in the stage directory.\n",
                  "\n内化由运行器验收并保存知识版本：不要运行 `knosis ws check`、`knosis ws goto`，不要切换阶段，"
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
    if step == "compact":
        issues += compact_issues(before_units, {u["id"]: u for u in now})
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


def compact_issues(before: dict, after: dict) -> list[str]:
    """The active unit count drops (no change also passes); units made inactive in this step must point to active units, not silently vanish."""
    if before == after:
        return []
    alive = lambda units: {uid for uid, u in units.items() if u.get("status") not in INACTIVE}  # noqa: E731
    issues = []
    if len(alive(after)) >= len(alive(before)):
        issues.append(f"compact: active units {len(alive(before))} -> {len(alive(after))}; must decrease")
    for uid in alive(before) - alive(after):
        target = after[uid].get("merged_into") or after[uid].get("superseded_by")
        if not target:
            issues.append(f"{uid}: compacted units need merged_into (or superseded_by) pointing to the unit that covers them")
        elif after.get(resolve(target, after), {}).get("status") in INACTIVE:
            issues.append(f"{uid}: {target} must resolve to an active unit")
    return issues


# ------------------------------------------------------------------ logging


def actions(before: dict, after: dict, step) -> list[dict]:
    """Diff units before and after consolidation to derive operation records."""
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


# ------------------------------------------------------------------ run


def backup(base, tmp) -> None:
    for part in ("kb", "evidence"):
        if (Path(base) / part).exists():
            shutil.copytree(Path(base) / part, Path(tmp) / part, ignore=shutil.ignore_patterns("__pycache__"))


def restore(base, tmp) -> None:
    for part in ("kb", "evidence"):
        shutil.rmtree(Path(base) / part, ignore_errors=True)
        if (Path(tmp) / part).exists():
            shutil.copytree(Path(tmp) / part, Path(base) / part)


def run_step(path, step, agent="codex", model=None, effort=None, topic=None) -> dict:
    from ..workspace.driver import agent_command
    from . import check_knowledge

    base, root = resolve_base(path)
    lay = layout(base)
    before = {u["id"]: u for u in load_units(lay.units)}
    before_issues = [i for i in check_knowledge(base, history_ids(base), root=root) if not i.startswith(LAYERED)]
    text, issues, started = prompt(base, step, topic), [], time.monotonic()
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
            text += t("\nAcceptance failed, please fix:\n", "\n验收未通过，请修正：\n") + "\n".join(issues)
        if issues:
            restore(base, tmp)
            return {"step": step, "issues": issues, "restored": True, "seconds": round(time.monotonic() - started)}
    after = {u["id"]: u for u in load_units(lay.units)}
    done = actions(before, after, step)
    if step == "compact":
        alive = lambda units: sum(u.get("status") not in INACTIVE for u in units.values())  # noqa: E731
        done.append({"step": step, "op": "compact", "topic": topic, "active_before": alive(before),
                     "active_after": alive(after), "created": datetime.now(timezone.utc).isoformat()})
    if step == "structure":
        from .structure import coverage

        done.append({"step": step, "op": "structure", **coverage(base), "created": datetime.now(timezone.utc).isoformat()})
    log_actions(base, done)
    ops = {}
    for a in done:
        ops[a["op"]] = ops.get(a["op"], 0) + 1
    out = {"step": step, "issues": [], "actions": ops, "seconds": round(time.monotonic() - started)}
    if step == "compact":
        out |= {"topic": topic, "active": [done[-1]["active_before"], done[-1]["active_after"]]}
    return out


def run(path, steps=STEPS, agent="codex", model=None, effort=None, topic=None) -> list[dict]:
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
    results = []
    for step in steps:
        if step not in STEPS + EXTRA:
            raise ValueError(f"unknown step: {step}; choose from {', '.join(STEPS + EXTRA)}")
        results.append(run_step(path, step, agent, model, effort, topic))
        print(json.dumps(results[-1], ensure_ascii=False))
    return results
