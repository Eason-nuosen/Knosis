"""agent 轨迹：把 Codex / Claude Code / 普通 agent 的轨迹统一成步骤序列，供 agent 从中提取知识。

统一格式（每行一步）：

    {"step": 7, "role": "assistant", "kind": "call", "name": "exec", "text": "..."}

`role`：user / assistant / tool / system；`kind`：message / reasoning / call / output。
文本过长时截断，`truncated` 记原长度。知识引用轨迹时写 `data/traces/<轨迹 id>.jsonl#step/<n>`。

支持的格式（`detect`）：
- codex：`~/.codex/sessions/**/rollout-*.jsonl`（`session_meta` + `response_item`）
- claude：Claude Code 的会话 JSONL（每行 `type: user / assistant`，`message.content` 为块列表）
- steps：逐步记录的 agent 轨迹（如 agent-rsi 的 AppWorld ReAct），`{instruction, steps: [{reasoning, response, code, env_feedback}]}`
- messages：OpenAI 风格消息，JSON 列表或 JSONL，每条 `{role, content[, tool_calls]}`；也接受 `{"messages": [...]}` 包一层
"""

from __future__ import annotations

import json
from pathlib import Path

LIMIT = 4000


def read(path) -> list:
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith(("[", "{")) and not text.lstrip().startswith("{\"timestamp\""):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and isinstance(data.get("steps"), list):
                return [data]
            return data if isinstance(data, list) else data.get("messages", [data])
        except json.JSONDecodeError:
            pass
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def detect(rows) -> str:
    first = rows[0]
    if first.get("type") == "session_meta":
        return "codex"
    if isinstance(first.get("steps"), list):
        return "steps"
    if any(r.get("type") in ("user", "assistant") and isinstance(r.get("message"), dict) for r in rows[:20]):
        return "claude"
    return "messages"


def step(role, kind, text, name=None) -> dict:
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    out = {"role": role, "kind": kind, "text": text[:LIMIT]}
    if name:
        out["name"] = name
    if len(text) > LIMIT:
        out["truncated"] = len(text)
    return out


def blocks(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text") or b.get("input_text") or b.get("output_text") or "" for b in content if isinstance(b, dict))


def codex(rows) -> list[dict]:
    steps = []
    for r in rows:
        p = r.get("payload", {})
        if r["type"] != "response_item":
            continue
        kind = p.get("type")
        if kind == "message" and p.get("role") != "developer":
            steps.append(step(p["role"], "message", blocks(p.get("content", []))))
        elif kind == "reasoning" and p.get("summary"):
            steps.append(step("assistant", "reasoning", blocks(p["summary"])))
        elif kind in ("custom_tool_call", "function_call"):
            steps.append(step("assistant", "call", p.get("input") or p.get("arguments", ""), p.get("name")))
        elif kind in ("custom_tool_call_output", "function_call_output"):
            out = p.get("output")
            steps.append(step("tool", "output", blocks(out) if isinstance(out, list) else out))
    return steps


def claude(rows) -> list[dict]:
    steps = []
    for r in rows:
        if r.get("type") not in ("user", "assistant") or not isinstance(r.get("message"), dict):
            continue
        role, content = r["message"]["role"], r["message"]["content"]
        for b in [{"type": "text", "text": content}] if isinstance(content, str) else content:
            if b["type"] == "text":
                steps.append(step(role, "message", b["text"]))
            elif b["type"] == "thinking" and b.get("thinking"):
                steps.append(step(role, "reasoning", b["thinking"]))
            elif b["type"] == "tool_use":
                steps.append(step(role, "call", b["input"], b["name"]))
            elif b["type"] == "tool_result":
                steps.append(step("tool", "output", blocks(b["content"]) if isinstance(b["content"], list) else b["content"]))
    return steps


def react(rows) -> list[dict]:
    """逐步记录：每步的思考、写出的代码（视为一次调用）、环境反馈；`input_messages` 是累积对话，不重复展开。"""
    run = rows[0]
    steps = [step("user", "message", run.get("instruction", ""))]
    for s in run["steps"]:
        if s.get("reasoning"):
            steps.append(step("assistant", "reasoning", s["reasoning"]))
        if s.get("code"):
            steps.append(step("assistant", "call", s["code"], "code"))
        elif s.get("response"):
            steps.append(step("assistant", "message", s["response"]))
        if s.get("env_feedback") is not None:
            steps.append(step("tool", "output", s["env_feedback"]))
    if "success" in run:
        steps.append(step("system", "message", f"任务结束：completed={run.get('completed')} success={run['success']}"))
    return steps


def messages(rows) -> list[dict]:
    steps = []
    for m in rows:
        role = m.get("role", "assistant")
        if m.get("content"):
            steps.append(step("tool" if role in ("tool", "function", "environment") else role,
                              "output" if role in ("tool", "function", "environment") else "message", blocks(m["content"]),
                              m.get("name")))
        for call in m.get("tool_calls") or []:
            fn = call.get("function", call)
            steps.append(step(role, "call", fn.get("arguments", ""), fn.get("name")))
    return steps


def normalize(path) -> list[dict]:
    rows = read(path)
    steps = {"codex": codex, "claude": claude, "steps": react, "messages": messages}[detect(rows)](rows)
    return [{"step": i, **s} for i, s in enumerate(steps)]


def render(steps, title="") -> str:
    """给人和 agent 读的 markdown：每步一节，编号即 `#step/<n>`。"""
    lines = [f"# {title}\n"] if title else []
    for s in steps:
        name = f" `{s['name']}`" if s.get("name") else ""
        cut = f"（截断，原 {s['truncated']} 字符）" if s.get("truncated") else ""
        lines.append(f"## step {s['step']} · {s['role']} · {s['kind']}{name}{cut}\n\n{s['text']}\n")
    return "\n".join(lines)
