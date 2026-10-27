"""Data for the English version: translate Chinese text in the exported data to English, cached in site/i18n/en.json (Chinese source → English).

Knowledge units, evidence, graphs, flowcharts, outlines, skills etc. are written by agents in Chinese; when the page switches to EN it shows translations from this mapping.
Identifier fields (ids, unit references, paths, sources) are not translated. Only text missing from the cache is translated, in batches by Codex (`codex exec`, output constrained by a JSON Schema).

    python site/build.py --translate        # also fill in translations while exporting
"""
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CACHE = Path(__file__).with_name("i18n") / "en.json"
CJK = re.compile(r"[㐀-鿿]")
SKIP_KEYS = {"id", "unit", "src", "dst", "file", "path", "entity", "source", "provenance", "merged_into", "superseded_by",
             "created", "key", "dir", "rel", "kind", "type", "form", "status", "scope", "level", "verdict", "method", "op", "step"}
ID_LISTS = {"units", "used", "derived_from", "conflicts_with", "uses", "nodes", "about", "datasets", "traces"}
BATCH = 50
PROMPT = """Translate each string in the JSON array below from Chinese into clear, concise English for a technical product page.
These are knowledge units, evidence notes, graph labels and procedure steps written by an AI agent about datasets and tasks.
Rules:
- Return exactly one translation per input, in the same order (the array "t" must have {n} items).
- Keep code, identifiers, file paths, column / table / function names, numbers, formulas and English words unchanged.
- Keep status words as is: verified, inferred, observed, contested, retracted, stale, merged; keep κ.
- Translate meaning faithfully; do not add or drop claims; keep it as short as the original allows.
- Chinese punctuation becomes English punctuation.

Input:
{items}
"""
SCHEMA = {"type": "object", "properties": {"t": {"type": "array", "items": {"type": "string"}}},
          "required": ["t"], "additionalProperties": False}


def collect(*objs) -> list[str]:
    found = {}

    def walk(v, key=""):
        if isinstance(v, str):
            if CJK.search(v) and key not in SKIP_KEYS:
                found[v] = None
        elif isinstance(v, list):
            if key in ID_LISTS and all(isinstance(x, str) for x in v):
                return
            for x in v:
                walk(x, key)
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)

    for obj in objs:
        walk(obj)
    return list(found)


def load_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def save_cache(cache) -> None:
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")


def translate_batch(items: list[str]) -> list[str] | None:
    with tempfile.TemporaryDirectory() as tmp:
        schema, out = Path(tmp) / "schema.json", Path(tmp) / "out.json"
        schema.write_text(json.dumps(SCHEMA))
        prompt = PROMPT.format(n=len(items), items=json.dumps(items, ensure_ascii=False, indent=0))
        for _ in range(2):
            subprocess.run(["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "-C", tmp,
                            "-c", 'model_reasoning_effort="low"', "--output-schema", str(schema), "-o", str(out), prompt],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
            try:
                result = json.loads(out.read_text(encoding="utf-8"))["t"]
            except (OSError, ValueError, KeyError):
                continue
            if len(result) == len(items):
                return result
    return None


def translate(strings: list[str], workers=6) -> dict:
    """Translate text missing from the cache; return the Chinese → English mapping (restricted to `strings`)."""
    cache = load_cache()
    todo = [s for s in strings if s not in cache]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"translate: {len(strings)} strings, {len(todo)} new, {len(batches)} batches")
    with ThreadPoolExecutor(workers) as pool:
        for n, (items, result) in enumerate(zip(batches, pool.map(translate_batch, batches)), 1):
            if result is None:
                print(f"  batch {n}: failed, kept Chinese")
                continue
            cache.update(dict(zip(items, result)))
            save_cache(cache)
            print(f"  batch {n}/{len(batches)} done")
    return {s: cache[s] for s in strings if s in cache}
