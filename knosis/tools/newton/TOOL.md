---
name: newton
version: "0.1"
kind: program
modality: [simulator]
stage: [explore, extract, refine, decide]
license: "Apache-2.0（Knosis 自带）；模拟器来自 NewtonBench 上游（MIT），从原始数据目录加载"
---

NewtonBench 的实验装置：对一道题（`<域>/<难度>/<版本>/<实验系统>`）跑一批实验，返回观测值。
输入格式与上游 `<run_experiment>` 中的 JSON 列表相同，每个元素是一组实验参数；噪声水平由工作区设定。

```bash
knosis tool run newton -- --task m0_gravity/easy/v0/vanilla_equation \
  --inputs '[{"mass1": 1, "mass2": 2, "distance": 3}]' --out stages/1_explore/newton/001
```

结果打印到标准输出，并写到 `--out` 的 `experiments.json`（输入与观测一一对应）。
实验是与环境的交互，观测不是知识；由此得到的结论写成 κ，来源写 `tool:newton@0.1(task=...)`。
