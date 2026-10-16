# NewtonBench

| 项 | 值 |
| --- | --- |
| 论文 | NewtonBench: Benchmarking Generalizable Scientific Law Discovery in LLM Agents |
| arXiv | **2510.07172**（v1 2025-10-08；v3 2026-02-24） |
| 会议 | **ICLR 2026** |
| 作者 | Tianshi Zheng, Kelvin Kiu-Wai Tam, Newt Hue-Nam K. Nguyen … Yangqiu Song, Ginny Y. Wong |
| 机构 | HKUST + NVIDIA |
| 代码 | https://github.com/HKUST-KnowComp/NewtonBench |
| 数据 | **没有数据产物** —— 上游不提供任何可下载的数据集 |
| 访问 | 公开、无 gated、无需申请（git clone） |
| **许可** | 代码 **MIT**（仓库根 `LICENSE`）/ 论文 **CC BY-NC-SA 4.0**（非商用） |
| 上游版本 | 无数据版本号 —— adapter 读的是 clone 下来的源码树，任务由 harness 在运行时生成 |

## 许可

代码 **MIT**（仓库根有 `LICENSE`）；论文 **CC BY-NC-SA 4.0**（非商用）。

**两者不一致。** 代码复用按 MIT，引用论文文本时注意 NC 条款。

⚠️ 本基准**没有任何数据产物** —— 所以「数据集许可」这一栏不存在，
不存在需要另行授权的数据文件。adapter 读到的是源码。

## 获取

```bash
knosis download newtonbench     # 走 git clone，拉上游仓库
```

- **没有 HuggingFace 数据集，没有 PyPI 包，没有任何可下载的数据产物。** 只有源码。
- 仿真环境用 numpy，**跑起来不需要 API key**；但上游默认的评测用 LLM 当裁判
  （默认 `nemotron-ultra`），**那一环要 key —— 离线环境跑不了符号准确率**。
- 别指望 clone 完就能 `load` 出一张 x/y 表 —— 磁盘上没有这样的表。
- adapter 的 `_root` 依次找 `<数据根>/NewtonBench`、`<数据根>`，判定标志是存在
  `modules/` 目录；找不到时报错并提示运行 `knosis download newtonbench`。

## 体量

**这个基准没有「数据集」可加载。** 任务在运行时由 harness *生成*：
agent 通过 `<run_experiment>` 工具主动探测模拟器（给一组输入参数，拿回输出），
真值方程在 `modules/m*/laws.py` 里以 Python 函数形式存在。

| 维度 | 取值 | 数 |
| --- | --- | --- |
| 物理域 | `m0_gravity` … `m11_heat_transfer` | 12 |
| 难度 | `easy` / `medium` / `hard` | 3 |
| 版本 | `v0` / `v1` / `v2` | 3 |
| **反事实定律** | 12 × 3 × 3 | **108** |
| system complexity | `vanilla_equation` / `simple_system` / `complex_system` | 3 |
| **任务总数** | 108 × 3 | **324** |

⚠️ **「12 域 × 3 难度 = 36」这种读法少算了 3 倍。** 难度与版本是两个正交维度，
`evaluation_results/` 里 `{难度}/{版本}` 是两层嵌套目录。

**两个维度性质不同：**

- **难度** `easy` / `medium` / `hard` —— 由**对表达式的变异次数**决定。变异是**累积**的：
  easy = 从范式定律做 1–2 次变异；medium = easy 再加 1–2 次；hard 继续加。
- **版本** `v0` / `v1` / `v2` —— 同一个难度下的不同变异。

变异操作是表达式树上的操作（交换运算符，比如 `+` → `×`；改常数/指数，比如平方 → 立方）。
策展规则有四条：不引入新变量、复杂度不降低、变异不能是上一步的逆、
连续两次变异不能等价于单次变异。

12 个物理域（目录名 → 物理内容，目录名 verbatim）：

| 目录 | 物理内容 |
| --- | --- |
| `m0_gravity` | 万有引力 |
| `m1_coulomb_force` | 库仑力 |
| `m2_magnetic_force` | 安培力 / 磁场 |
| `m3_fourier_law` | 傅里叶热传导 |
| `m4_snell_law` | 斯涅尔折射 |
| `m5_radioactive_decay` | 放射性衰变 |
| `m6_underdamped_harmonic` | 欠阻尼谐振 |
| `m7_malus_law` | 马吕斯定律（偏振） |
| `m8_sound_speed` | 声速 |
| `m9_hooke_law` | 胡克定律 |
| `m10_be_distribution` | 玻色-爱因斯坦分布 |
| `m11_heat_transfer` | 传热 |

**system complexity 三档**：`vanilla_equation`（纯方程）/ `simple_system` / `complex_system`。
后两档会加「辅助方程」—— 辅助方程会告诉 agent，目标定律不会。
Simple 平均 **1.75 条辅助方程 / 5.17 个操作**，Complex 平均 **2.42 / 8.17**。

**变量与取值域**：变量名与含义是**散文描述**（`prompts.py` 里的 `PARAM_DESCRIPTION` 字符串），
取值域是**对数均匀采样**的约定，比如 `m0_gravity` 的两个质量是 `U_log(10^0, 10^3)`、
距离是 `U_log(1, 10^1)`。源码里就是
`np.exp(np.random.uniform(np.log(1), np.log(1e3)))`。

