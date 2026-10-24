# 内化 3/3：构建知识体系

知识层根目录：`$base`（$n_units 条活跃 κ，$n_skills 个 skill，$n_inactive 条已失效）。
目标：把零散的单跳知识（一条只讲一个对象、一步关系）串成清晰的脉络，写入 `$base/kb/outline.yaml`。

## 输入

- `$base/kb/knowledge/units.jsonl`、`$base/kb/skills/*/SKILL.md`、`$base/evidence/ledger.jsonl`；
  可用 `knosis knowledge select --ws $base --include-inactive`、`knosis knowledge trace <id> --ws $base` 查看。
- 按粒度自动生成的草稿：`$draft`（`knosis knowledge outline --ws $base --draft` 可看渲染结果）。
- $existing

## 要求

1. 层级从上到下：**场景**（任务、目标，以及对它有用的 usage 元知识与 skill）→ **数据间关系**（实体 / 表 / 变量之间的结构）
   → **数据本身**（数据集整体规律、具体对象）。method 可以单列一个「方法」分支，也可以挂在用到它的场景下。
   按语义分组，不要只按粒度或文件机械分组；同一主题的知识放在一起，一节一般 2 到 15 条。
2. 每节写 `title` 与 `summary`（一两句：这一节的知识讲什么、对哪类任务有用）。**summary 只概括成员单元已经说了的内容**，
   不新增断言、不写数字以外的推测；对错仍以单元和证据为准。
3. 每条活跃的 κ 与 skill（`skill:<名字>`）至少放进一节；可以放进多节。本体单元（`ontology/...`）不必逐个列出。
   已撤回、失效、已合并（merged）的单元只能放在 `archive: true` 的节里，或者不放。
4. 去重与矛盾处理已在前两步做过；仍觉得可疑的，在所在节的 `notes` 里写明（列出 id 与理由），不改动原单元。
5. **归纳**：串联时如果多条单跳知识能合成一条上位规律（多条具体对象 → 数据整体规律；多次成功的做法 → method），
   可以在 `kb/knowledge/units.jsonl` 新增归纳单元：`provenance` 写 `derived`，`derived_from` 列出全部原单元（至少两条），
   `status` 为 `inferred`（能验证时照常验证并记证据后再改 verified）。归纳只在确有把握时做，不改原单元。
6. 除归纳单元外，不修改 `units.jsonl`、证据与 skill；大纲写 `kb/outline.yaml`。格式见草稿与下面的示例。

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

`knosis knowledge outline --ws $base` 末尾没有「未归类」一节，且 `knosis knowledge check --ws $base` 不新增问题$check_note。
最后用两三句话说明脉络怎么组织、归纳了什么。
