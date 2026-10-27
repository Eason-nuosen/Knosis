"""Visualization: the agent writes a self-contained HTML page for a knowledge base or workspace; Knosis checks it and opens it.

    knosis knowledge view [--ws <dir>] [--request <what to show>] [--refresh] [--no-open]

The page lives in `<dir>/view/index.html` (outside `kb/` and `evidence/`; it is a rendering, not knowledge). If it already
exists and neither `--refresh` nor `--request` is given, it is just opened. Acceptance: the page exists, loads nothing from
the network (works offline and from `file://`), loads without uncaught JavaScript errors (checked in a headless
Chrome / Chromium when one is found; `KNOSIS_BROWSER` points to one), and the knowledge layer is unchanged; otherwise retry
once with the issues, then restore `kb/` and `evidence/` if they were changed and report the issues.
`knosis knowledge view --check` runs only the page checks (the agent uses it while writing the page).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path
from string import Template

from ..lang import t
from .layout import layout
from .units import INACTIVE, load_units

PAGE = "view/index.html"
# Remote scripts, stylesheets, images, fonts or ES imports: the page must work offline. Plain links (<a href>) are fine.
REMOTE = re.compile(r"""\bsrc\s*=\s*["']?(?:https?:)?//|<link\b[^>]*\bhref\s*=\s*["']?(?:https?:)?//|"""
                    r"""@import\s+(?:url\()?["']?(?:https?:)?//|\burl\(\s*["']?(?:https?:)?//|"""
                    r"""\bfrom\s+["'](?:https?:)?//|\bimport\(\s*["'](?:https?:)?//""", re.I)


def page(base) -> Path:
    return Path(base).resolve() / PAGE


