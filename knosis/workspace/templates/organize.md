# 整理知识体系

知识层目录：`$kdir`（$n_units 条 κ，$n_skills 个 skill，$n_inactive 条已撤回或失效）。
目标：把零散的知识组织成一份有条理的知识体系，写入 `$kdir/outline.yaml`。

## 输入

- `$kdir/units.jsonl`、`$kdir/skills/*/SKILL.md`、`$kdir/evidence.jsonl`；
  可用 `knosis knowledge select --ws $ws --include-inactive`、`knosis knowledge trace <id> --ws $ws` 查看。
- 按粒度自动生成的草稿：`$draft`（`knosis knowledge outline --ws $ws --draft` 可看渲染结果）。

## 要求

1. 层级从上到下：**场景**（任务、目标，以及对它有用的 utility 与 skill）→ **数据间关系**（实体 / 表 / 变量之间的结构）
   → **数据本身**（数据集整体规律、具体对象）。method 可以单列一个「方法」分支，也可以挂在用到它的场景下。
   按语义分组，不要只按粒度或文件机械分组；同一主题的知识放在一起，一节一般 2 到 15 条。
2. 每节写 `title` 与 `summary`（一两句：这一节的知识讲什么、对哪类任务有用）。**summary 只概括成员单元已经说了的内容**，
   不新增断言、不写数字以外的推测；对错仍以单元和证据为准。
3. 每条活跃的 κ 与 skill（`skill:<名字>`）至少放进一节；可以放进多节。本体单元（`ontology/...`）不必逐个列出。
   已撤回或失效的单元只能放在 `archive: true` 的节里，或者不放。
4. 疑似重复、互相矛盾、条件互斥的单元，在所在节的 `notes` 里写明（列出 id 与理由），不要改动或删除单元本身。
5. 不修改 `units.jsonl`、`evidence.jsonl` 与 skill；只写 `outline.yaml`。格式见草稿与下面的示例。

```yaml
title: <这份知识体系的名字>
summary: <一两句>
sections:
  - id: scene-gravity
    title: 场景：从受控实验发现幂律
    summary: ……
    units: [skill:discover-positive-power]
    sections:
      - id: scene-gravity/method
        title: 估计指数的方法
        summary: ……
        units: [extract/single-axis-scaling, extract/log-domain-check]
  - id: archive
    title: 已撤回
    archive: true
    units: [extract/all-inverse-square]
```

## 验收

`knosis knowledge outline --ws $ws` 末尾没有「未归类」一节，且 `knosis knowledge check --ws $ws` 输出 OK$check_note。
