"""skill 层：如何运用知识解某类任务（解题集）。知识是对环境的理解、与 agent 无关；skill 是用法，讲有没有效，不讲对错。

    kb/skills/<名字>/SKILL.md      与 Codex / Claude Code 的 skill 同格式

    ---
    name: multi-hop-loan
    description: 多跳贷款类题目的解法          # 一句话，装给 agent 时用作触发说明
    when: 题目沿 Loan / Account 走两跳以上     # 适用的任务类型与条件
    uses: [refine/type-view, usage/refine/type-view/agg]   # 引用的知识 id（κ、usage 单元或本体单元）
    derived_from: [003-refine-r1]           # 总结自哪些反馈记录（可选）
    status: active                          # active / stale / retracted
    ---
    步骤 ……

skill 由 agent 在 RSI 中根据反馈自己补充。聪明的 agent 也许用不上它，但它照样记录在库里。
Knosis 检查：`uses` 能解析；所用知识被撤回或失效后，skill 须标为 stale / retracted（与 κ 的 I5 同理）。
usage 管有没有用，skill 管怎么做：skill 的效果写成 usage 单元（`scope=usage`，`meta.of: skill:<名字>`，
dev 反馈会自动生成 `usage/skill:<名字>/<题型>`），再由证据支持；在决策里通过 `used_units` 引用 `skill:<名字>`。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .layout import layout
from .units import INACTIVE, resolve

STATUSES = {"active", "stale", "retracted"}
REQUIRED = ("name", "description", "when", "uses")


def load_skills(base) -> list[dict]:
    """知识库里的全部 skill：front matter 字段 + `body` + `path`（相对 `base`）。"""
    skills = []
    for path in sorted(layout(base).skills.glob("*/SKILL.md")):
        _, head, body = path.read_text(encoding="utf-8").split("---", 2)
        skills.append({**yaml.safe_load(head), "body": body.strip(), "path": str(path.relative_to(Path(base)))})
    return skills


def skill_id(skill) -> str:
    return f"skill:{skill['name']}"


def check_skills(skills, units: dict, feedback_ids=None) -> list[str]:
    """`units`：{id: κ}（含本体单元与历史版本）；`feedback_ids`：给定时检查 derived_from 指向的反馈记录存在。"""
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