def fingerprint(base) -> str:
    """Hash of everything under kb/ and evidence/, to check that rendering did not change the knowledge."""
    h = hashlib.sha256()
    for part in ("kb", "evidence"):
        for path in sorted((Path(base) / part).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.name != "consolidate.log":
                h.update(str(path.relative_to(base)).encode())
                h.update(path.read_bytes())
    return h.hexdigest()


def prompt(base, request=None) -> str:
    from ..workspace import templates
    from . import structure as st

    base = Path(base).resolve()
    lay = layout(base)
    units = load_units(lay.units) if lay.units.exists() else []
    flows = st.load_flows(base)
    n_active, n_inactive = sum(u.get('status') not in INACTIVE for u in units), sum(u.get('status') in INACTIVE for u in units)
    forms = [t(f"- Knowledge units: `kb/knowledge/units.jsonl` ({n_active} active, {n_inactive} inactive)",
               f"- 知识单元：`kb/knowledge/units.jsonl`（{n_active} 条活跃、{n_inactive} 条已失效）"),
             t("- Evidence ledger: `evidence/ledger.jsonl`; consolidation log: `evidence/consolidate.jsonl`",
               "- 证据账本：`evidence/ledger.jsonl`；内化记录：`evidence/consolidate.jsonl`")]
    forms += [t("- Outline: `kb/outline.yaml`", "- 大纲：`kb/outline.yaml`") if lay.outline.exists() else t("- Outline: none yet", "- 大纲：还没有")]
    forms += [t("- Knowledge graph: `kb/graph.json`", "- 知识图谱：`kb/graph.json`") if st.graph_path(base).exists()
              else t("- Knowledge graph: none yet", "- 知识图谱：还没有")]
    forms += [t(f"- Flowcharts: `kb/flows/*.json` ({len(flows)})", f"- 流程图：`kb/flows/*.json`（{len(flows)} 张）") if flows
              else t("- Flowcharts: none yet", "- 流程图：还没有")]
    if (base / "kb/skills").is_dir():
        forms.append(t("- skill: `kb/skills/<name>/SKILL.md`", "- skill：`kb/skills/<名字>/SKILL.md`"))
    if (base / "kb/knowledge/ontology").is_dir():
        forms.append(t("- Ontology: `kb/knowledge/ontology/`", "- 本体：`kb/knowledge/ontology/`"))
    values = {"base": base, "page": PAGE, "forms": "\n".join(forms),
              "request": t(f"\n## This request\n\n{request}\n", f"\n## 这次的要求\n\n{request}\n") if request else ""}
    return Template((templates() / "view.md").read_text(encoding="utf-8")).substitute(values)


def browser() -> str | None:
    """A Chrome / Chromium / Edge binary that can run headless, or None."""
    if os.environ.get("KNOSIS_BROWSER"):
        return os.environ["KNOSIS_BROWSER"]
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge"):
        if shutil.which(name):
            return shutil.which(name)
    apps = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    apps += sorted(str(p) for root in (Path.home() / "Library/Caches/ms-playwright", Path.home() / ".cache/ms-playwright")
                   for p in root.glob("chromium*/*/chrome-headless-shell"))
    return next((a for a in apps if Path(a).exists()), None)


def script_errors(path) -> list[str] | None:
    """Uncaught JavaScript errors while loading the page; None when no browser is available."""
    exe = browser()
    if exe is None:
        return None
    headless = [] if "headless-shell" in exe else ["--headless=new"]
    with tempfile.TemporaryDirectory() as profile:
        done = subprocess.run([exe, *headless, "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                               "--enable-logging=stderr", "--v=0", "--virtual-time-budget=5000", "--dump-dom",
                               Path(path).resolve().as_uri()], capture_output=True, text=True, timeout=120)
    return [line.split("CONSOLE", 1)[-1].lstrip(":()0123456789] ")[:300] for line in done.stderr.splitlines()
            if "CONSOLE" in line and "Uncaught" in line]


def issues(base, before) -> list[str]:
    path = page(base)
    if not path.exists() or not path.stat().st_size:
        return [f"missing {PAGE}"]
    found = []
    text = path.read_text(encoding="utf-8", errors="replace")
    remote = sorted({m.group(0) for m in REMOTE.finditer(text)})
    if remote:
        found.append(f"{PAGE} loads resources from the network ({', '.join(remote[:5])}); inline everything so it works offline")
    found += [f"{PAGE}: JavaScript error on load: {e}" for e in script_errors(path) or []]
    if before is not None and fingerprint(base) != before:
        found.append("the knowledge layer (kb/ or evidence/) was changed; rendering must only write under view/")
    return found


def run(path, request=None, refresh=False, open_page=True, agent="codex", model=None, effort=None) -> dict:
    from ..workspace.driver import agent_command
    from .consolidate import backup, restore

    base = Path(path).resolve()
    target = page(base)
    if target.exists() and not refresh and not request:
        result = {"page": str(target), "generated": False, "issues": []}
    else:
        if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
            raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
        target.parent.mkdir(parents=True, exist_ok=True)
        before, text, found, started = fingerprint(base), prompt(base, request), [], time.monotonic()
        env = {**os.environ, "KNOSIS_DEPTH": "1"}
        with tempfile.TemporaryDirectory() as tmp:
            backup(base, tmp)
            for attempt in range(2):
                with (target.parent / "agent.log").open("a", encoding="utf-8") as log:
                    log.write(f"\n===== view attempt {attempt + 1} =====\n")
                    log.flush()
                    done = subprocess.run(agent_command(agent, base, text, model, effort), cwd=base, env=env,
                                          stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                found = [f"{agent} exited with {done.returncode}"] if done.returncode else issues(base, before)
                if not found:
                    break
                text += t("\nAcceptance failed, please fix:\n", "\n验收未通过，请修正：\n") + "\n".join(found)
            if fingerprint(base) != before:
                restore(base, tmp)
        result = {"page": str(target), "generated": True, "issues": found, "seconds": round(time.monotonic() - started)}
    if open_page and not result["issues"]:
        webbrowser.open(target.as_uri())
    return result
