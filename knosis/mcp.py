"""MCP 服务：把一个工作区（或知识库）的知识层与工具层以 MCP 工具暴露给 agent（stdio，JSON-RPC 2.0，每行一条消息）。

三层的分工：
- 工具（`knosis/tools/<name>/`）：独立进程，读数据、产出 inferred / observed 的 κ 注解，不改知识层；
- skill（`knowledge/skills/<name>/SKILL.md`）：知识层里「如何运用知识解某类任务」的记录，由 agent 写、讲有没有效；
- MCP（本模块）：协议适配，不实现功能。知识操作直接调用 `knosis.knowledge`，工具经 `tool_run` 以子进程运行。

写操作（`knowledge_add`、`knowledge_update`、`evidence_add`）在写入前用 `check_units` 检查，引入新问题就拒绝。
不暴露 `eval`（测试题评测不属于 agent 可用的操作）。

    knosis mcp --ws <工作区或知识库>
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
        self.ws = Path(ws).resolve()
        # 工作区的知识层在 knowledge/；知识库本身就是知识层目录，没有 data/。
        is_ws = (self.ws / "knowledge").is_dir()
        self.kdir = self.ws / "knowledge" if is_ws else self.ws
        self.root = self.ws if is_ws else None

    # ------------------------------------------------------------ 知识层

    def units(self):
        from .knowledge import load_units

        path = self.kdir / "units.jsonl"
        return load_units(path) if path.exists() else []

    def issues(self, units):
        from .knowledge import by_unit, check_units, load_evidence

        return set(check_units(units, root=self.root, evidence=by_unit(load_evidence(self.kdir), self.root)))

    def guarded_write(self, units):
        """只在不引入新问题时写回 units.jsonl。"""
        from .knowledge import write_units

        new = sorted(self.issues(units) - self.issues(self.units()))
        if new:
            raise ValueError("rejected, would introduce issues:\n" + "\n".join(new))
        write_units(self.kdir / "units.jsonl", units)

    def knowledge_select(self, text=None, about=None, form=None, scope=None, include_inactive=False, limit=50):
        from .knowledge import scope_of
        from .knowledge.select import select

        out = []
        for unit in select(self.kdir, about or [], form, text, include_inactive, root=self.root):
            if scope and scope_of(unit) != scope:
                continue
            out.append({"scope": scope_of(unit)} | {k: unit[k] for k in (
                "id", "form", "status", "content", "condition", "about", "evidence") if k in unit})
        return out[:limit]

    def knowledge_skills(self, text=None):
        from .knowledge.select import select_skills

        return select_skills(self.kdir, text)

    def knowledge_index(self, prefix=None):
        from .knowledge.select import index

        return index(self.kdir, self.root, prefix)

    def knowledge_trace(self, unit):
        from .knowledge import trace

        return trace(self.kdir, unit)

    def knowledge_outline(self, draft=False):
        from .knowledge import by_unit, load_evidence
        from .knowledge import outline as ol

        items = ol.members(self.kdir)
        current = None if draft else ol.load_outline(self.kdir)
        return ol.render(current or ol.draft(self.kdir), items, by_unit(load_evidence(self.kdir), self.root))

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
        added = add_evidence(self.kdir, [entry])[0]
        stale = [i for i in self.issues(self.units()) if i.startswith(f"{unit}:")]
        return {"evidence": added["id"], "unit_issues": stale}

    def knowledge_verify(self, units=None):
        from .knowledge import verify

        if self.root is None:
            raise ValueError("verify needs a workspace (checks run against data/)")
        return [{k: e[k] for k in ("id", "unit", "verdict", "note")} for e in verify(self.ws, units)]

    def knowledge_check(self):
        from .knowledge import check_knowledge

        return check_knowledge(self.kdir, root=self.root) or ["OK"]

    # ------------------------------------------------------------ 工具层与工作区

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

    # ------------------------------------------------------------ 协议

    def call(self, name, arguments):
        if name not in TOOLS:
            raise ValueError(f"unknown tool: {name}")
        return getattr(self, name)(**arguments)

    def handle(self, message):
        method, mid = message.get("method"), message.get("id")
        if mid is None:  # 通知不回复
            return None
        if method == "initialize":
            client = message.get("params", {}).get("protocolVersion", PROTOCOL)
            result = {"protocolVersion": client, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "knosis", "version": __version__},
                      "instructions": f"Knosis knowledge layer at {self.kdir}"}
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
            except Exception as error:  # 工具错误按 MCP 约定放进结果，让 agent 看到并修正
                result = {"content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required)}


S, B, I = {"type": "string"}, {"type": "boolean"}, {"type": "integer"}
LIST = {"type": "array", "items": {"type": "string"}}
SCOPE = {"type": "string", "enum": ["instance", "relation", "dataset", "method", "utility"]}
TOOLS = {
    "knowledge_select": ("按任务筛选知识（κ 与本体单元），附证据计数。text 在 id / content / condition 里找子串。",
                         {"text": S, "about": LIST, "form": S, "scope": SCOPE, "include_inactive": B, "limit": I}, ()),
    "knowledge_skills": ("列出 skill（如何运用知识解某类任务），附效果证据计数。", {"text": S}, ()),
    "knowledge_index": ("以对象为键的视图：某个数据文件 / 列 / 节点上有哪些知识、被决策引用过几次。", {"prefix": S}, ()),
    "knowledge_trace": ("一条知识的发现途径：派生链与全部证据。", {"unit": S}, ("unit",)),
    "knowledge_outline": ("知识体系大纲（knowledge/outline.yaml）渲染成 markdown；没有大纲或 draft=true 时给按粒度生成的草稿。",
                          {"draft": B}, ()),
    "knowledge_add": ("新增一条 κ（字段同 units.jsonl：id、content、form、provenance、status，可选 scope、condition、about、"
                      "derived_from、meta）。写入前检查结构与来源，引入新问题会被拒绝。",
                      {"unit": {"type": "object"}}, ("unit",)),
    "knowledge_update": ("修改一条 κ 的字段（如撤回：{\"status\": \"retracted\"}），不能改 id；同样先检查再写。",
                         {"id": S, "fields": {"type": "object"}}, ("id", "fields")),
    "evidence_add": ("给一条 κ 或 skill:<名字> 记一条证据。verdict：support / refute / undetermined / not_applicable；"
                     "method：check / tool / data / feedback / ablation / derivation / human。返回该单元因此需要处理的问题（如被反驳后要改状态）。",
                     {"unit": S, "verdict": S, "method": S, "source": S, "note": S, "inputs": LIST},
                     ("unit", "verdict", "method", "source")),
    "knowledge_verify": ("重跑单元的可执行检查（check 字段），结果记为证据；不给 units 时检查全部。", {"units": LIST}, ()),
    "knowledge_check": ("检查整个知识层：结构、状态与证据一致、本体引用、skill、大纲。", {}, ()),
    "tool_list": ("可用工具（profile、joins、sql、fit、tabpfn、ultra、newton、autoschemakg 等）。", {"modality": S}, ()),
    "tool_card": ("工具说明与用法。", {"name": S}, ("name",)),
    "tool_run": ("在工作区根目录运行一个工具，args 同命令行（如 [\"--tables\", \"data/\", \"--out\", \"stages/1_explore/profile\"]）。",
                 {"name": S, "args": LIST, "timeout": I}, ("name", "args")),
    "workspace_next": ("当前阶段的目标、输入、交付与验收标准。", {}, ()),
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
