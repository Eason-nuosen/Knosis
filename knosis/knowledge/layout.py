"""Directory layout of the knowledge layer (v0.5): workspaces and standalone knowledge bases share it; two parts.

    <root>/
    ├── kb/                         knowledge body: permanent, inheritable, selectable
    │   ├── knowledge/
    │   │   ├── units.jsonl         κ: object knowledge (instance / relation / dataset) + meta-knowledge (method / usage)
    │   │   └── ontology/           structured knowledge (OSI three layers: semantic model / concepts / mapping)
    │   ├── skills/<name>/SKILL.md   usage procedures
    │   ├── outline.yaml            knowledge outline (tree)
│   ├── graph.json              knowledge graph: entities and relations, each edge cites units
│   └── flows/<name>.json        flowcharts: steps, checks, decisions, each node cites units or skills
    └── evidence/                   full record of sources and verification
        ├── ledger.jsonl            evidence ledger
        ├── consolidate.jsonl       consolidation log (dedup, conflict handling, organizing)
        ├── checks/                 executable checks
        ├── feedback/               dev feedback records
        └── traces/                 source traces (sessions collected into the knowledge base)

`root` is a workspace root, a knowledge base root, or a knowledge version snapshot inside a workspace (`stages/<stage>/`).
"""

from __future__ import annotations

from pathlib import Path

UNITS = "kb/knowledge/units.jsonl"
ONTOLOGY = "kb/knowledge/ontology"
SKILLS = "kb/skills"
OUTLINE = "kb/outline.yaml"
LEDGER = "evidence/ledger.jsonl"
ACTIONS = "evidence/consolidate.jsonl"
CHECKS = "evidence/checks"
FEEDBACK = "evidence/feedback"
TRACES = "evidence/traces"
PARTS = ("kb", "evidence")


class Layout:
    def __init__(self, root):
        self.root = Path(root)

    def __getattr__(self, name):
        rel = {"units": UNITS, "ontology": ONTOLOGY, "skills": SKILLS, "outline": OUTLINE, "ledger": LEDGER,
               "actions": ACTIONS, "checks": CHECKS, "feedback": FEEDBACK, "traces": TRACES,
               "kb": "kb", "knowledge": "kb/knowledge", "evidence": "evidence"}.get(name)
        if rel is None:
            raise AttributeError(name)
        return self.root / rel


def layout(root) -> Layout:
    """Layout object; hints at migration when it finds the old v0.4 layout (`knowledge/units.jsonl` or `units.jsonl` at the root)."""
    root = Path(root)
    if not (root / "kb").is_dir() and ((root / "knowledge/units.jsonl").exists() or (root / "units.jsonl").exists()):
        raise RuntimeError(f"{root} uses the v0.4 layout; run `knosis migrate {root}` first")
    return Layout(root)


def is_workspace(root) -> bool:
    return (Path(root) / ".knosis/state.json").exists()


def data_root(root):
    """Root used to check `data/` sources and data fingerprints: itself for a workspace; none for knowledge bases and snapshots (returns None)."""
    return Path(root).resolve() if is_workspace(root) else None


def ensure(root) -> Layout:
    lay = Layout(root)
    for path in (lay.knowledge, lay.skills, lay.checks, lay.feedback):
        path.mkdir(parents=True, exist_ok=True)
    for path in (lay.units, lay.ledger):
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return lay
