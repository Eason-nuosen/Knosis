"""NewtonBench 实验：在环境侧用上游模拟器（含 GT 定律）跑实验，只把观测交给 agent。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from knosis.data.loaders.newtonbench import upstream
from knosis.tools import write_result


def experiment(task: str, inputs: list[dict], noise: float, root=None) -> list:
    domain, difficulty, version, system = task.split("/")
    module = upstream(domain, root)
    return [module.run_experiment_for_module(noise_level=noise, difficulty=difficulty, system=system,
                                             law_version=version, **params) for params in inputs]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--inputs", required=True, help="JSON 列表，每项一组实验参数")
    parser.add_argument("--out", required=True)
    parser.add_argument("--ws", default=".", help="工作区；噪声水平与原始数据目录取自其 .knosis/state.json")
    args = parser.parse_args(argv)
    started = time.monotonic()
    state = json.loads((Path(args.ws) / ".knosis/state.json").read_text(encoding="utf-8"))
    noise = state["options"].get("noise", 0.0)
    root = state["options"].get("root")
    inputs = json.loads(args.inputs)
    outputs = experiment(args.task, inputs, noise, root and Path(root))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    record = [{"input": i, "output": o} for i, o in zip(inputs, outputs)]
    (out / "experiments.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps(outputs, ensure_ascii=False, default=float))
    write_result(out, "newton", {"task": args.task, "n": len(inputs), "noise": noise}, [], started)


if __name__ == "__main__":
    main()
