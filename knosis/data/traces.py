"""Agent traces: normalize traces from various sources to ATIF v1.7 (Harbor's Agent Trajectory Interchange Format) so agents can extract knowledge from them.

One JSON file `<id>.json` per trace:

    {"schema_version": "ATIF-v1.7", "session_id": "...", "agent": {"name": "codex", "version": "0.160.0"},
     "steps": [{"step_id": 1, "source": "user", "message": "..."},
               {"step_id": 2, "source": "agent", "message": "...", "reasoning_content": "...",
                "tool_calls": [{"tool_call_id": "c1", "function_name": "exec", "arguments": {...}}],
                "observation": {"results": [{"source_call_id": "c1", "content": "..."}]}}],
     "subagent_trajectories": [...],
     "extra": {"knosis": {"format": "codex", "file": "...", "reader": "knosis-traces/1", "version": "0.160.0",
                          "tested": true, "accounting": {...}, ...}}}

- `step_id` runs consecutively from 1; `source` is user / agent / system. An agent step is one model output (text, reasoning, calls);
  call results hang on the `observation` of the step that issued the call. In multi-agent traces the speaking agent is in `extra.knosis.agent`.
- Only what the source has is recorded: values ATIF requires but the source lacks (e.g. "" for a message without text, non-object call
  arguments wrapped as `{"input": ...}`) are noted in `extra.knosis`; position-inferred pairings (results without a call id) are marked `paired_by`.
- Text longer than `LIMIT` is truncated; `extra.knosis.truncated` records the fields and original lengths.
- Every source line is accounted for (`accounting`: how many mapped, which kinds skipped and how many); if the source format version is not
  in `TESTED`, `tested=false` and callers should warn (a changed format may parse wrongly).
- Reference answers, annotations and other GT stay out of traces (kept separately by each dataset's loader).

Knowledge cites trace steps as `<dir>/<id>.json#step/<n>`; subagent steps as `<dir>/<id>.json#agent/<subagent id>/step/<n>`.

Supported formats (`detect`):
- codex: `~/.codex/sessions/**/rollout-*.jsonl` (`session_meta` + `response_item`)
- claude: Claude Code session JSONL (`~/.claude/projects/<project>/<session>.jsonl`), with `<session>/subagents/agent-*.jsonl` in the same directory as subagents
- steps: step-by-step agent traces (e.g. agent-rsi's AppWorld ReAct), `{instruction, steps: [{reasoning, response, code, env_feedback}]}`
- messages: OpenAI-style messages, a JSON list or JSONL, each `{role, content[, tool_calls]}`; `{"messages": [...]}` wrappers are accepted too
- whoandwhen: one Who&When failure log (`{question, history: [...], mistake_*}`), one step per history entry (step = index + 1)
- atif: traces already in ATIF v1.7
- legacy: pre-v0.5 Knosis step sequences (one `{step, role, kind, text}` per line), only for `knosis migrate`
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

SCHEMA = "ATIF-v1.7"
READER = "knosis-traces/1"
LIMIT = 4000
TESTED = {"codex": ("0.147", "0.149", "0.160", "0.163"), "claude": ("2.1",)}
SOURCES = ("system", "user", "agent")
REF = re.compile(r"#(?:agent/([^/#;\s]+)/)?step/(\d+)$")


# ---------- reading files ----------

def read(path):
    """A JSON document (list or object) or the list of JSONL lines."""
    text = Path(path).read_text(encoding="utf-8")
    head = text.lstrip()
    if head.startswith(("[", "{")):
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def detect(rows) -> str:
    first = rows[0] if rows else {}
    if not isinstance(first, dict):
        return "messages"
    if str(first.get("schema_version", "")).startswith("ATIF-"):
        return "atif"
    if first.get("type") == "session_meta":
        return "codex"
    if isinstance(first.get("steps"), list):
        return "steps"
    if isinstance(first.get("history"), list) and "question" in first:
        return "whoandwhen"
    if isinstance(first.get("messages"), list):
        return "messages"
    if {"step", "role", "kind"} <= set(first):
        return "legacy"
    if any(r.get("type") in ("user", "assistant") and isinstance(r.get("message"), dict) for r in rows[:50]):
        return "claude"
    return "messages"


# ---------- entries → ATIF steps ----------
# Each format is first read into a stream of entries, which `assemble` turns into steps by shared rules. An entry:
#   {"role": user|assistant|tool|system, "kind": message|reasoning|call|output, "text", "name", "call_id",
#    "arguments", "group", "agent", "timestamp", "ref"}
# Rules: each user / system message is its own step; assistant entries join the current agent step unless a result or user message
# came in between, the speaking agent changed, or `group` changed (Claude Code's message.id, Who&When's index); results attach by
# call_id to the step that issued the call, and those without an id are paired by position.

def item(role, kind, text="", **extra) -> dict:
    return {"role": role, "kind": kind, "text": text, **{k: v for k, v in extra.items() if v is not None}}


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for b in value:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                t = b.get("text") or b.get("input_text") or b.get("output_text")
                if t is None and b.get("type") in ("image", "input_image", "image_url"):
                    t = "[image]"
                parts.append(t if isinstance(t, str) else json.dumps(b, ensure_ascii=False))
        return "\n".join(parts)
    return json.dumps(value, ensure_ascii=False)


def cut(text, field, note) -> str:
    if len(text) > LIMIT:
        note.setdefault("truncated", {})[field] = note.get("truncated", {}).get(field, 0) + len(text)
        return text[:LIMIT]
    return text


def cut_args(value, note, field):
    if isinstance(value, str):
        return cut(value, field, note)
    if isinstance(value, dict):
        return {k: cut_args(v, note, f"{field}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [cut_args(v, note, field) for v in value]
    return value


def arguments(raw, note, cid) -> dict:
    """ATIF call arguments must be objects: JSON strings are parsed; other values are wrapped as `{"input": value}` and noted."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
    if raw is None:
        note.setdefault("calls", {})[cid] = {"arguments": "missing"}
        return {}
    note.setdefault("calls", {})[cid] = {"arguments": "wrapped"}
    return {"input": raw}


