# NewtonBench — $domain

## 数据是什么

这里没有现成的数据文件：你身处一个物理定律被改写过的虚拟宇宙，要通过实验发现其中的定律。
共 $n_tasks 道题，题目 id 形如 `<域>/<难度>/<版本>/<实验系统>`，实验系统有 $systems。
同一难度、同一版本的题共用同一条待发现的定律，只是实验装置不同。实验观测可能含噪声；如何判断与处理，由你决定。

定律的参数：

$params

做实验用 `newton` 工具（见 `TOOLS.md`），在工作区根目录运行：

```bash
knosis tool run newton -- --task <题目 id> --inputs '<JSON 列表>' --out stages/<当前阶段>/newton/<编号>
```

`--inputs` 就是下面上游说明里 `<run_experiment>` 标签中的 JSON 列表；结果打印出来并写到 `--out`。
下面是上游对每种实验系统的原始说明（其中的 `<run_experiment>` / `<final_law>` 标签格式在这里分别换成工具调用和交付文件）：

$apparatus

## 下游任务是什么

为每道题提交发现的定律：Python 函数源码，签名为 `$signature`，可以 `import math` 或使用 `np.`。
交付 JSONL 每行 `{"id": 题目 id, "answer": 函数源码字符串}`。
评测按上游方式在 5000 个随机采样点上与真实定律比较 RMSLE；符号等价（需要 LLM 裁判）不做。
dev 题与测试题不共用定律。

## 知识应该服务什么

关于这个宇宙里的定律形式、常数、实验系统与定律之间关系、实验设计经验的知识，都可以写下来复用。
