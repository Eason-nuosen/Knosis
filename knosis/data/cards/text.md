# 文本语料（任意文档集合 → schema-free KG）

## 来源

无固定出处 —— 由使用者指向自己的语料目录：`load_dataset("text", path="./corpus")`。
语料本身不受 Knosis 许可约束；Knosis 只读不写。
抽取器可插拔：默认只切块；AutoSchemaKG 等真实抽取器以函数形式传入
`load_dataset("text", path=..., extractor=fn)`，`fn(doc_id, text) -> Iterable[Unit]`。

## 说明

把一堆文档变成一张 schema-free 的知识图。这是 Knosis 里唯一"load 即产出知识单元"
的入口 —— 文本没有 schema 可以先接着，抽取本身就是建图。

**产出什么**（都在 `ds.units` 里）

- `doc` 单元：每篇文档一个，`π` 指向文件路径。`dedup=True`（默认）时，
  归一化后内容相同的转载稿会被折叠，记录在 `ds.schema["duplicates"]` 里 ——
  不去重会让 L2 的支持度计数和聚合失真。
- `chunk` 单元：按 `chunk_chars` 切的块，`π` 定位到 `doc_id#start-end`。
  L2 接地时要靠这个回到原文。
- 传了 `extractor` 时：额外产出抽取器返回的单元（如 `entity` / `triple`），
  关系短语保持**开放词汇**。

**关键约定**

- 关系词表是开放词汇，**不要假设有固定关系类型**。规范化是 L2 的事，
  在这里做会把原始短语丢掉，接不回原文。
- 抽取配置与模型版本应写进每个单元的 `provenance` —— 换了模型就该知道知识变了。
- `condition` 默认为空。文本知识往往带条件（时间、地域、适用对象），
  但现在没人标 —— 别假装它是无条件的。

**坑**

- 单元 id 来自相对路径，删改文件后重跑 id 会变。
- 体量：先跑子目录。抽取时间与语料线性相关。
- 非 UTF-8 文件会被跳过。

**适合**：给 agent 提供一份可追溯、可分块定位的背景知识底图。
**不适合**：当作事实核验的来源 —— 这里没有 GT，抽取出来的东西一律是 `observed`。
