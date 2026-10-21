"""导出器：把一个数据集变成工作区里 agent 可见的部分（数据 + BRIEF + 题目）；GT 留在原始数据目录。

新增数据集的工作区支持：在本目录写 `<name>.py`，用 `@register("<name>")` 装饰
`export(ds, ws, write_data=True, **opts) -> dict`，并加进下面的 import 列表。返回：

    brief        BRIEF.md 正文
    tasks        测试题（无答案），每项至少有 "id"；decide 阶段才写到 tasks/tasks.jsonl
    dev          开发题（无答案，与测试题不重叠），init 时写到 tasks/dev.jsonl，用于知识层反馈；可为空
    holdout      写进 BRIEF 当示例的题目 id
    output       decide 交付文件名：predictions.jsonl（每行 {id, answer}）或 predictions.csv（row_id, prediction, ...）；
                 没有下游预测时为 None
    modalities   用于挑选 TOOLS.md 里的工具，如 ["graph"]、["table"]、["tables"]

同样的 `opts` 必须给出同样的划分（`write_data=False` 用于 decide 阶段重新生成题目）。
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path
from string import Template
from typing import Callable

BRIEFS = Path(__file__).resolve().parents[1] / "templates" / "briefs"
EXPORTERS: dict[str, Callable] = {}


def register(name: str):
    def deco(fn):
        EXPORTERS[name] = fn
        return fn

    return deco


def place(src, dst) -> None:
    """把原始文件放进工作区：同一文件系统用硬链接（不占空间），否则复制。
    不用软链接：软链接会暴露原始目录的位置，GT 往往就在旁边。"""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:  # 跨文件系统
        shutil.copy2(src, dst)


def render(template, **values):
    return Template((BRIEFS / template).read_text(encoding="utf-8")).substitute(values)


def split(items, dev, limit=None, seed=0):
    """按 `seed` 打乱后切出 dev 与测试；`limit` 限制测试题数。保持原顺序输出。"""
    order = list(range(len(items)))
    random.Random(seed).shuffle(order)
    dev_idx, test_idx = set(order[:dev]), order[dev:]
    test_idx = set(test_idx[:limit] if limit is not None else test_idx)
    return [x for i, x in enumerate(items) if i in dev_idx], [x for i, x in enumerate(items) if i in test_idx]



from . import (  # noqa: E402,F401
    alphabench, bibench, burr, kramabench, llm_srbench, newtonbench, ngdbench, relbench, tabarena, text, traces,
)
