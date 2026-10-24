"""文本语料打分：没有下游 GT，评知识层本身——单元构成，以及来源能否定位回 `data/` 里的原文片段。

来源写法 `data/<文件>#<start>-<end>`（字符偏移，左闭右开）；单元 `meta.quote` 若给出，必须出现在该片段里。
"""

from __future__ import annotations

import re
from collections import Counter

from ..knowledge import load_units, layout
from . import register

SPAN = re.compile(r"^(data/.+)#(\d+)-(\d+)$")


def check_unit(ws, unit) -> dict:
    spans = [SPAN.match(s.strip()) for s in unit["provenance"].split(";")]
    spans = [m for m in spans if m]
    texts = []
    for m in spans:
        path, start, end = ws / m.group(1), int(m.group(2)), int(m.group(3))
        text = path.read_text(encoding="utf-8") if path.is_file() else None
        texts.append(text[start:end] if text is not None and 0 <= start < end <= len(text) else None)
    quote = unit.get("meta", {}).get("quote")
    supported = None if quote is None else any(t is not None and quote in t for t in texts)
    resolvable = sum(t is not None for t in texts)
    return {"id": unit["id"], "form": unit["form"], "status": unit["status"], "spans": len(spans),
            "resolvable": resolvable, "quote_supported": supported,
            "ok": bool(spans) and resolvable == len(spans) and supported is not False, "gold": None}


@register("text")
def score(ws, state, ds, path, ids) -> dict:
    units = load_units(layout(ws).units)
    items = [check_unit(ws, u) for u in units]
    spans = sum(i["spans"] for i in items)
    quoted = [i for i in items if i["quote_supported"] is not None]
    metrics = {
        "units": len(units), "by_form": dict(Counter(u["form"] for u in units)),
        "by_status": dict(Counter(u["status"] for u in units)),
        "with_text_span": sum(i["spans"] > 0 for i in items) / max(1, len(items)),
        "span_resolvable": sum(i["resolvable"] for i in items) / max(1, spans),
        "quote_supported": sum(i["quote_supported"] for i in quoted) / len(quoted) if quoted else None,
        "grounded": sum(i["ok"] for i in items) / max(1, len(items)),
    }
    return {"metrics": metrics, "items": items, "reference": {}}
