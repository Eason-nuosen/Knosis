"""Skill layer: how to apply knowledge to a class of tasks (solution playbooks). Knowledge is understanding of the environment, independent of the agent; a skill is usage, judged by whether it helps, not by truth.

    kb/skills/<name>/SKILL.md      same format as Codex / Claude Code skills

    ---
    name: multi-hop-loan
    description: Solving multi-hop loan questions   # one sentence, used as the trigger description when installed for an agent
    when: the question goes two or more hops via Loan / Account   # applicable task type and conditions
    uses: [refine/type-view, usage/refine/type-view/agg]   # referenced knowledge ids (κ, usage units or ontology units)
    derived_from: [003-refine-r1]           # feedback records it was summarized from (optional)
    status: active                          # active / stale / retracted
    ---
    Steps ...

Skills are added by the agent itself during RSI based on feedback. A smart agent may not need them, but they are still recorded in the library.
Knosis checks: `uses` resolves; once the knowledge used is retracted or stale, the skill must be marked stale / retracted (same as κ's I5).
Usage says whether it helps, a skill says how: a skill's effect is a usage unit (`scope=usage`, `meta.of: skill:<name>`;
dev feedback auto-generates `usage/skill:<name>/<question type>`) backed by evidence; decisions cite `skill:<name>` via `used_units`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .layout import layout
from .units import INACTIVE, resolve

STATUSES = {"active", "stale", "retracted"}
REQUIRED = ("name", "description", "when", "uses")


def load_skills(base) -> list[dict]:
    """All skills in the knowledge base: front matter fields + `body` + `path` (relative to `base`)."""
    skills = []
    for path in sorted(layout(base).skills.glob("*/SKILL.md")):
        _, head, body = path.read_text(encoding="utf-8").split("---", 2)
        skills.append({**yaml.safe_load(head), "body": body.strip(), "path": str(path.relative_to(Path(base)))})
    return skills


def skill_id(skill) -> str:
    return f"skill:{skill['name']}"


def check_skills(skills, units: dict, feedback_ids=None) -> list[str]:
    """`units`: {id: κ} (including ontology units and historical versions); `feedback_ids`: if given, check that derived_from feedback records exist."""
    issues, seen = [], set()
    for skill in skills:
        name = skill.get("name") or skill["path"]
        for key in REQUIRED:
            if not skill.get(key):
                issues.append(f"skill {name}: missing {key}")
        if Path(skill["path"]).parent.name != skill.get("name"):
            issues.append(f"skill {name}: directory name must equal name")
        if name in seen:
            issues.append(f"skill {name}: duplicate name")
        seen.add(name)
        status = skill.get("status", "active")
        if status not in STATUSES:
            issues.append(f"skill {name}: invalid status: {status}")
        for uid in skill.get("uses", []):
            if uid not in units:
                issues.append(f"skill {name}: unknown knowledge in uses: {uid}")
            elif units.get(resolve(uid, units), {}).get("status") in INACTIVE and status == "active":
                issues.append(f"skill {name}: uses inactive knowledge {uid}; status must be stale or retracted")
        if feedback_ids is not None:
            for record in skill.get("derived_from", []):
                if record not in feedback_ids:
                    issues.append(f"skill {name}: unknown feedback record in derived_from: {record}")
    return issues


def active_skills(base) -> list[dict]:
    return [s for s in load_skills(base) if s.get("status", "active") == "active"]
