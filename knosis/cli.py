"""Command line:

    knosis list | describe <dataset> | download <dataset>
    knosis ws init|next|check|status|goto|fork|run ...
    knosis tool list|card|run ...
    knosis ontology check <dir> | convert <dataset> <scenario> --out <dir> | units <dir>
    knosis knowledge check|verify|select|skills|index|trace|outline|candidates|consolidate|organize|compact|evidence add|evidence import ... [--ws <ws>]
    knosis kb init <dir> | merge <ws> --kb <dir> | import-ontology <src> --kb <dir> [--strip-gt]
    knosis kb collect --kb <dir> [--since 1d] [--source codex|claude] [--dry-run]
    knosis feedback submit <dev predictions file> [--ws <ws>] | list [--ws <ws>]
    knosis eval <ws>
    knosis install [--codex] [--claude] [--kb <dir>]
    knosis mcp [--ws <workspace or knowledge base>]
    knosis migrate <v0.4 workspace or knowledge base> ...
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from .data import data_dir, describe, list_datasets, list_scenarios

STAGE_NAMES = ["explore", "extract", "refine", "decide"]


def workspace_parser(sub):
    ws = sub.add_parser("ws", help="workspace").add_subparsers(dest="ws_cmd", required=True)
    init = ws.add_parser("init")
    init.add_argument("benchmark")
    init.add_argument("scenario")
    init.add_argument("--out")
    init.add_argument("--root", help="raw data directory")
    init.add_argument("--dev", type=int, help="number of dev tasks (for feedback); default set by the dataset")
    init.add_argument("--limit", type=int, help="number of test tasks to sample")
    init.add_argument("--seed", type=int)
    init.add_argument("-o", "--option", action="append", default=[], metavar="KEY=VALUE",
                      help="extra exporter arguments, e.g. repeat=0, task=driver-dnf; values parsed as YAML")
    init.add_argument("--feedback", choices=["answer", "score", "none"], default="answer")
    init.add_argument("--budget", type=int, default=20, help="maximum number of feedback submissions")
    init.add_argument("--feedback-full", action="store_true", help="every feedback submission must answer all dev tasks")
    init.add_argument("--kb", help="inherit initial knowledge from a standalone knowledge base (K_inherit)")
    init.add_argument("--kb-scope", help="inherit only these scopes, comma-separated, e.g. method or method,usage,skill")
    for name in ("next", "check", "status"):
        ws.add_parser(name).add_argument("dir", nargs="?", default=".")
    goto = ws.add_parser("goto")
    goto.add_argument("dir", nargs="?", default=".")
    goto.add_argument("stage", choices=STAGE_NAMES)
    fork = ws.add_parser("fork")
    fork.add_argument("dir")
    fork.add_argument("--out", required=True)
    fork.add_argument("--knowledge", default="K_final", help="none / K_inherit / K_0 / K_<n> / K_final")
    fork.add_argument("--drop", nargs="+", default=[], help="also drop these units (single-unit ablation)")
    run = ws.add_parser("run")
    run.add_argument("dir")
    run.add_argument("--agent", choices=["codex", "claude"], default="codex")
    run.add_argument("--model")
    run.add_argument("--effort", help="codex model_reasoning_effort, e.g. medium")
    run.add_argument("--note", help="experiment note appended to every stage prompt (e.g. force a tool)")
    run.add_argument("--stage", nargs="+", choices=STAGE_NAMES)
    run.add_argument("--rounds", type=int, default=1)
    run.add_argument("--consolidate", action="store_true", help="run consolidation after refine (dedup → conflict resolution → organize)")


def workspace_command(args):
    from . import workspace

    if args.ws_cmd == "init":
        import yaml

        options = {k: v for k, v in (("dev", args.dev), ("limit", args.limit), ("seed", args.seed), ("root", args.root))
                   if v is not None}
        options |= {k: yaml.safe_load(v) for k, v in (item.split("=", 1) for item in args.option)}
        print(workspace.init(args.benchmark, args.scenario, args.out, args.feedback, args.budget,
                             kb=args.kb, kb_scope=args.kb_scope.split(",") if args.kb_scope else None, feedback_full=args.feedback_full, **options))
    elif args.ws_cmd == "next":
        print(workspace.next_prompt(args.dir))
    elif args.ws_cmd == "status":
        print(json.dumps(workspace.status(args.dir), ensure_ascii=False, indent=2))
    elif args.ws_cmd == "goto":
        workspace.goto(args.dir, args.stage)
    elif args.ws_cmd == "check":
        report(workspace.check(args.dir))
    elif args.ws_cmd == "fork":
        print(workspace.fork(args.dir, args.out, args.knowledge, args.drop))
    elif args.ws_cmd == "run":
        workspace.run(args.dir, args.agent, args.stage, args.rounds, args.model, args.effort, args.note, args.consolidate)


def ontology_command(args):
    from . import load_dataset
    from .knowledge import ontology

    from .knowledge import all_ontology_units, ontology_docs

    # The directory is either an ontology itself or a workspace / knowledge base (ontologies under kb/knowledge/ontology/, possibly several subdirectories).
    docs = ontology_docs(args.dir) if (Path(args.dir) / "kb").is_dir() else {"": ontology.load_ontology(args.dir)}
    if args.onto_cmd == "check":
        report([issue for d in docs.values() for issue in ontology.check_ontology(d)])
    elif args.onto_cmd == "units":
        for unit in all_ontology_units(docs):
            print(json.dumps(unit, ensure_ascii=False))
    elif args.onto_cmd == "convert":
        convert = {"bibench": ontology.from_bibench, "relbench": ontology.from_relbench}[args.dataset]
        for path in ontology.write_ontology(args.out, {"semantic_model": convert(load_dataset(args.dataset, args.scenario))}):
            print(path)


def knowledge_parser(sub):
    kn = sub.add_parser("knowledge", help="knowledge layer: check, verify, select, evidence chains").add_subparsers(dest="kn_cmd", required=True)
    kn.add_parser("check").add_argument("--ws", default=".")
    verify = kn.add_parser("verify", help="rerun units' executable checks and record them as evidence")
    verify.add_argument("--ws", default=".")
    verify.add_argument("--unit", nargs="+")
    select = kn.add_parser("select", help="select knowledge for a task (including ontology elements), with evidence counts")
    select.add_argument("--ws", default=".")
    select.add_argument("--about", nargs="+", default=[])
    select.add_argument("--form")
    select.add_argument("--scope", choices=["instance", "relation", "dataset", "method", "usage"],
                        help="object knowledge instance / relation / dataset; meta-knowledge method (how knowledge was obtained) / usage (how to use knowledge well)")
    select.add_argument("--text")
    select.add_argument("--include-inactive", action="store_true")
    select.add_argument("--include-contested", action="store_true", help="also include unresolved (contested) units")
    skills = kn.add_parser("skills", help="list skills (how to apply knowledge to a class of tasks), with effect evidence counts")
    skills.add_argument("--ws", default=".")
    skills.add_argument("--text")
    skills.add_argument("--include-inactive", action="store_true")
    index = kn.add_parser("index", help="object-keyed view: which knowledge sits on a table / column / node and how often decisions cited it")
    index.add_argument("--ws", default=".")
    index.add_argument("--prefix", help="only objects starting with this, e.g. data/train.parquet#col/")
    trace = kn.add_parser("trace", help="how a unit was found: derivation chain and evidence")
    trace.add_argument("unit")
    trace.add_argument("--ws", default=".")
    outline = kn.add_parser("outline", help="knowledge outline (kb/outline.yaml), rendered as markdown")
    outline.add_argument("--ws", default=".", help="workspace or knowledge base")
    outline.add_argument("--draft", action="store_true", help="show the draft generated by scope")
    outline.add_argument("--write", action="store_true", help="write the draft to outline.yaml (refused if one exists)")
    kn.add_parser("candidates", help="consolidation candidates: likely duplicates, possible conflicts, contested units").add_argument("--ws", default=".")
    graph = kn.add_parser("graph", help="structured forms of the knowledge: knowledge graph, flowcharts, derivation graph, rule / formula cards")
    graph.add_argument("--ws", default=".", help="workspace or knowledge base")
    graph.add_argument("--entity", help="only the subgraph around one entity (id or name)")
    graph.add_argument("--depth", type=int, default=1)
    graph.add_argument("--view", choices=["summary", "graph", "flows", "derivation", "cards"], default="summary")
    for name, text in (("consolidate", "consolidation: dedup → conflict resolution → organize → structure; each step done by the agent, accepted and logged by Knosis"),
                       ("organize", "run only the organize step of consolidation (writes kb/outline.yaml)"),
                       ("compact", "compaction: the agent merges units that can be stated together into a primary unit (kept as aliases), reducing active units; --topic limits it to one topic")):
        cmd = kn.add_parser(name, help=text)
        cmd.add_argument("--ws", default=".", help="workspace or knowledge base")
        if name == "consolidate":
            cmd.add_argument("--steps", default="dedup,conflict,organize,structure",
                             help="comma-separated, from dedup / conflict / organize / structure (plus compact, not in the default)")
        if name == "compact":
            cmd.add_argument("--topic", help="only compact knowledge related to this topic (if omitted the agent decides what to compact)")
        cmd.add_argument("--agent", choices=["codex", "claude"], default="codex")
        cmd.add_argument("--model")
        cmd.add_argument("--effort")
        cmd.add_argument("--prompt-only", action="store_true", help="only print the prompt (of the first step), for the current session's agent to do itself")
    ev = kn.add_parser("evidence", help="evidence ledger").add_subparsers(dest="ev_cmd", required=True)
    add = ev.add_parser("add")
    add.add_argument("--ws", default=".")
    add.add_argument("--unit", required=True)
    add.add_argument("--verdict", required=True, choices=["support", "refute", "undetermined", "not_applicable"])
    add.add_argument("--method", required=True, choices=["check", "tool", "data", "feedback", "ablation", "derivation", "human"])
    add.add_argument("--source", required=True)
    add.add_argument("--note", default="")
    add.add_argument("--inputs", nargs="*", default=[], help="data files this evidence depends on (relative to the workspace); fingerprints are recorded")
    imp = ev.add_parser("import", help="import an evidence.jsonl written by a tool")
    imp.add_argument("file")
    imp.add_argument("--ws", default=".")
    ev.add_parser("list").add_argument("--ws", default=".")
    kb = sub.add_parser("kb", help="standalone knowledge base").add_subparsers(dest="kb_cmd", required=True)
    kb.add_parser("init").add_argument("dir")
    merge = kb.add_parser("merge")
    merge.add_argument("ws")
    merge.add_argument("--kb", required=True)
    merge.add_argument("--namespace", help="id prefix when merging workspaces from different datasets (e.g. newton), so same-named ids do not overwrite each other")
    onto = kb.add_parser("import-ontology")
    onto.add_argument("source", nargs="+")
    onto.add_argument("--kb", required=True)
    onto.add_argument("--strip-gt", action="store_true")
    collect = kb.add_parser("collect", help="have an agent extract knowledge from recent Codex / Claude Code sessions, write it to the knowledge base and consolidate")
    collect.add_argument("--kb", required=True)
    collect.add_argument("--since", default="1d", help="30m / 12h / 1d / 2w, or an ISO date")
    collect.add_argument("--source", choices=["codex", "claude"], default="codex")
    collect.add_argument("--limit", type=int, default=10, help="maximum sessions collected per run (oldest first)")
    collect.add_argument("--min-calls", type=int, default=3, help="skip sessions with fewer tool calls than this")
    collect.add_argument("--include-workspaces", action="store_true", help="also collect sessions run inside Knosis workspaces")
    collect.add_argument("--agent", choices=["codex", "claude"], default="codex")
    collect.add_argument("--model")
    collect.add_argument("--effort")
    collect.add_argument("--no-consolidate", action="store_true", help="skip consolidation after collecting (dedup, conflict resolution, organize)")
    collect.add_argument("--dry-run", action="store_true", help="only list the sessions that would be collected")


def knowledge_command(args):
    from . import knowledge
    from .knowledge import kb, select
    from .knowledge.evidence import data_inputs
    from .workspace import snapshots

    if args.cmd == "kb":
        if args.kb_cmd == "init":
            print(kb.init_kb(args.dir))
        elif args.kb_cmd == "merge":
            print(kb.merge(args.ws, args.kb, args.namespace))
        elif args.kb_cmd == "collect":
            from .knowledge import collect

            print(json.dumps(collect.run(args.kb, args.source, args.since, args.limit, args.agent, args.model, args.effort,
                                         args.include_workspaces, args.min_calls, not args.no_consolidate, args.dry_run),
                             ensure_ascii=False, indent=1))
        else:
            for source in args.source:
                print(source, json.dumps(kb.import_ontology(source, args.kb, args.strip_gt), ensure_ascii=False))
        return
    # Workspaces and knowledge bases share a layout (kb/ + evidence/); a knowledge base has no data/, so root is None.
    ws = Path(args.ws).resolve()
    kdir, root = ws, knowledge.data_root(ws)
    history = [u for d in snapshots(ws) for u in knowledge.load_units(knowledge.layout(d).units)] if root else []
    if args.kn_cmd in {"outline", "organize", "consolidate", "compact"}:
        outline_command(args)
    elif args.kn_cmd == "graph":
        from .knowledge import structure

        if args.entity:
            print(json.dumps(structure.neighbors(kdir, args.entity, args.depth), ensure_ascii=False, indent=1))
        elif args.view == "summary":
            print(structure.summary(kdir))
        else:
            data = {"graph": lambda: structure.load_graph(kdir), "flows": lambda: structure.load_flows(kdir),
                    "derivation": lambda: structure.derivation(kdir), "cards": lambda: structure.cards(kdir)}[args.view]()
            print(json.dumps(data, ensure_ascii=False, indent=1))
    elif args.kn_cmd == "candidates":
        from .knowledge.consolidate import candidates

        print(json.dumps(candidates(ws), ensure_ascii=False, indent=1))
    elif args.kn_cmd == "check":
        report(knowledge.check_knowledge(kdir, {u["id"] for u in history}, root=root))
    elif args.kn_cmd == "verify":
        if root is None:
            raise SystemExit("verify needs a workspace (checks run against data/)")
        for entry in knowledge.verify(ws, args.unit):
            print(entry["id"], entry["unit"], entry["verdict"], entry["note"][:200])
    elif args.kn_cmd == "select":
        from .knowledge import scope_of

        for unit in select.select(kdir, args.about, args.form, args.text, args.include_inactive, root=root,
                                  include_contested=args.include_contested):
            if args.scope and scope_of(unit) != args.scope:
                continue
            print(json.dumps({"scope": scope_of(unit)} | {k: unit[k] for k in (
                "id", "form", "status", "content", "condition", "about", "evidence") if k in unit}, ensure_ascii=False))
    elif args.kn_cmd == "skills":
        for skill in select.select_skills(kdir, args.text, args.include_inactive):
            print(json.dumps(skill, ensure_ascii=False))
    elif args.kn_cmd == "index":
        for anchor, entry in select.index(kdir, root, args.prefix).items():
            print(json.dumps({"anchor": anchor, **entry}, ensure_ascii=False))
    elif args.kn_cmd == "trace":
        print(knowledge.trace(kdir, args.unit, history), end="")
    elif args.ev_cmd == "add":
        entry = {"unit": args.unit, "verdict": args.verdict, "method": args.method, "source": args.source,
                 "note": args.note, "inputs": data_inputs(ws, args.inputs) if args.inputs and root else {}}
        print(knowledge.add_evidence(kdir, [entry])[0]["id"])
    elif args.ev_cmd == "import":
        for entry in knowledge.add_evidence(kdir, knowledge.load_units(args.file)):
            print(entry["id"], entry["unit"], entry["verdict"])
    else:
        for entry in knowledge.load_evidence(kdir):
            print(entry["id"], entry["unit"], entry["verdict"], entry["method"], entry["source"], entry.get("note", "")[:120])


def outline_command(args):
    from .knowledge import by_unit, consolidate, load_evidence, outline

    kdir, root = consolidate.resolve_base(args.ws)
    if args.kn_cmd in {"organize", "consolidate", "compact"}:
        steps = args.steps.split(",") if args.kn_cmd == "consolidate" else [args.kn_cmd]
        topic = getattr(args, "topic", None)
        if args.prompt_only:
            print(consolidate.prompt(args.ws, steps[0], topic))
            return
        results = consolidate.run(args.ws, steps, args.agent, args.model, args.effort, topic)
        report([f"{r['step']}: {i}" for r in results for i in r["issues"]])
        return
    current = None if args.draft or args.write else outline.load_outline(kdir)
    if args.write:
        if outline.load_outline(kdir) is not None:
            raise SystemExit(f"{knowledge_layout(kdir).outline} exists")
        print(outline.write_outline(kdir, outline.draft(kdir)))
        return
    print(outline.render(current or outline.draft(kdir), outline.members(kdir), by_unit(load_evidence(kdir), root)))


def knowledge_layout(path):
    from .knowledge import layout

    return layout(path)


def report(issues):
    print("\n".join(issues) if issues else "OK")
    if issues:
        raise SystemExit(1)


BEGIN, END = "# >>> knosis (managed by `knosis install --kb`)", "# <<< knosis"


def mcp_command(kb) -> list[str]:
    import sys

    return [sys.executable, "-m", "knosis.cli", "mcp", "--ws", str(Path(kb).expanduser().resolve())]


def install_codex_mcp(config: Path, kb) -> Path:
    """Write (or replace) a knosis MCP block in Codex's config.toml; approvals are allowed, otherwise calls under `codex exec` are rejected."""
    command, *args = mcp_command(kb)
    block = "\n".join([BEGIN, "[mcp_servers.knosis]", f"command = {json.dumps(command)}", f"args = {json.dumps(args)}",
                       'default_tools_approval_mode = "approve"', END]) + "\n"
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    if BEGIN in text:
        text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):].lstrip("\n")
    elif "[mcp_servers.knosis]" in text:
        raise SystemExit(f"{config} already has [mcp_servers.knosis] not managed by knosis; remove it first")
    else:
        text = text + ("\n" if text and not text.endswith("\n") else "") + ("\n" if text else "") + block
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    return config