def assemble(items) -> tuple[list[dict], list[list[int]]]:
    """Entries → ATIF steps; also returns which entries (indices) make up each step, for migrating old step numbers."""
    steps, members, owner = [], [], {}
    open_agent = None  # index of the agent step that can still absorb entries
    n_calls = 0
    for idx, it in enumerate(items):
        role, kind = it["role"], it["kind"]
        if role in ("user", "system") and kind == "message":
            note = {}
            step = {"source": role, "message": cut(as_text(it.get("text")), "message", note)}
            steps.append(finish(step, it, note))
            members.append([idx])
            open_agent = None
            continue
        if role == "tool" or kind == "output":
            content = as_text(it.get("text"))
            target, paired = owner.get(it.get("call_id")), None
            if target is None:
                # no id (or no matching id): attach to the latest agent step with unanswered calls, paired by position
                for j in range(len(steps) - 1, -1, -1):
                    if steps[j]["source"] != "agent":
                        continue
                    answered = {r.get("source_call_id") for r in steps[j].get("observation", {}).get("results", [])}
                    pending = [c["tool_call_id"] for c in steps[j].get("tool_calls", []) if c["tool_call_id"] not in answered]
                    target, paired = j, (pending[0] if pending else None)
                    break
            if target is None:  # no earlier agent step: treat as a user message from the environment
                note = {"environment": True}
                steps.append(finish({"source": "user", "message": cut(content, "message", note)}, it, note))
                members.append([idx])
                open_agent = None
                continue
            step = steps[target]
            note = step.setdefault("extra", {}).setdefault("knosis", {})
            result = {"source_call_id": it.get("call_id") if it.get("call_id") in owner else paired,
                      "content": cut(content, "observation", note)}
            if it.get("call_id") not in owner:
                note.setdefault("paired_by", "position")
            step.setdefault("observation", {"results": []})["results"].append(result)
            members[target].append(idx)
            open_agent = None
            continue
        # assistant entry
        cur = steps[open_agent] if open_agent is not None else None
        same = (cur is not None and cur.get("extra", {}).get("knosis", {}).get("agent") == it.get("agent")
                and members[open_agent] and items[members[open_agent][-1]].get("group") == it.get("group"))
        if not same:
            note = {}
            cur = finish({"source": "agent", "message": ""}, it, note)
            steps.append(cur)
            members.append([])
            open_agent = len(steps) - 1
        note = cur.setdefault("extra", {}).setdefault("knosis", {})
        members[open_agent].append(idx)
        if kind == "message":
            text = cut(as_text(it.get("text")), "message", note)
            cur["message"] = f"{cur['message']}\n\n{text}" if cur["message"] else text
        elif kind == "reasoning":
            text = cut(as_text(it.get("text")), "reasoning_content", note)
            cur["reasoning_content"] = f"{cur['reasoning_content']}\n\n{text}" if cur.get("reasoning_content") else text
        elif kind == "call":
            n_calls += 1
            cid = str(it.get("call_id") or f"call_{n_calls}")
            if "call_id" not in it:
                note.setdefault("calls", {}).setdefault(cid, {})["id"] = "generated"
            args = cut_args(arguments(it.get("arguments", it.get("text")), note, cid), note, f"arguments.{cid}")
            cur.setdefault("tool_calls", []).append({"tool_call_id": cid, "function_name": str(it.get("name") or "tool"),
                                                     "arguments": args})
            owner[cid] = open_agent
        if not note:
            cur["extra"].pop("knosis")
        if not cur.get("extra"):
            cur.pop("extra", None)
    for i, step in enumerate(steps):
        step["step_id"] = i + 1
    return [order(s) for s in steps], members


