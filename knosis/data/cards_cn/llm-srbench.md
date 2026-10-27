# LLM-SRBench —— 抗记忆的符号回归基准

## 来源

Virginia Tech / VinUniversity / CMU。**LLM-SRBench: A New Benchmark for Scientific Equation
Discovery with Large Language Models**，arXiv **2504.10415**（2025-04-14，v2 2025-06-07），
**ICML 2025 Oral**。
作者：Parshin Shojaee, Ngoc-Hieu Nguyen, Kazem Meidani, Amir Barati Farimani, Khoa D Doan, Chandan K Reddy。
仓库 https://github.com/deep-symbolic-mathematics/llm-srbench ；
数据 https://huggingface.co/datasets/nnheui/llm-srbench

获取：`knosis download llm-srbench`
（内部走 HF 直连；上游用 `snapshot_download`，会自己拉。）

**⚠️ 数据是 gated（`gated: "auto"`）。** 匿名访问 `resolve/main/...` 会返回 **401**，
所以 CI 里必须有 `HF_TOKEN`，而且要先在 HF 网页上接受条款。这是最容易卡住的一步。

**许可：** 代码 **MIT**；论文 **CC BY 4.0**；
**但 HF 数据产物本身没有任何 license 字段** —— 未声明。在意的话联系作者。

体量很小（元数据）加大文件：5 个 parquet 合计约 36 KB，加一个 **239 MB** 的 HDF5。
**⚠️ 论文说 239 题，磁盘上是 240 题**（物理 split 是 44 而不是 43）——
差一题的成因未知，需要严格对齐题目数的话自己去 diff `phys_osc` 的名字。

## 说明

LLM-SRBench 考的是：**从给定的输入输出数据里，反推出背后的科学方程。**

它和 NewtonBench 的区别：**这里给你数据**（不用主动做实验），
但它的核心贡献是**抗记忆** —— 题目不是从教科书里直接抄来的，
而是构造过的，防止 LLM 靠背答案冒充"发现"。

**两条构造路线，性质不同：**
- **LSR-Transform**（111 题）：拿 100 个经典 Feynman 方程，把其中一个**输入变量变成目标**，
  再用 SymPy 符号求解得到新方程。只保留解析可解的变换，数据点也投影到新方程的有效域里，
  复杂度控制在原 Feynman 的节点数分布内。这是物理。
- **LSR-Synth**（129 题）：GPT-4o 先为某个科学问题生成**已知项**与**合成的新项**，
  再用 `solve_ivp` 检查可解性、用 GPT-4o 做新颖性检查、生成数据点，
  最后**两位领域专家人工校验**表达式与数据点图。分四个域：化学 36、生物 24、物理 44、材料 25。

**数据分两处，别只看 parquet：**
- **parquet 只有元数据**，五个文件，列是
  `name` / `symbols` / `symbol_descs` / `symbol_properties` / `expression`。
  **里面没有任何数值数据。** 想当然地用 parquet 当数据集会发现"很完整但没数据"。
- **数值在 HDF5**（`lsr_bench_data.hdf5`，239 MB）。组路径：
  - LSR-Transform：`/lsr_transform/{name}`
  - LSR-Synth：`/lsr_synth/{数据集}/{name}`，比如 `/lsr_synth/bio_pop_growth/BPG0`
  每个组里的 dataset 键是 `train` / `test` / `ood_test`（`ood_test` 只有 LSR-Synth 有）。
  Knosis 把组路径放在 `task.meta["hdf5_group"]`，用 `ds.read("hdf5")[group]["train"]` 取数。

**⚠️ OOD 只有 LSR-Synth 才有。** LSR-Transform 的题取 `ood_test_samples` 会
**静默返回 None 而不是报错**，假设到处都有 OOD 的代码会悄悄出问题。

**变量元数据有名字和含义（`symbols` + `symbol_descs`），但没有单位。**
没有 units 字段、没有量纲、没有 SI 标注 —— 整个 schema 里都找不到。
`symbol_properties` 是自由格式的字符串列表（编码了变量角色/标志），
**上游没有公布它的取值词表**，别假设有固定枚举。

也没有 `domain` 字段、没有 `complexity` 字段 —— 域由你加载哪个 split 决定；
复杂度只能自己算（比如对 `expression` 跑 sympy 的 `count_ops`）。

评分（两路）：
- **符号准确率**：GPT-4o 当裁判判断数学等价，**先剥掉参数与常数**。
  与两位人类标注者在 130 题上的一致率 94.6%。
- **数据保真度**：`Acc_τ = 1[max_i |(ŷ-y)/y| ≤ τ]` 与 `NMSE`，在域内测试集
  **和留出的 OOD 集**上分别算。
- 上游最好成绩约 **31.5%** 符号准确率，预算标准化为每题 1000 次 LLM 调用。

适合：符号回归、方程发现、抗记忆评测、域内与域外的泛化对比。
不适合：需要单位/量纲的物理建模（本基准完全不含量纲信息）。

陷阱：
- **gated 下载**，401 是最常见的第一次失败。
- **parquet 与 HDF5 两个文件容易混淆**：parquet 看着像完整数据集但只有元数据；
  而且这个 parquet 是可再生成的，很容易做出一个"看起来完整"的小数据集。
- **符号评分会剥掉常数** —— 数值拟合极好但常数写错，符号准确率照样是 1；
  反过来，结构对但常数位置怪，也可能被判等价。**别把符号准确率当数值保真度用**，
  数值那一路要看 NMSE / Acc_τ。
- 上游的 `feynman` 数据模块是**被注释掉的**，走不通原生 Feynman 评测。
- 上游 `root` 参数实际上**会被覆盖**（`setup()` 里把 `_dataset_dir` 换成下载快照目录），
  指到本地副本不生效。
- 每个搜索方法（LLM-SR、LaSR、SGA、PySR）都要**各自单独装上游包**，
  只装 `requirements.txt` 不够。
