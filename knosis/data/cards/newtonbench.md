# NewtonBench —— 从数据发现物理定律（方程类知识）

## 来源

HKUST + NVIDIA。**NewtonBench: Benchmarking Generalizable Scientific Law Discovery in
LLM Agents**，arXiv **2510.07172**（v1 2025-10-08，v3 2026-02-24），ICLR 2026。
作者：Tianshi Zheng, Kelvin Kiu-Wai Tam, Newt Hue-Nam K. Nguyen … Yangqiu Song, Ginny Y. Wong。
仓库 https://github.com/HKUST-KnowComp/NewtonBench

**没有 HuggingFace 数据集，没有 PyPI 包，没有任何可下载的数据产物。**
只有源码：`knosis download newtonbench` 会 `git clone`。
仿真环境用 numpy，**跑起来不需要 API key**（但上游默认的评测用 LLM 当裁判，那一环要 key）。

**许可：** 代码 **MIT**（仓库根有 LICENSE）；**论文 CC BY-NC-SA 4.0**（非商用）。
两者不一致，代码复用按 MIT，引用论文注意 NC 条款。

**⚠️ 这个基准没有「数据集」可加载。** 任务在运行时由 harness 生成：
agent 通过 `<run_experiment>` 工具主动探测模拟器（给一组输入参数，拿回输出），
真值方程在 `modules/m*/laws.py` 里以 Python 函数形式存在。
所以本 adapter 读的是**源码**，产出的是「变量 + 取值分布」的物理 schema 与方程任务。

规模：12 个物理域 × 3 个难度 × 3 个版本 = **108 条反事实定律**，
再乘 3 个 system complexity = **324 个任务**。

获取：`knosis download newtonbench`

## 说明

NewtonBench 考的是：**让 agent 主动做实验、从观测数据里反推出背后的物理定律。**

它和常见的符号回归基准（Feynman / SRBench 那类）有个根本区别：
**它不给你输入数据点。** agent 必须自己设计实验 —— 选一组输入参数、
调用模拟器、拿到输出、再决定下一组问什么。这是「主动实验设计」而不是「给定数据拟合」。

**12 个物理域**（目录名 → 物理内容）：
`m0_gravity` 万有引力、`m1_coulomb_force` 库仑力、`m2_magnetic_force` 安培力、
`m3_fourier_law` 傅里叶热传导、`m4_snell_law` 斯涅尔折射、`m5_radioactive_decay` 放射性衰变、
`m6_underdamped_harmonic` 欠阻尼谐振、`m7_malus_law` 马吕斯定律、`m8_sound_speed` 声速、
`m9_hooke_law` 胡克定律、`m10_be_distribution` 玻色-爱因斯坦分布、`m11_heat_transfer` 传热。

**两个正交的维度，容易只数一个：**
- **难度** `easy` / `medium` / `hard` —— 由**对表达式的变异次数**决定（从范式定律出发累计变异）。
- **版本** `v0` / `v1` / `v2` —— 同一个难度下的不同变异。`evaluation_results/` 里
  `{难度}/{版本}` 是两层嵌套目录。**"12 域 × 3 难度 = 36" 这种读法少算了 3 倍。**

变异是**累积**的：easy = 从范式做 1–2 次变异；medium = easy 再加 1–2 次；hard 继续加。
变异操作是表达式树上的操作（交换运算符，比如 `+` → `×`；改常数/指数，比如平方 → 立方）。
策展规则有四条：不引入新变量、复杂度不降低、变异不能是上一步的逆、连续两次变异不能等价于单次变异。

**⚠️ 每条目标定律里都嵌了至少一个「被重新缩放的物理常数」**，用来补回变异破坏掉的量纲一致性。
源码里以 `HIDDEN_CONSTANT` 出现，比如 `m0_gravity` 是 `6.674e-5`。
**这不是真实的重力常数，别去"改正"它。** 提示里以 `HIDDEN_CONSTANT_C` 暴露，
且禁止把它当函数参数（要求定义成函数体内部的局部变量）。

**⚠️ system complexity 三档**：`vanilla_equation`（纯方程）/ `simple_system` / `complex_system`。
后两档会加「辅助方程」—— 辅助方程会告诉 agent，目标定律不会。
Simple 平均 1.75 条辅助方程 / 5.17 个操作，Complex 平均 2.42 / 8.17 个。

**变量与取值域**：变量名与含义是**散文描述**（`PARAM_DESCRIPTION` 字符串），
取值域是**对数均匀采样**的约定，比如 `m0_gravity` 的两个质量是 `U_log(10^0, 10^3)`、
距离是 `U_log(1, 10^1)`。源码里就是 `np.exp(np.random.uniform(np.log(1), np.log(1e3)))`。

**⚠️ 没有 units / 量纲的元数据。** 整个仓库里没有结构化的单位或量纲表 ——
单位只在**容差常数的注释**里出现过（`1e-9  # meters` 这种）。
所以 plan 里设想的「物理 schema + 量纲」在本基准上**需要我们自己补**，
Knosis 这里只如实给出「变量名 + 含义 + 采样分布」，并标明量纲缺失。

评分（两路，别混）：
- **Symbolic Accuracy（SA）** —— 二分，用 **LLM 当裁判**判断符号等价，
  **刻意忽略物理常数**。裁判默认 `nemotron-ultra`（论文报与人类 98.3% 一致）。
  裁判容忍变量改名与常数改写法，但**不容忍改指数**（"指数 4 和 4.03 算不同"）。
  **离线环境跑不了 —— 这一环需要 API。**
- **RMSLE** —— 数据保真度，在 **5000 个留出样本**上算，带 Modified Z-Score 去极值。
  上游**明确拒绝了 NMSE**，改用 RMSLE。

适合：主动实验设计、符号回归、反事实推理、量纲分析。
不适合：当作普通的 x/y 表格数据集读 —— **磁盘上没有这样的表**。

陷阱：
- **真值在代码里**：`modules/m*/laws.py` 的 `LAW_REGISTRY`，是 `{'easy': {'v0','v1','v2'}, ...}` 结构。
  **没有导出格式**（没有 JSON manifest），想做成数据产物得自己导。
- **真值函数签名和给 LLM 看的签名不一样**：内部是
  `_ground_truth_law_easy_v0(mass1, mass2, distance)`，提交的必须是
  `def discovered_law(...)`，靠 `parameter_mapping` 桥接。
- **有物理上不合理的定律**（上游论文明确承认）：变异保证量纲自洽，但有些形式在我们的宇宙里
  不成立。比如 `m8`、`m10` 的部分 hard 变体 ——
  **某些输入会产生 NaN / inf**，代码里有 guard clause 和 `float('nan')` 分支，
  指标代码会显式过滤掉。别把这些当成加载失败。
- **随机性**：`core.py` 用裸的 `np.random.uniform`，没有可见的全局种子；
  论文的数字是**四次运行**的均值与标准差。默认不保证可复现。
- 上游报告：噪声即使只有 0.0001 也会让 SA 掉 12–16%；
  **给强模型加代码辅助反而降低表现**（探索→利用的偏移），弱模型则有提升。

术语：这里 "law" 指一条可写成等式的物理定律；"counterfactual" 指对范式定律做过变异的版本。