def install_skill(codex=False, claude=False, home=None, kb=None):
    from .workspace import TEMPLATES

    home = Path(home or Path.home())
    both = not codex and not claude
    roots = []
    if codex or both:
        roots.extend([home / ".agents", Path(os.environ.get("CODEX_HOME", home / ".codex"))])
    if claude or both:
        roots.append(home / ".claude")
    for root in roots:
        target = root / "skills/knosis/SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / "SKILL.md", target)
        print(target)
    if kb and (codex or both):
        print(install_codex_mcp(Path(os.environ.get("CODEX_HOME", home / ".codex")) / "config.toml", kb))
    if kb and (claude or both):
        import shlex

        print("Claude Code: run claude mcp add -s user knosis -- " + " ".join(map(shlex.quote, mcp_command(kb))))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="knosis")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="datasets")
    sub.add_parser("describe").add_argument("name")
    dl = sub.add_parser("download")
    dl.add_argument("name")
    dl.add_argument("--include", action="append", help="HF allow_patterns or OpenML dataset name; repeatable")
    workspace_parser(sub)
    tools = sub.add_parser("tool", help="tools").add_subparsers(dest="tool_cmd", required=True)
    tools.add_parser("list").add_argument("--modality")
    tools.add_parser("card").add_argument("name")
    tool_run = tools.add_parser("run")
    tool_run.add_argument("name")
    tool_run.add_argument("args", nargs=argparse.REMAINDER)
    onto = sub.add_parser("ontology", help="ontology").add_subparsers(dest="onto_cmd", required=True)
    onto.add_parser("check").add_argument("dir")
    onto.add_parser("units").add_argument("dir")
    convert = onto.add_parser("convert")
    convert.add_argument("dataset", choices=["bibench", "relbench"])
    convert.add_argument("scenario")
    convert.add_argument("--out", required=True)
    knowledge_parser(sub)
    fb = sub.add_parser("feedback", help="dev task feedback").add_subparsers(dest="fb_cmd", required=True)
    fb_submit = fb.add_parser("submit")
    fb_submit.add_argument("file")
    fb_submit.add_argument("--ws", default=".")
    fb.add_parser("list").add_argument("--ws", default=".")
    sub.add_parser("eval", help="evaluate decide outputs").add_argument("dir", nargs="?", default=".")
    install = sub.add_parser("install", help="install the Codex / Claude Code skill")
    install.add_argument("--codex", action="store_true")
    install.add_argument("--claude", action="store_true")
    install.add_argument("--kb", help="also install an MCP server for this knowledge base into Codex (writes config.toml) and print the Claude Code command")
    sub.add_parser("mcp", help="expose the knowledge and tool layers over MCP (stdio)").add_argument("--ws", default=".", help="workspace or knowledge base")
    sub.add_parser("migrate", help="convert a v0.4-layout workspace or knowledge base to v0.5 (kb/ + evidence/)").add_argument("dirs", nargs="+")
    args = p.parse_args(argv)

    if args.cmd == "list":
        for name in list_datasets():
            print(f"{name:12} {'local' if data_dir(name).exists() else '-':6} {describe(name).splitlines()[0].lstrip('# ')}")
    elif args.cmd == "describe":
        print(describe(args.name))
        print(f"\n## scenarios\n{list_scenarios(args.name)}")
    elif args.cmd == "download":
        from .data.download import download

        print(download(args.name, args.include))
    elif args.cmd == "ws":
        workspace_command(args)
    elif args.cmd == "ontology":
        ontology_command(args)
    elif args.cmd in {"knowledge", "kb"}:
        knowledge_command(args)
    elif args.cmd == "feedback":
        from .knowledge import feedback

        if args.fb_cmd == "submit":
            record = feedback.submit(args.ws, args.file)
            print(json.dumps({"id": record["id"], "metrics": record["metrics"], "items": record["items"][:50]},
                             ensure_ascii=False, indent=1, default=str))
            print(f"Full record: evidence/feedback/{record['id']}.json")
        else:
            for record in feedback.records(args.ws):
                print(record["id"], record["submitted"], json.dumps(record["metrics"], ensure_ascii=False)[:200])
    elif args.cmd == "eval":
        from .decision import evaluate

        print(json.dumps(evaluate(args.dir), ensure_ascii=False, indent=2))
    elif args.cmd == "install":
        install_skill(args.codex, args.claude, kb=args.kb)
    elif args.cmd == "migrate":
        from .knowledge.migrate import migrate

        for directory in args.dirs:
            print(json.dumps(migrate(directory), ensure_ascii=False))
    elif args.cmd == "mcp":
        from .mcp import serve

        serve(args.ws)
    elif args.cmd == "tool":
        from .tools import card, list_tools, run_tool

        if args.tool_cmd == "list":
            for tool in list_tools(args.modality):
                print(f"{tool['name']:10} {tool['kind']:8} {', '.join(tool['modality']):14} @{tool['version']}")
        elif args.tool_cmd == "card":
            print(card(args.name))
        elif args.tool_cmd == "run":
            raise SystemExit(run_tool(args.name, args.args[1:] if args.args[:1] == ["--"] else args.args))


if __name__ == "__main__":
    main()
