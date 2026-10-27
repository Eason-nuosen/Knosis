"""Routine collection: hand recent Codex / Claude Code sessions to an agent to extract knowledge, written back to a standalone knowledge base.

    knosis kb collect --kb ~/kb --since 1d [--source codex] [--limit 10] [--dry-run]

1. Find sessions: Codex in `$CODEX_HOME/sessions/**/rollout-*.jsonl`, Claude Code in `~/.claude/projects/*/*.jsonl`;
   filter by modification time, skipping those already collected (`collected.jsonl`), those whose cwd is inside the knowledge base
   (sessions collecting / organizing the KB itself), those whose cwd is a Knosis workspace (its knowledge is already recorded by the
   workspace flow; `--include-workspaces` lifts this), and those with fewer than `--min-calls` tool calls.
2. Normalize to ATIF traces in `<kb>/evidence/traces/<session id>.{json,md}` (format: `knosis.data.traces`); knowledge cites
   `evidence/traces/<id>.json#step/<n>` (consistent with `kb merge`, so it still resolves after inheritance into a workspace).
3. Launch the extraction agent in the KB directory (template `templates/collect.md`); acceptance: no new knowledge-layer issues and new
   units cite this run's traces. On failure retry once with the issues; if it still fails, restore the KB to its pre-run state
   (requires no uncommitted changes in the KB before the run).
4. On success record in `collected.jsonl`, then consolidate (`consolidate`: dedup -> conflicts -> organize; `--no-consolidate` skips it),
   and finally commit a git version.

Raw traces are copied into the knowledge base (a local git repository) and may contain paths or internal information; the prompt tells the agent not to put keys or passwords into knowledge.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..data.traces import calls, dump, normalize, read, render, warning
from .layout import TRACES, layout
from .units import load_units, write_units

LOG = "collected.jsonl"


def parse_since(text) -> datetime:
    """`30m` / `12h` / `1d` / `2w`, or an ISO date (`2026-10-20`)."""
    match = re.fullmatch(r"(\d+)([mhdw])", text)
    if match:
        unit = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[match[2]]
        return datetime.now(timezone.utc) - timedelta(**{unit: int(match[1])})
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.astimezone()


def session_files(source, home=None) -> list[Path]:
    home = Path(home or Path.home())
    if source == "codex":
        root = Path(os.environ.get("CODEX_HOME", home / ".codex")) / "sessions"
        return sorted(root.glob("**/rollout-*.jsonl"))
    return sorted((home / ".claude/projects").glob("*/*.jsonl"))


def session_cwd(rows, source) -> str:
    if source == "codex":
        return rows[0].get("payload", {}).get("cwd", "") if rows else ""
    return next((r["cwd"] for r in rows if r.get("cwd")), "")


def in_workspace(cwd) -> bool:
    path = Path(cwd)
    return any((p / ".knosis/state.json").exists() for p in [path, *path.parents])


def collected(kb) -> set[str]:
    path = Path(kb) / LOG
    return {r["session"] for r in load_units(path)} if path.exists() else set()


def find(kb, source="codex", since="1d", include_workspaces=False, min_calls=3, home=None) -> tuple[list[dict], dict]:
    """Candidate sessions (oldest first) and counts of skipped ones."""
    kb, cutoff, done = Path(kb).resolve(), parse_since(since).timestamp(), collected(kb)
    found, skipped = [], {"collected": 0, "inside_kb": 0, "workspace": 0, "few_calls": 0, "unreadable": 0}
    for path in session_files(source, home):
        if path.stat().st_mtime < cutoff:
            continue
        sid = path.stem
        if sid in done:
            skipped["collected"] += 1
            continue
        try:
            rows = read(path)
            cwd = session_cwd(rows, source)
            trace = normalize(path, source)
        except (ValueError, KeyError, IndexError, json.JSONDecodeError):
            skipped["unreadable"] += 1
            continue
        resolved = Path(cwd).resolve() if cwd else None
        if resolved and (resolved == kb or kb in resolved.parents):
            skipped["inside_kb"] += 1
        elif cwd and not include_workspaces and in_workspace(cwd):
            skipped["workspace"] += 1
        elif calls(trace) < min_calls:
            skipped["few_calls"] += 1
        else:
            found.append({"session": sid, "source": source, "path": str(path), "cwd": cwd, "trace": trace, "warning": warning(trace),
                          "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
    return sorted(found, key=lambda s: s["modified"]), skipped


def write_traces(kb, sessions) -> list[str]:
    lines = []
    for s in sessions:
        out = dump(s["trace"], layout(kb).traces / f"{s['session']}.json")
        out.with_suffix(".md").write_text(render(s["trace"], f"{s['session']}（{s['source']}，工作目录 {s['cwd']}）"),
                                          encoding="utf-8")
        lines.append(f"- `{TRACES}/{s['session']}.md`：{s['source']}，{s['modified'][:16]}，工作目录 `{s['cwd']}`，"
                     f"{len(s['trace']['steps'])} 步（工具调用 {calls(s['trace'])} 次）")
    return lines


def prompt(kb, sessions) -> str:
    from string import Template

    from ..workspace import TEMPLATES

    units = load_units(layout(kb).units)
    return Template((TEMPLATES / "collect.md").read_text(encoding="utf-8")).substitute(
        kb=Path(kb).resolve(), n=len(sessions), listing="\n".join(write_traces(kb, sessions)), n_units=len(units),
        outline="有，先读 `kb/outline.yaml`" if layout(kb).outline.exists() else "还没有")


def git(kb, *args) -> str:
    return subprocess.run(["git", *args], cwd=kb, check=True, capture_output=True, text=True).stdout.strip()


def acceptance(kb, before_issues, before_ids, sessions) -> list[str]:
    from . import check_knowledge

    issues = sorted(set(check_knowledge(kb)) - set(before_issues))
    ids = {s["session"] for s in sessions}
    for unit in load_units(layout(kb).units):
        if unit["id"] in before_ids:
            continue
        cited = re.findall(rf"{TRACES}/([^#; ]+)\.json#", unit.get("provenance", ""))
        if unit.get("provenance", "").strip() != "derived" and not set(cited) & ids:
            issues.append(f"{unit['id']}: new unit must cite this run's traces as {TRACES}/<id>.json#step/<n>")
    return issues


def run(kb, source="codex", since="1d", limit=10, agent="codex", model=None, effort=None, include_workspaces=False,
        min_calls=3, consolidate=True, dry_run=False) -> dict:
    from ..workspace.driver import agent_command
    from . import check_knowledge
    from . import consolidate as consolidate_kb

    kb = Path(kb).resolve()
    sessions, skipped = find(kb, source, since, include_workspaces, min_calls)
    sessions = sessions[:limit]
    summary = {"kb": str(kb), "sessions": [s["session"] for s in sessions], "skipped": skipped}
    warnings = {s["session"]: s["warning"] for s in sessions if s["warning"]}
    if warnings:  # untested session format version or unknown records: parsing may be incomplete
        summary["warnings"] = warnings
    if dry_run or not sessions:
        return summary | {"cwd": [s["cwd"] for s in sessions]}
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
    if git(kb, "status", "--porcelain", "--", ".", ":!*.log", ":!kb/outline.draft.yaml"):
        raise RuntimeError(f"{kb} has uncommitted changes; commit or discard them first")
    before_issues = check_knowledge(kb)
    before_ids = {u["id"] for u in load_units(layout(kb).units)}
    text, issues = prompt(kb, sessions), []
    env = {**os.environ, "KNOSIS_DEPTH": "1"}
    for attempt in range(2):
        started = time.monotonic()
        with (kb / "collect.log").open("a", encoding="utf-8") as log:
            result = subprocess.run(agent_command(agent, kb, text, model, effort), cwd=kb, env=env,
                                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        issues = [f"{agent} exited with {result.returncode}"] if result.returncode else acceptance(
            kb, before_issues, before_ids, sessions)
        print(json.dumps({"step": "extract", "attempt": attempt + 1, "seconds": round(time.monotonic() - started),
                          "issues": issues}, ensure_ascii=False))
        if not issues:
            break
        text += "\n验收未通过，请修正：\n" + "\n".join(issues)
    if issues:
        git(kb, "reset", "--hard", "HEAD")
        git(kb, "clean", "-fd", "-e", "*.log", "-e", "kb/outline.draft.yaml")
        return summary | {"issues": issues, "restored": True}
    added = sorted({u["id"] for u in load_units(layout(kb).units)} - before_ids)
    now = datetime.now(timezone.utc).isoformat()
    log = load_units(kb / LOG) if (kb / LOG).exists() else []
    write_units(kb / LOG, log + [{"session": s["session"], "source": s["source"], "path": s["path"], "cwd": s["cwd"],
                                  "collected": now} for s in sessions])
    summary |= {"added": added}
    if consolidate:
        summary["consolidate"] = consolidate_kb.run(kb, agent=agent, model=model, effort=effort)
    git(kb, "add", "-A")
    git(kb, "-c", "user.name=Knosis", "-c", "user.email=knosis@localhost", "commit", "--quiet", "-m",
        f"collect: {len(sessions)} {source} sessions, {len(added)} new units")
    return summary | {"version": git(kb, "rev-parse", "--short", "HEAD")}
