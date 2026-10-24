"""MCP 服务：把一个工作区（或知识库）的知识层与工具层以 MCP 工具暴露给 agent（stdio，JSON-RPC 2.0，每行一条消息）。

三层的分工：
- 工具（`knosis/tools/<name>/`）：独立进程，读数据、产出 inferred / observed 的 κ 注解，不改知识层；
- skill（`kb/skills/<name>/SKILL.md`）：知识库里「如何运用知识解某类任务」的流程，由 agent 写、讲怎么做；
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
        from .knowledge import data_root, layout

        # 工作区与知识库同布局（kb/ + evidence/）；知识库没有 data/，root 为 None。
        self.ws = Path(ws).resolve()
        self.lay = layout(self.ws)
        self.root = data_root(self.ws)

    # ------------------------------------------------------------ 知识层

    def units(self):
        from .knowledge import load_units

        return load_units(self.lay.units) if self.lay.units.exists() else []

    def issues(self, units):
        from .knowledge import by_unit, check_units, load_evidence

        return set(check_units(units, root=self.root, evidence=by_unit(load_evidence(self.ws), self.root)))

    def guarded_write(self, units):
        """只在不引入新问题时写回 units.jsonl。"""
        from .knowledge import write_units

        new = sorted(self.issues(units) - self.issues(self.units()))
        if new:
            raise ValueError("rejected, would introduce issues:\n" + "\n".join(new))
        write_units(self.lay.units, units)

    def knowledge_select(self, text=None, about=None, form=None, scope=None, include_inactive=False,
                         include_contested=False, limit=50):
        """`text` 含空格时按关键词检索：命中任一词即入选，按命中词数排序。"""
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
            except Exception as error:  # 工具错误按 MCP 约定放进结果，让 agent 看到并修正
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
    "knowledge_select": ("按任务筛选知识（κ 与本体单元），附证据计数。text 为一个词时在 id / content / condition 里找子串；"
                         "多个词（空格分隔）时命中任一词即入选，按命中词数排序。scope：对象知识 instance / relation / dataset，"
                         "元知识 method（怎么得到知识）/ usage（怎么用好知识）。矛盾未决（contested）的默认不给。",
                         {"text": S, "about": LIST, "form": S, "scope": SCOPE, "include_inactive": B,
                          "include_contested": B, "limit": I}, ()),
    "knowledge_skills": ("列出 skill（如何运用知识解某类任务），附评价它的 usage 单元。", {"text": S}, ()),
    "knowledge_index": ("以对象为键的视图：某个数据文件 / 列 / 节点上有哪些知识、被决策引用过几次。", {"prefix": S}, ()),
    "knowledge_trace": ("一条知识的发现途径：派生链与全部证据。", {"unit": S}, ("unit",)),
    "knowledge_outline": ("知识体系大纲（kb/outline.yaml）渲染成 markdown；没有大纲或 draft=true 时给按粒度生成的草稿。",
                          {"draft": B}, ()),
    "knowledge_add": ("新增一条 κ（字段同 units.jsonl：id、content、form、provenance、status，可选 scope、condition、about、"
                      "derived_from、meta）。form：finding / fact / rule / formula / schema / tool / procedure。"
                      "写入前检查结构与来源，引入新问题会被拒绝。",
                      {"unit": {"type": "object"}}, ("unit",)),
    "knowledge_update": ("修改一条 κ 的字段，不能改 id；同样先检查再写。撤回：{\"status\": \"retracted\"}；"
                         "去重：{\"status\": \"merged\", \"merged_into\": 主单元}；版本替换：{\"status\": \"stale\", "
                         "\"superseded_by\": 新单元}；矛盾未决：{\"status\": \"contested\", \"conflicts_with\": [对方]}。",
                         {"id": S, "fields": {"type": "object"}}, ("id", "fields")),
    "evidence_add": ("给一条 κ 记一条证据（skill 的效果写成 usage 单元，不直接记在 skill 上）。verdict：support / refute / undetermined / not_applicable；"
                     "method：check / tool / data / feedback / ablation / derivation / human。返回该单元因此需要处理的问题（如被反驳后要改状态）。",
                     {"unit": S, "verdict": S, "method": S, "source": S, "note": S, "inputs": LIST},
                     ("unit", "verdict", "method", "source")),
    "knowledge_verify": ("重跑单元的可执行检查（check 字段），结果记为证据；不给 units 时检查全部。", {"units": LIST}, ()),
    "knowledge_candidates": ("内化用的候选：疑似重复的单元对、同一对象上可能矛盾的单元对、有争议的单元。只是提示，由你判断。", {}, ()),
    "knowledge_check": ("检查整个知识层：结构、状态与证据一致、本体引用、skill、大纲、去重别名与矛盾标记。", {}, ()),
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
