"""NGDBench：含噪观测属性图 + 图问答。"""

from __future__ import annotations

import pickle
import re
from collections import Counter
from pathlib import Path

from . import register, render, split


def graph_summary(graph):
    nodes = Counter(attrs.get("label", "(无 label)") for _, attrs in graph.nodes(data=True))
    edges = Counter(attrs.get("label", "(无 label)") for *_, attrs in graph.edges(data=True))
    attributes = {}
    for _, attrs in graph.nodes(data=True):
        attributes.setdefault(attrs.get("label", "(无 label)"), set()).update(attrs)
    return {
        "graph_type": type(graph).__name__, "n_nodes": graph.number_of_nodes(),
        "n_edges": graph.number_of_edges(),
        "node_types": "\n".join(f"- {label}: {n}" for label, n in sorted(nodes.items())),
        "edge_types": "\n".join(f"- {label}: {n}" for label, n in sorted(edges.items())),
        "attributes": "\n".join(
            f"- {label}: {', '.join(sorted(keys - {'label'}))}" for label, keys in sorted(attributes.items())
        ),
    }


# BRIEF 里随题目形式变化的一段：题目给什么、答案形状怎么定。
# ---------------------------------------------------------------- NL 题面是否完整

LITERAL = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|(?<![\w.$])(-?\d+(?:\.\d+)?)(?![\w.])")


def literals(cypher: str) -> list[str]:
    """Cypher 里题目自带的常数（字符串、数字）；不算 LIMIT / SKIP、变长路径 `*1..3` 与 0 / 1。"""
    cypher = re.sub(r"\*\s*\d*\s*\.\.\s*\d*", "", re.sub(r"(?i)\b(LIMIT|SKIP)\s+\d+", "", cypher))
    return [s or d or n for s, d, n in LITERAL.findall(cypher) if (s or d) or n not in ("0", "1", "-1")]


def squash(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def mentioned(value: str, question: str) -> bool:
    if squash(value) and squash(value) in squash(question):
        return True
    try:
        number = float(value)
    except ValueError:
        return False
    return any(abs(number - float(n)) <= 1e-9 * max(1.0, abs(number))
               for n in re.findall(r"-?\d+(?:\.\d+)?", question.replace(",", "")))


def relation_words(cypher: str) -> set[str]:
    """关系类型里的动词（`Person_Own_Account` → own，`produces_output` → prod / outp），取前 4 个字母。"""
    words = set()
    for group in re.findall(r"\[[^\]]*:\s*`?([A-Za-z_|]+)`?", cypher):
        for rel in group.split("|"):
            parts = rel.lower().split("_")
            if len(parts) == 3 and rel[:1].isupper():  # 类型_动词_类型
                parts = parts[1:2]
            words |= {p[:4] for p in parts if len(p) > 2 and p not in {"entity", "has"}}
    return words


def nl_complete(question: str, cypher: str) -> bool:
    """自然语言题面是否交代了 Cypher 的全部常数，且提到了所用关系。上游 NL 常丢常数或描述错关系（NGD-Fin 约 73% 的题）。"""
    words = relation_words(cypher)
    return (all(mentioned(v, question) for v in literals(cypher))
            and (not words or any(w in squash(question) for w in words)))


NOISE_SECTION = {
    False: "## 可选交付：噪声断言\n\ndecide 阶段除答案外，还可以交 `stages/4_decide/noise.jsonl`：",
    True: "## 必交：噪声断言与识别方法\n\n识别噪声的方法本身也是知识：把它写成 `form=method` 的单元（步骤、适用条件、已知局限），"
          "附一个可执行检查 `knowledge/checks/<id>.py`（读 `data/graph.gpickle`，输出噪声断言），"
          "使换一张同类图的人也能照做。\n\ndecide 阶段除答案外，必须交 `stages/4_decide/noise.jsonl`：",
}

QUERY_HELP = {
    "cypher": """每题提供自然语言问题与 Cypher；答案以真实图为准，不一定等于在观测图上执行 Cypher 的结果。
答案的形状与 Cypher 的 `RETURN` 一致：返回多列时写成对象列表（键为返回别名，如 `[{"a": "Account:1", "cnt": 2}]`）；
返回单列时写成值的列表；只返回一个聚合值时写成标量。""",
    "nl": """每题只提供自然语言问题，不提供 Cypher：需要你自己把问题转成对 `data/graph.gpickle` 的查询。
答案以真实图为准，不一定等于在观测图上直接查询的结果。
答案的形状按问题所问：每个结果含多个值时写成对象列表（键名不限，如 `[{"a": "Account:1", "cnt": 2}]`）；
每个结果只有一个值时写成值的列表；只问一个聚合值时写成标量。""",
}


@register("ngdbench")
def export(ds, ws: Path, write_data=True, dev=50, limit=None, seed=0, question="cypher", noise_report=False, **opts) -> dict:
    """`dev`：用于反馈的开发题数；`limit`：抽样的测试题数（NGD-Fin 全量约 8700 题）。
    `question`：`cypher` 每题同时给自然语言问题与 Cypher；`nl` 只给自然语言问题，且只用题面完整（`nl_complete`）的题。
    `noise_report`：为真时噪声断言 `noise.jsonl` 是必交物，并要求把识别噪声的方法写成元知识。"""
    ws = Path(ws)
    clean = ds.read("clean")
    graph = ds.read("perturbed") if "perturbed" in ds.files else clean.copy()
    node_keys = {key for _, attrs in clean.nodes(data=True) for key in attrs}
    edge_keys = {key for *_, attrs in clean.edges(data=True) for key in attrs}
    # 属性键白名单来自 clean 图；加噪痕迹（is_noise / noise_similarity / original_name 等）会直接泄漏去噪答案。
    graph.graph.clear()
    for _, attrs in graph.nodes(data=True):
        for key in set(attrs) - node_keys:
            del attrs[key]
    for *_, attrs in graph.edges(data=True):
        for key in set(attrs) - edge_keys:
            del attrs[key]
    if write_data:
        (ws / "data").mkdir(parents=True, exist_ok=True)
        with (ws / "data/graph.gpickle").open("wb") as fh:
            pickle.dump(graph, fh)
    tasks = [
        {"id": task.id, "kind": task.kind, "question": task.meta.get("nlp") or task.input}
        | ({"cypher": task.meta.get("query", "")} if question == "cypher" else {})
        for task in ds.tasks if task.kind.startswith(("complex_query", "query_results"))
        and (question == "cypher" or (task.meta.get("nlp") and nl_complete(task.meta["nlp"], task.meta.get("query", ""))))
    ]
    n_examples = min(6, len(tasks))
    indices = {i * (len(tasks) - 1) // max(1, n_examples - 1) for i in range(n_examples)}
    examples = [task for i, task in enumerate(tasks) if i in indices]
    dev_tasks, tests = split([task for i, task in enumerate(tasks) if i not in indices], dev, limit, seed)
    return {
        "brief": render(
            f"ngdbench-{ds.scenario}.md", **graph_summary(graph),
            examples="\n".join(f"- [{t['kind']}] {t['question']}" for t in examples),
            query_help=QUERY_HELP[question], noise_section=NOISE_SECTION[bool(noise_report)],
        ),
        "extras": ["noise.jsonl"] if noise_report else [],
        "tasks": tests, "dev": dev_tasks, "holdout": [task["id"] for task in examples],
        "output": "predictions.jsonl", "modalities": ["graph"],
    }
