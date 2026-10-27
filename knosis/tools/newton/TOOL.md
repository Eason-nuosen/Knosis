---
name: newton
version: "0.1"
kind: program
modality: [simulator]
stage: [explore, extract, refine, decide]
license: "Apache-2.0 (bundled with Knosis); the simulator comes from upstream NewtonBench (MIT) and is loaded from the raw data directory"
---

The NewtonBench experimental apparatus: runs a batch of experiments for one task (`<domain>/<difficulty>/<version>/<system>`) and returns the observations.
The input format is the same JSON list as in upstream `<run_experiment>`, one set of experiment parameters per element; the noise level is set by the workspace
(read from `<ws>/.knosis/state.json`, `--ws` defaults to the current directory).

```bash
knosis tool run newton -- --task m0_gravity/easy/v0/vanilla_equation \
  --inputs '[{"mass1": 1, "mass2": 2, "distance": 3}]' --out stages/1_explore/newton/001
```

Results are printed to stdout and written to `experiments.json` under `--out` (inputs and observations paired one to one).
Experiments are interactions with the environment, and observations are not knowledge; write the conclusions drawn from them as κ, with source `tool:newton@0.1(task=...)`.
