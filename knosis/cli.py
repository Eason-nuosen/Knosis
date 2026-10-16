"""命令行：

    knosis list | describe <dataset> | download <dataset>
    knosis ws init|next|check|status|goto|fork|run ...
    knosis tool list|card|run ...
    knosis ontology check <dir> | convert <dataset> <scenario> --out <dir> | units <dir>
    knosis feedback submit <dev 预测文件> [--ws <ws>] | list [--ws <ws>]
    knosis eval <ws>
    knosis install [--codex] [--claude]
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
    ws = sub.add_parser("ws", help="工作区").add_subparsers(dest="ws_cmd", required=True)
    init = ws.add_parser("init")
    init.add_argument("benchmark")
    init.add_argument("scenario")
    init.add_argument("--out")
    init.add_argument("--root", help="原始数据目录")
    init.add_argument("--dev", type=int, help="开发题（反馈用）数量；默认由数据集决定")
    init.add_argument("--limit", type=int, help="抽样的测试题数")
    init.add_argument("--seed", type=int)
    init.add_argument("-o", "--option", action="append", default=[], metavar="KEY=VALUE",
                      help="导出器的其他参数，如 repeat=0、task=driver-dnf；值按 YAML 解析")
    init.add_argument("--feedback", choices=["answer", "score", "none"], default="answer")
    init.add_argument("--budget", type=int, default=20, help="反馈提交次数上限")
    for name in ("next", "check", "status"):
        ws.add_parser(name).add_argument("dir", nargs="?", default=".")
    goto = ws.add_parser("goto")
    goto.add_argument("dir", nargs="?", default=".")
    goto.add_argument("stage", choices=STAGE_NAMES)
    fork = ws.add_parser("fork")
    fork.add_argument("dir")
    fork.add_argument("--out", required=True)
    fork.add_argument("--knowledge", default="K_final", help="none / K_0 / K_<n> / K_final")
    run = ws.add_parser("run")
    run.add_argument("dir")
    run.add_argument("--agent", choices=["codex", "claude"], default="codex")
    run.add_argument("--model")
    run.add_argument("--stage", nargs="+", choices=STAGE_NAMES)
    run.add_argument("--rounds", type=int, default=1)


def workspace_command(args):
    from . import workspace

    if args.ws_cmd == "init":
        import yaml

        options = {k: v for k, v in (("dev", args.dev), ("limit", args.limit), ("seed", args.seed), ("root", args.root))
                   if v is not None}
        options |= {k: yaml.safe_load(v) for k, v in (item.split("=", 1) for item in args.option)}
        print(workspace.init(args.benchmark, args.scenario, args.out, args.feedback, args.budget, **options))
    elif args.ws_cmd == "next":
        print(workspace.next_prompt(args.dir))
    elif args.ws_cmd == "status":
        print(json.dumps(workspace.status(args.dir), ensure_ascii=False, indent=2))
    elif args.ws_cmd == "goto":
        workspace.goto(args.dir, args.stage)
    elif args.ws_cmd == "check":
        report(workspace.check(args.dir))
    elif args.ws_cmd == "fork":
        print(workspace.fork(args.dir, args.out, args.knowledge))
    elif args.ws_cmd == "run":
        workspace.run(args.dir, args.agent, args.stage, args.rounds, args.model)


def ontology_command(args):
    from . import load_dataset
    from .knowledge import ontology

    if args.onto_cmd == "check":
        report(ontology.check_ontology(ontology.load_ontology(args.dir)))
    elif args.onto_cmd == "units":
        for unit in ontology.ontology_units(ontology.load_ontology(args.dir), prefix=args.dir):
            print(json.dumps(unit, ensure_ascii=False))
    elif args.onto_cmd == "convert":
        convert = {"bibench": ontology.from_bibench, "relbench": ontology.from_relbench}[args.dataset]
        for path in ontology.write_ontology(args.out, {"semantic_model": convert(load_dataset(args.dataset, args.scenario))}):
            print(path)


def report(issues):
    print("\n".join(issues) if issues else "OK")
    if issues:
        raise SystemExit(1)


def install_skill(codex=False, claude=False, home=None):
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


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="knosis")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="数据集")
    sub.add_parser("describe").add_argument("name")
    dl = sub.add_parser("download")
    dl.add_argument("name")
    dl.add_argument("--include", action="append", help="HF allow_patterns 或 OpenML 数据集名，可重复")
    workspace_parser(sub)
    tools = sub.add_parser("tool", help="工具").add_subparsers(dest="tool_cmd", required=True)
    tools.add_parser("list").add_argument("--modality")
    tools.add_parser("card").add_argument("name")
    tool_run = tools.add_parser("run")
    tool_run.add_argument("name")
    tool_run.add_argument("args", nargs=argparse.REMAINDER)
    onto = sub.add_parser("ontology", help="本体").add_subparsers(dest="onto_cmd", required=True)
    onto.add_parser("check").add_argument("dir")
    onto.add_parser("units").add_argument("dir")
    convert = onto.add_parser("convert")
    convert.add_argument("dataset", choices=["bibench", "relbench"])
    convert.add_argument("scenario")
    convert.add_argument("--out", required=True)
    fb = sub.add_parser("feedback", help="dev 题反馈").add_subparsers(dest="fb_cmd", required=True)
    fb_submit = fb.add_parser("submit")
    fb_submit.add_argument("file")
    fb_submit.add_argument("--ws", default=".")
    fb.add_parser("list").add_argument("--ws", default=".")
    sub.add_parser("eval", help="评测 decide 产物").add_argument("dir", nargs="?", default=".")
    install = sub.add_parser("install", help="安装 Codex / Claude Code skill")
    install.add_argument("--codex", action="store_true")
    install.add_argument("--claude", action="store_true")
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
    elif args.cmd == "feedback":
        from .knowledge import feedback

        if args.fb_cmd == "submit":
            record = feedback.submit(args.ws, args.file)
            print(json.dumps({"id": record["id"], "metrics": record["metrics"], "items": record["items"][:50]},
                             ensure_ascii=False, indent=1, default=str))
            print(f"完整记录：knowledge/feedback/{record['id']}.json")
        else:
            for record in feedback.records(args.ws):
                print(record["id"], record["submitted"], json.dumps(record["metrics"], ensure_ascii=False)[:200])
    elif args.cmd == "eval":
        from .decision import evaluate

        print(json.dumps(evaluate(args.dir), ensure_ascii=False, indent=2))
    elif args.cmd == "install":
        install_skill(args.codex, args.claude)
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