def finish(step, it, note) -> dict:
    if it.get("timestamp"):
        step["timestamp"] = it["timestamp"]
    if it.get("model"):
        step["model_name"] = it["model"]
    for key in ("agent", "ref", "speaker"):
        if it.get(key) is not None:
            note[key] = it[key]
    if note:
        step["extra"] = {"knosis": note}
    return step


def order(step) -> dict:
    keys = ("step_id", "timestamp", "source", "model_name", "message", "reasoning_content", "tool_calls", "observation", "extra")
    return {k: step[k] for k in keys if k in step}


def trajectory(items, *, session, agent, fmt, file=None, version=None, accounting=None, extra=None, subagents=None) -> dict:
    steps, _ = assemble(items)
    if not steps:
        steps = [{"step_id": 1, "source": "system", "message": "", "extra": {"knosis": {"empty": True}}}]
    tested = None
    if fmt in TESTED:
        tested = bool(version) and any(str(version) == v or str(version).startswith(v + ".") for v in TESTED[fmt])
    info = {"format": fmt, "reader": READER, **({"file": str(file)} if file else {}),
            **({"version": version} if version else {}), **({"tested": tested} if tested is not None else {}),
            **({"accounting": accounting} if accounting else {}), **(extra or {})}
    out = {"schema_version": SCHEMA, "session_id": str(session), "agent": agent, "steps": steps}
    if subagents:
        out["subagent_trajectories"] = subagents
    out["extra"] = {"knosis": info}
    return out


# ---------- formats ----------