⚠️ **没有 units / 量纲的元数据。** 整个仓库里没有结构化的单位或量纲表 ——
单位只在**容差常数的注释**里出现过（`1e-9  # meters` 这种）。
所以 plan 里设想的「物理 schema + 量纲」在本基准上**需要我们自己补**；
Knosis 只如实给出「变量名 + 含义 + 采样分布」，并标明量纲缺失（`units_available: False`）。

## 布局

```
<数据根>/                            # dataset_dir("newtonbench")
└── NewtonBench/                     # git clone 下来的上游仓库（_root 第一候选）
    ├── LICENSE                      # MIT
    ├── quick_start.py               # 上游运行入口
    ├── configs/                     # 上游配置
    ├── evaluation_results/
    │   └── <easy|medium|hard>/<v0|v1|v2>/     # ⚠️ 两层嵌套，共 9 种组合/域
    └── modules/
        ├── m0_gravity/
        │   ├── laws.py              # LAW_REGISTRY + _ground_truth_law_* + HIDDEN_CONSTANT
        │   ├── prompts.py           # PARAM_DESCRIPTION（散文变量表）
        │   └── core.py              # 采样代码：np.random.uniform（对数均匀）
        ├── m1_coulomb_force/        # 同上三件套
        ├── m2_magnetic_force/
        ├── m3_fourier_law/
        ├── m4_snell_law/
        ├── m5_radioactive_decay/
        ├── m6_underdamped_harmonic/
        ├── m7_malus_law/
        ├── m8_sound_speed/
        ├── m9_hooke_law/
        ├── m10_be_distribution/
        └── m11_heat_transfer/
```

adapter 的 `load(domain=…)` 只认 `modules/{domain}/`；`list_scenarios()` 返回 `DOMAINS` 的 12 个 key。

`laws.py` 的结构：

```python
LAW_REGISTRY = {'easy': {'v0', 'v1', 'v2'}, 'medium': {...}, 'hard': {...}}
HIDDEN_CONSTANT = <每域一个数>          # 例：m0_gravity 是 6.674e-5
def _ground_truth_law_easy_v0(mass1, mass2, distance): ...
```

## 评分

两路，**别混**：

- **Symbolic Accuracy（SA）** —— 二分，用 **LLM 当裁判**判断符号等价，
  **刻意忽略物理常数**。裁判默认 `nemotron-ultra`（论文报与人类 **98.3%** 一致）。
  裁判容忍变量改名与常数改写法，但**不容忍改指数**（「指数 4 和 4.03 算不同」）。
  **离线环境跑不了 —— 这一环需要 API。**
- **RMSLE** —— 数据保真度，在 **5000 个留出样本**上算，带 Modified Z-Score 去极值。
  上游**明确拒绝了 NMSE**，改用 RMSLE。

Knosis 注册的读数：`symbolic_accuracy`（up）、`rmsle`（down）、
`symbolic_accuracy_by_complexity`（SA 按 vanilla/simple/complex 分桶 ——
强模型在 complex-hard 上会塌）、`noise_robustness`（同一题在不同噪声水平
**0.0001 / 0.001 / 0.01 / 0.1** 下的 SA 差）。

上游报告的读数：

- 噪声即使只有 **0.0001** 也会让 SA 掉 **12–16%**。
- **给强模型加代码辅助反而降低表现**（探索→利用的偏移），弱模型则有提升。
- 论文的数字是**四次运行**的均值与标准差。

适合：主动实验设计、符号回归、反事实推理、量纲分析。
不适合：当作普通的 x/y 表格数据集读 —— **磁盘上没有这样的表**。

## 已知问题

- ⚠️ **这个基准没有「数据集」可加载。** 任务是运行时由 harness 生成的，
  真值在源码里，输入点要 agent 主动探测模拟器。本 adapter **不产出任何 x/y 表**（因为它不存在）。
- **真值在代码里**：`modules/m*/laws.py` 的 `LAW_REGISTRY`，是
  `{'easy': {'v0','v1','v2'}, ...}` 结构。
  **没有导出格式**（没有 JSON manifest），想做成数据产物得自己导。
- **真值函数签名和给 LLM 看的签名不一样**：内部是
  `_ground_truth_law_easy_v0(mass1, mass2, distance)`，提交的必须是
  `def discovered_law(...)`，靠 `parameter_mapping` 桥接。
- ⚠️ **每条目标定律里都嵌了至少一个「被重新缩放的物理常数」**，用来补回变异破坏掉的量纲一致性。
  源码里以 `HIDDEN_CONSTANT` 出现，比如 `m0_gravity` 是 **`6.674e-5`**。
  **这不是真实的重力常数，别去「改正」它。** 提示里以 `HIDDEN_CONSTANT_C` 暴露，
  且**禁止把它当函数参数**（要求定义成函数体内部的局部变量）。
  裁判会忽略常数值，但 **RMSLE 不会**。
- **有物理上不合理的定律**（上游论文明确承认）：变异保证量纲自洽，但有些形式在我们的宇宙里
  不成立。比如 `m8`、`m10` 的部分 hard 变体 ——
  **某些输入会产生 NaN / inf**，代码里有 guard clause 和 `float('nan')` 分支，
  指标代码会显式过滤掉。**别把这些当成加载失败。**
- **随机性**：`core.py` 用裸的 `np.random.uniform`，**没有可见的全局种子**；
  **默认不保证可复现**（论文数字是四次运行的均值±标准差）。
- **变量元数据是散文，不是权威声明**：Knosis 原样取 `prompts.py` 的 `PARAM_DESCRIPTION` 作为任务输入，不做解析。
- **量纲缺失**：上游没有结构化单位表，单位只在容差常数的注释里出现 ——
  变量 unit 字段一律为 `None`。
