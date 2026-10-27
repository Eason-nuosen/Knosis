"""MCP server: exposes a workspace's (or knowledge base's) knowledge and tool layers to agents as MCP tools (stdio, JSON-RPC 2.0, one message per line).

Division of labor:
- tools (`knosis/tools/<name>/`): separate processes that read data and emit inferred / observed κ annotations, never modifying the knowledge layer;
- skills (`kb/skills/<name>/SKILL.md`): procedures in the knowledge base for "how to apply knowledge to a class of tasks", written by agents;
- MCP (this module): protocol adapter only, no functionality. Knowledge operations call `knosis.knowledge` directly; tools run as subprocesses via `tool_run`.

Writes (`knowledge_add`, `knowledge_update`, `evidence_add`) are checked with `check_units` first and rejected if they introduce new issues.
`eval` is not exposed (scoring test tasks is not an operation available to agents).

    knosis mcp --ws <workspace or knowledge base>
    codex:  -c 'mcp_servers.knosis.command="knosis"' -c 'mcp_servers.knosis.args=["mcp","--ws","<dir>"]'
    claude: --mcp-config '{"mcpServers":{"knosis":{"command":"knosis","args":["mcp","--ws","<dir>"]}}}'
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__

PROTOCOL = "2025-06-18"


class Server:
    def __init__(self, ws):
        from .knowledge import data_root, layout

        # Workspaces and knowledge bases share a layout (kb/ + evidence/); a knowledge base has no data/, so root is None.
        self.ws = Path(ws).resolve()
        self.lay = layout(self.ws)
        self.root = data_root(self.ws)

    # ------------------------------------------------------------ knowledge layer

    def units(self):
        from .knowledge import load_units

        return load_units(self.lay.units) if self.lay.units.exists() else []

    def issues(self, units):
        from .knowledge import by_unit, check_units, load_evidence

        return set(check_units(units, root=self.root, evidence=by_unit(load_evidence(self.ws), self.root)))

    def guarded_write(self, units):
        """Write back units.jsonl only if no new issues are introduced."""
        from .knowledge import write_units

        new = sorted(self.issues(units) - self.issues(self.units()))
        if new:
            raise ValueError("rejected, would introduce issues:\n" + "\n".join(new))
        write_units(self.lay.units, units)

    def knowledge_select(self, text=None, about=None, form=None, scope=None, include_inactive=False,
                         include_contested=False, limit=50):
        """If `text` contains spaces, search by keywords: any matching word selects a unit, ranked by number of matched words."""
        from .knowledge import scope_of
        from .knowledge.select import select

        terms = text.lower().split() if text else []
        units = select(self.ws, about or [], form, text if len(terms) == 1 else None, include_inactive, root=self.root,
                       include_contested=include_contested)
        out = []
        for unit in units:
            if scope and scope_of(unit) != scope:
                continue
            blob = " ".join(str(unit.get(k, "")) for k in ("id", "content", "condition")).lower()
            hits = sum(t in blob for t in terms) if len(terms) > 1 else 1
            if hits:
                out.append((hits, {"scope": scope_of(unit)} | {k: unit[k] for k in (
                    "id", "form", "status", "content", "condition", "about", "evidence") if k in unit}))
        return [u for _, u in sorted(out, key=lambda x: -x[0])][:limit]

    def knowledge_skills(self, text=None):
        from .knowledge.select import select_skills

        return select_skills(self.ws, text)

    def knowledge_index(self, prefix=None):
        from .knowledge.select import index

        return index(self.ws, self.root, prefix)

    def knowledge_trace(self, unit):
        from .knowledge import trace

        return trace(self.ws, unit)

    def knowledge_outline(self, draft=False):
        from .knowledge import by_unit, load_evidence
        from .knowledge import outline as ol

        items = ol.members(self.ws)
        current = None if draft else ol.load_outline(self.ws)
        return ol.render(current or ol.draft(self.ws), items, by_unit(load_evidence(self.ws), self.root))

    def knowledge_graph(self, entity=None, depth=1, view="summary"):
        from .knowledge import structure

        if entity:
            return structure.neighbors(self.ws, entity, depth)
        if view == "flows":
            return structure.load_flows(self.ws)
        if view == "cards":
            return structure.cards(self.ws)
        return structure.summary(self.ws)

    def knowledge_add(self, unit):
        units = self.units()
        if any(u["id"] == unit.get("id") for u in units):
            raise ValueError(f"unit id already exists: {unit.get('id')}")
        self.guarded_write(units + [unit])
        return {"added": unit["id"]}

    def knowledge_update(self, id, fields):
        units = self.units()
        if not any(u["id"] == id for u in units):
            raise ValueError(f"unknown unit: {id}")
        if "id" in fields:
            raise ValueError("id cannot change")
        self.guarded_write([{**u, **fields} if u["id"] == id else u for u in units])
        return {"updated": id, "fields": sorted(fields)}

    def evidence_add(self, unit, verdict, method, source, note="", inputs=None):
        from .knowledge import add_evidence
        from .knowledge.evidence import METHODS, VERDICTS, data_inputs

        if verdict not in VERDICTS or method not in METHODS:
            raise ValueError(f"verdict must be one of {sorted(VERDICTS)}, method one of {sorted(METHODS)}")
        entry = {"unit": unit, "verdict": verdict, "method": method, "source": source, "note": note,
                 "inputs": data_inputs(self.root, inputs) if inputs and self.root else {}}
        added = add_evidence(self.ws, [entry])[0]
        stale = [i for i in self.issues(self.units()) if i.startswith(f"{unit}:")]
        return {"evidence": added["id"], "unit_issues": stale}

    def knowledge_verify(self, units=None):
        from .knowledge import verify

        if self.root is None:
            raise ValueError("verify needs a workspace (checks run against data/)")
        return [{k: e[k] for k in ("id", "unit", "verdict", "note")} for e in verify(self.ws, units)]

    def knowledge_candidates(self):
        from .knowledge.consolidate import candidates

        return candidates(self.ws)

    def knowledge_check(self):
        from .knowledge import check_knowledge

        return check_knowledge(self.ws, root=self.root) or ["OK"]

    # ------------------------------------------------------------ tool layer and workspace

    def tool_list(self, modality=None):
        from .tools import list_tools

        return [{k: t[k] for k in ("name", "version", "kind", "modality", "stage")} for t in list_tools(modality)]

    def tool_card(self, name):
        from .tools import card

        return card(name)

    def tool_run(self, name, args, timeout=1800):
        from .tools import TOOLS_DIR

        python = os.environ.get(f"KNOSIS_{name.upper()}_PYTHON", sys.executable)
        result = subprocess.run([python, str(TOOLS_DIR / name / "run.py"), *args], cwd=self.ws,
                                capture_output=True, text=True, timeout=timeout)
        return {"returncode": result.returncode, "stdout": result.stdout[-20000:], "stderr": result.stderr[-5000:]}

    def workspace_next(self):
        from .workspace import next_prompt

        if self.root is None:
            raise ValueError("not a workspace")
        return next_prompt(self.ws)

    # ------------------------------------------------------------ protocol

    def call(self, name, arguments):
        if name not in TOOLS:
            raise ValueError(f"unknown tool: {name}")
        return getattr(self, name)(**arguments)

    def handle(self, message):
        method, mid = message.get("method"), message.get("id")
        if mid is None:  # notifications get no reply
            return None
        if method == "initialize":
            client = message.get("params", {}).get("protocolVersion", PROTOCOL)
            result = {"protocolVersion": client, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "knosis", "version": __version__},
                      "instructions": INSTRUCTIONS.format(kdir=self.ws)}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [{"name": n, "description": d, "inputSchema": schema(p, r)} for n, (d, p, r) in TOOLS.items()]}
        elif method == "tools/call":
            params = message.get("params", {})
            try:
                value = self.call(params["name"], params.get("arguments") or {})
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1, default=str)
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            except Exception as error:  # per MCP convention tool errors go in the result, so the agent can see and fix them
                result = {"content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}


INSTRUCTIONS = ("Knosis knowledge base at {kdir}: knowledge about the user's environment (projects, data, tools, servers) "
                "collected from earlier agent sessions, each with evidence. At the start of a non-trivial task, call "
                "knowledge_outline once, then knowledge_select with a few keywords for the task; treat inferred or contested "
                "units as hints to verify, not facts. Record a clear, verified finding with knowledge_add only when it will "
                "help later tasks; otherwise sessions are collected later by `knosis kb collect`.")


def schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required)}


S, B, I = {"type": "string"}, {"type": "boolean"}, {"type": "integer"}
LIST = {"type": "array", "items": {"type": "string"}}
SCOPE = {"type": "string", "enum": ["instance", "relation", "dataset", "method", "usage"]}
TOOLS = {
    "knowledge_select": ("Select knowledge for a task (κ and ontology units), with evidence counts. A single-word text matches substrings of id / content / condition; "
                         "multiple words (space-separated) select units matching any word, ranked by number of matched words. scope: object knowledge instance / relation / dataset, "
                         "meta-knowledge method (how knowledge was obtained) / usage (how to use knowledge well). Unresolved (contested) units are excluded by default.",
                         {"text": S, "about": LIST, "form": S, "scope": SCOPE, "include_inactive": B,
                          "include_contested": B, "limit": I}, ()),
    "knowledge_skills": ("List skills (how to apply knowledge to a class of tasks), with the usage units that evaluate them.", {"text": S}, ()),
    "knowledge_index": ("Object-keyed view: which knowledge sits on a data file / column / node and how often decisions cited it.", {"prefix": S}, ()),
    "knowledge_trace": ("How a unit was found: derivation chain and all evidence.", {"unit": S}, ("unit",)),
    "knowledge_outline": ("Knowledge outline (kb/outline.yaml) rendered as markdown; without an outline, or with draft=true, returns a draft generated by scope.",
                          {"draft": B}, ()),
    "knowledge_graph": ("Structured forms of the knowledge. No arguments: summary of the knowledge graph and flowcharts; entity: the subgraph within depth hops of an entity (id or name), "
                        "with cited units on edges; view=flows: all flowcharts (steps, checks, decisions, each citing units or skills); view=cards: rules and formulas grouped by object.",
                        {"entity": S, "depth": I, "view": {"type": "string", "enum": ["summary", "flows", "cards"]}}, ()),
    "knowledge_add": ("Add a κ (fields as in units.jsonl: id, content, form, provenance, status; optional scope, condition, about, "
                      "derived_from, meta). form: finding / fact / rule / formula / schema / tool / procedure. "
                      "Structure and provenance are checked before writing; additions that introduce new issues are rejected.",
                      {"unit": {"type": "object"}}, ("unit",)),
    "knowledge_update": ("Update fields of a κ (id cannot change); also checked before writing. Retract: {\"status\": \"retracted\"}; "
                         "dedup: {\"status\": \"merged\", \"merged_into\": primary unit}; supersede: {\"status\": \"stale\", "
                         "\"superseded_by\": new unit}; unresolved conflict: {\"status\": \"contested\", \"conflicts_with\": [other units]}.",
                         {"id": S, "fields": {"type": "object"}}, ("id", "fields")),
    "evidence_add": ("Record evidence for a κ (a skill's effect is written as a usage unit, not recorded on the skill). verdict: support / refute / undetermined / not_applicable; "
                     "method: check / tool / data / feedback / ablation / derivation / human. Returns issues the unit now needs addressed (e.g. a status change after refutation).",
                     {"unit": S, "verdict": S, "method": S, "source": S, "note": S, "inputs": LIST},
                     ("unit", "verdict", "method", "source")),
    "knowledge_verify": ("Rerun units' executable checks (check field) and record results as evidence; checks all units if units is omitted.", {"units": LIST}, ()),
    "knowledge_candidates": ("Consolidation candidates: likely duplicate unit pairs, possibly conflicting pairs on the same object, contested units. Hints only; you decide.", {}, ()),
    "knowledge_check": ("Check the whole knowledge layer: structure, status/evidence consistency, ontology references, skills, outline, dedup aliases and conflict marks.", {}, ()),
    "tool_list": ("Available tools (profile, joins, sql, fit, tabpfn, ultra, newton, autoschemakg, etc.).", {"modality": S}, ()),
    "tool_card": ("Tool description and usage.", {"name": S}, ("name",)),
    "tool_run": ("Run a tool from the workspace root; args as on the command line (e.g. [\"--tables\", \"data/\", \"--out\", \"stages/1_explore/profile\"]).",
                 {"name": S, "args": LIST, "timeout": I}, ("name", "args")),
    "workspace_next": ("Goal, inputs, deliverables and acceptance criteria of the current stage.", {}, ()),
}


def serve(ws, stdin=None, stdout=None) -> None:
    server = Server(ws)
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            reply = server.handle(json.loads(line))
        except json.JSONDecodeError as error:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(error)}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()