def codex(rows, path=None) -> dict:
    meta = rows[0].get("payload", {}) if rows else {}
    items, skipped, mapped = [], Counter(), 0
    for line, r in enumerate(rows, 1):
        p = r.get("payload", {}) if isinstance(r.get("payload"), dict) else {}
        if r.get("type") != "response_item":
            skipped[str(r.get("type"))] += 1
            continue
        kind, ts = p.get("type"), r.get("timestamp")
        if kind == "message" and p.get("role") == "developer":  # system prompt and permission notes, identical in every session
            skipped["developer"] += 1
            continue
        if kind == "message" and p.get("role") in ("user", "assistant"):
            items.append(item(p["role"], "message", as_text(p.get("content", [])), timestamp=ts, ref=line))
        elif kind == "agent_message":  # message from another agent
            items.append(item("user", "message", as_text(p.get("content")), speaker=p.get("author"), timestamp=ts, ref=line))
        elif kind == "reasoning":
            if not p.get("summary"):  # encrypted content only
                skipped["reasoning(encrypted)"] += 1
                continue
            items.append(item("assistant", "reasoning", as_text(p["summary"]), timestamp=ts, ref=line))
        elif kind in ("custom_tool_call", "function_call"):
            items.append(item("assistant", "call", name=p.get("name"), call_id=p.get("call_id"), timestamp=ts, ref=line,
                              arguments=p.get("input") if kind == "custom_tool_call" else p.get("arguments")))
        elif kind in ("custom_tool_call_output", "function_call_output"):
            out = p.get("output")
            items.append(item("tool", "output", out if isinstance(out, (str, list)) else json.dumps(out, ensure_ascii=False),
                              call_id=p.get("call_id"), timestamp=ts, ref=line))
        elif kind == "web_search_call":
            items.append(item("assistant", "call", name="web_search", arguments=p.get("action") or {}, timestamp=ts, ref=line))
        else:
            skipped[f"response_item:{kind}:{p.get('role', '')}".rstrip(":")] += 1
            continue
        mapped += 1
    return trajectory(items, session=meta.get("id") or (Path(path).stem if path else "codex"), fmt="codex", file=path,
                      agent={"name": "codex", "version": str(meta.get("cli_version") or "unknown")},
                      version=meta.get("cli_version"), accounting={"lines": len(rows), "mapped": mapped, "skipped": dict(skipped)},
                      extra={"cwd": meta.get("cwd", "")})


def claude_items(rows, skipped) -> tuple[list[dict], int]:
    items, mapped = [], 0
    for line, r in enumerate(rows, 1):
        kind = r.get("type")
        if kind not in ("user", "assistant") or not isinstance(r.get("message"), dict):
            if kind == "system" and r.get("subtype") in ("compact_boundary", "api_error"):
                items.append(item("system", "message", f"[{r['subtype']}] {as_text(r.get('content'))}".strip(),
                                  timestamp=r.get("timestamp"), ref=line))
                mapped += 1
            else:
                skipped[f"{kind}:{r.get('subtype')}" if r.get("subtype") else str(kind)] += 1
            continue
        if r.get("isMeta"):
            skipped["meta"] += 1
            continue
        msg, ts = r["message"], r.get("timestamp")
        content = msg.get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
        group = msg.get("id") or r.get("uuid")
        for b in blocks:
            t = b.get("type") if isinstance(b, dict) else None
            if t == "text" and b.get("text"):
                items.append(item("assistant" if kind == "assistant" else "user", "message", b["text"], group=group,
                                  timestamp=ts, ref=line, model=msg.get("model") if kind == "assistant" else None))
            elif t == "thinking":
                if b.get("thinking"):
                    items.append(item("assistant", "reasoning", b["thinking"], group=group, timestamp=ts, ref=line))
            elif t == "tool_use":
                items.append(item("assistant", "call", name=b.get("name"), call_id=b.get("id"), arguments=b.get("input"),
                                  group=group, timestamp=ts, ref=line))
            elif t == "tool_result":
                items.append(item("tool", "output", b.get("content"), call_id=b.get("tool_use_id"), timestamp=ts, ref=line))
            elif t == "image":
                items.append(item("user", "message", "[image]", group=group, timestamp=ts, ref=line))
            else:
                skipped[f"block:{t}"] += 1
        mapped += 1
    return items, mapped


def claude(rows, path=None) -> dict:
    skipped = Counter()
    items, mapped = claude_items(rows, skipped)
    versions = sorted({r["version"] for r in rows if isinstance(r, dict) and r.get("version")})
    session = next((r.get("sessionId") for r in rows if isinstance(r, dict) and r.get("sessionId")), None)
    subagents = []
    folder = Path(path).with_suffix("") / "subagents" if path else None
    if folder and folder.is_dir():
        for sub in sorted(folder.glob("agent-*.jsonl")):
            sub_rows = read(sub)
            sub_skipped = Counter()
            sub_items, sub_mapped = claude_items(sub_rows, sub_skipped)
            t = trajectory(sub_items, session=session or Path(path).stem, fmt="claude", file=sub,
                           agent={"name": "claude-code", "version": versions[-1] if versions else "unknown"},
                           accounting={"lines": len(sub_rows), "mapped": sub_mapped, "skipped": dict(sub_skipped)})
            t["trajectory_id"] = sub.stem.removeprefix("agent-")
            subagents.append(t)
    links = {}
    for r in rows:
        tur = r.get("toolUseResult") if isinstance(r, dict) else None
        if isinstance(tur, dict) and tur.get("agentId"):
            for b in (r.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    links[b.get("tool_use_id")] = tur["agentId"]
    version = versions[-1] if versions else None
    t = trajectory(items, session=session or (Path(path).stem if path else "claude"), fmt="claude", file=path,
                   agent={"name": "claude-code", "version": version or "unknown"}, version=version,
                   accounting={"lines": len(rows), "mapped": mapped, "skipped": dict(skipped)},
                   extra={"cwd": next((r["cwd"] for r in rows if isinstance(r, dict) and r.get("cwd")), ""),
                          **({"versions": versions} if len(versions) > 1 else {}),
                          **({"subagent_calls": links} if links else {})},
                   subagents=subagents)
    return t


def react(rows, path=None) -> dict:
    """Step-by-step records: each step's reasoning, written code (treated as one call), and environment feedback; `input_messages` is the cumulative conversation and is not expanded again."""
    run = rows[0]
    items = [item("user", "message", run.get("instruction", ""))]
    for i, s in enumerate(run["steps"]):
        if s.get("reasoning"):
            items.append(item("assistant", "reasoning", s["reasoning"], group=i))
        if s.get("code"):
            items.append(item("assistant", "call", name="code", arguments={"code": s["code"]}, call_id=f"step{i + 1}", group=i))
        elif s.get("response"):
            items.append(item("assistant", "message", s["response"], group=i))
        if s.get("env_feedback") is not None:
            items.append(item("tool", "output", s["env_feedback"], call_id=f"step{i + 1}" if s.get("code") else None))
    extra = {"outcome": {k: run[k] for k in ("completed", "success") if k in run}} if "success" in run else {}
    return trajectory(items, session=run.get("task_id") or (Path(path).stem if path else "run"), fmt="steps", file=path,
                      agent={"name": str(run.get("agent") or "agent"), "version": "unknown"}, extra=extra)


def messages(rows, path=None) -> dict:
    if len(rows) == 1 and isinstance(rows[0], dict) and isinstance(rows[0].get("messages"), list):
        rows = rows[0]["messages"]
    items = []
    for m in rows:
        role = m.get("role", "assistant")
        if role in ("tool", "function", "environment"):
            items.append(item("tool", "output", m.get("content"), call_id=m.get("tool_call_id"), name=m.get("name")))
            continue
        role = "assistant" if role not in ("user", "system") else role
        if m.get("content"):
            items.append(item(role, "message", m["content"], agent=m.get("name") if role == "assistant" else None))
        for call in m.get("tool_calls") or []:
            fn = call.get("function", call)
            items.append(item("assistant", "call", name=fn.get("name"), call_id=call.get("id"), arguments=fn.get("arguments"),
                              agent=m.get("name")))
    return trajectory(items, session=Path(path).stem if path else "messages", fmt="messages", file=path,
                      agent={"name": "agent", "version": "unknown"})


PAREN = re.compile(r"\s*\(.*\)\s*$")
WHOANDWHEN_GT = ("is_correct", "is_corrected", "ground_truth", "groundtruth", "mistake_agent", "mistake_step", "mistake_reason")


def speaker(entry) -> str | None:
    """The speaking agent in Who&When: `name` for Algorithm-Generated; `role` with the parenthetical stripped for Hand-Crafted (`Orchestrator (thought)`)."""
    if entry.get("name"):
        return str(entry["name"])
    role = entry.get("role")
    return PAREN.sub("", role) if isinstance(role, str) and role != "human" else None


def whoandwhen(rows, path=None) -> dict:
    """One log: one step per history entry (step = index + 1, aligned with the `mistake_step` annotation); the question goes in `extra.knosis.task` and takes no step.
    Annotations and the reference answer (`WHOANDWHEN_GT`) stay out of the trace."""
    run = rows[0]
    items = []
    for i, entry in enumerate(run["history"]):
        who = speaker(entry)
        raw_role = entry.get("role")
        if who is None:
            items.append(item("user", "message", entry.get("content", ""), ref=i, speaker=raw_role))
        else:
            items.append(item("assistant", "message", entry.get("content", ""), agent=who, group=i, ref=i,
                              speaker=raw_role if raw_role != who else None))
    agents = sorted({speaker(e) for e in run["history"]} - {None})
    prompts = run.get("system_prompt") if isinstance(run.get("system_prompt"), dict) else {}
    hand = "system_prompt" not in run
    extra = {"task": {"id": run.get("question_ID"), "question": run.get("question"), "level": run.get("level")},
             "agents": {a: {"instructions": cut(as_text(prompts.get(a)), f"agents.{a}", {})} if prompts.get(a) else {}
                        for a in agents}}
    return trajectory(items, session=Path(path).stem if path else str(run.get("question_ID")), fmt="whoandwhen", file=path,
                      agent={"name": "magentic-one" if hand else "captain-agent", "version": "unknown"}, extra=extra)


def legacy(rows, path=None) -> tuple[dict, dict[int, int]]:
    """Pre-v0.5 step sequence → ATIF; returns the trace and old step → new step. The old format has no call ids, so results are paired by position."""
    items = [item(r["role"], r["kind"], r.get("text", ""), name=r.get("name"),
                  arguments=r.get("text", "") if r["kind"] == "call" else None) for r in rows]
    steps, members = assemble(items)
    mapping = {rows[i]["step"]: n + 1 for n, group in enumerate(members) for i in group}
    t = {"schema_version": SCHEMA, "session_id": Path(path).stem if path else "legacy",
         "agent": {"name": "agent", "version": "unknown"}, "steps": steps,
         "extra": {"knosis": {"format": "legacy", "reader": READER, "migrated_from": "steps-v0", "file": str(path or "")}}}
    truncated = sum(1 for r in rows if r.get("truncated"))
    if truncated:
        t["extra"]["knosis"]["legacy_truncated_steps"] = truncated
    return t, mapping


def atif(rows, path=None) -> dict:
    t = rows[0]
    if t.get("schema_version") != SCHEMA:
        raise ValueError(f"unsupported ATIF version {t.get('schema_version')!r} (supported: {SCHEMA})")
    return t


READERS = {"codex": codex, "claude": claude, "steps": react, "messages": messages, "whoandwhen": whoandwhen, "atif": atif}


def normalize(path, fmt=None) -> dict:
    """Trace file → ATIF trace."""
    rows = read(path)
    fmt = fmt or detect(rows)
    if fmt == "legacy":
        return legacy(rows, path)[0]
    return READERS[fmt](rows, path)


# ---------- usage ----------

def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(t, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(t, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def calls(t) -> int:
    return sum(len(s.get("tool_calls", [])) for s in t["steps"])


def warning(t) -> str | None:
    """A one-line warning when the format version is untested or there are unrecognized source records."""
    info = t.get("extra", {}).get("knosis", {})
    notes = []
    if info.get("tested") is False:
        notes.append(f"{info['format']} version {info.get('version')!r} is untested (tested: {', '.join(TESTED[info['format']])})")
    unknown = {k: v for k, v in info.get("accounting", {}).get("skipped", {}).items() if k.startswith(("response_item:", "block:"))}
    if unknown:
        notes.append(f"unmapped records {unknown}")
    return "; ".join(notes) or None


def refs(t) -> set[tuple[str | None, int]]:
    """Citable steps: (subagent id or None, step number)."""
    out = {(None, s["step_id"]) for s in t["steps"]}
    for sub in t.get("subagent_trajectories", []):
        out |= {(sub.get("trajectory_id"), s["step_id"]) for s in sub["steps"]}
    return out


def parse_ref(fragment) -> tuple[str | None, int] | None:
    m = REF.search(fragment)
    return (m[1], int(m[2])) if m else None


def validate(t, path="$") -> list[str]:
    """ATIF v1.7 structural constraints (consecutive step ids, valid sources, non-null messages, object call arguments, results pointing to calls in the same step, agent-only fields)."""
    errors = []
    if t.get("schema_version") != SCHEMA:
        errors.append(f"{path}.schema_version: expected {SCHEMA!r}")
    agent = t.get("agent")
    if not isinstance(agent, dict) or not all(isinstance(agent.get(k), str) for k in ("name", "version")):
        errors.append(f"{path}.agent: needs string name and version")
    steps = t.get("steps")
    if not isinstance(steps, list) or not steps:
        return errors + [f"{path}.steps: at least one step"]
    for i, s in enumerate(steps):
        p = f"{path}.steps[{i}]"
        if s.get("step_id") != i + 1:
            errors.append(f"{p}.step_id: expected {i + 1}")
        if s.get("source") not in SOURCES:
            errors.append(f"{p}.source: {s.get('source')!r}")
        if not isinstance(s.get("message"), (str, list)):
            errors.append(f"{p}.message: must be a string")
        if s.get("source") != "agent" and any(k in s for k in ("tool_calls", "reasoning_content", "model_name")):
            errors.append(f"{p}: tool_calls / reasoning_content / model_name only on agent steps")
        ids = [c.get("tool_call_id") for c in s.get("tool_calls", [])]
        for c in s.get("tool_calls", []):
            if not isinstance(c.get("tool_call_id"), str) or not isinstance(c.get("function_name"), str):
                errors.append(f"{p}.tool_calls: tool_call_id and function_name must be strings")
            if not isinstance(c.get("arguments"), dict):
                errors.append(f"{p}.tool_calls: arguments must be an object")
        if len(set(ids)) != len(ids):
            errors.append(f"{p}.tool_calls: duplicate tool_call_id")
        for r in s.get("observation", {}).get("results", []):
            if r.get("source_call_id") is not None and r["source_call_id"] not in ids:
                errors.append(f"{p}.observation: result {r['source_call_id']!r} matches no call on this step")
    for k, sub in enumerate(t.get("subagent_trajectories", [])):
        errors += validate(sub, f"{path}.subagent_trajectories[{k}]")
    return errors


def render(t, title="") -> str:
    """Markdown for humans and agents: one section per step; `## step <n>` corresponds to `#step/<n>` in citations."""
    info = t.get("extra", {}).get("knosis", {})
    lines = [f"# {title or t.get('session_id', '')}\n"]
    task = info.get("task") or {}
    if task.get("question"):
        lines.append(f"**任务**：{task['question']}\n")
    if info.get("agents"):
        lines.append("**agent**：" + "、".join(f"`{a}`" for a in info["agents"]) + "\n")
    lines += render_steps(t["steps"])
    for sub in t.get("subagent_trajectories", []):
        sid = sub.get("trajectory_id")
        lines.append(f"\n# 子 agent `{sid}`（引用写 `#agent/{sid}/step/<n>`）\n")
        lines += render_steps(sub["steps"])
    return "\n".join(lines)


def render_steps(steps) -> list[str]:
    lines = []
    for s in steps:
        note = s.get("extra", {}).get("knosis", {})
        who = f" `{note['agent']}`" if note.get("agent") else ""
        cut_note = f"（截断：{', '.join(f'{k} 原 {v} 字符' for k, v in note['truncated'].items())}）" if note.get("truncated") else ""
        lines.append(f"## step {s['step_id']} · {s['source']}{who}{cut_note}\n")
        if s.get("reasoning_content"):
            lines.append(f"*思考*：{s['reasoning_content']}\n")
        if s.get("message"):
            lines.append(f"{as_text(s['message'])}\n")
        results = {}
        for r in s.get("observation", {}).get("results", []):
            results.setdefault(r.get("source_call_id"), []).append(as_text(r.get("content")))
        for c in s.get("tool_calls", []):
            args = c["arguments"]
            body = args["input"] if set(args) == {"input"} and isinstance(args["input"], str) else json.dumps(args, ensure_ascii=False, indent=1)
            lines.append(f"**调用** `{c['function_name']}`（{c['tool_call_id']}）：\n\n```\n{body}\n```\n")
            for out in results.pop(c["tool_call_id"], []):
                lines.append(f"**结果**：\n\n```\n{out}\n```\n")
        for out in [o for v in results.values() for o in v]:
            lines.append(f"**结果**（未配对）：\n\n```\n{out}\n```\n")
    return lines
