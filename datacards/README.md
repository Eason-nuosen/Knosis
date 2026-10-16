# Datacards

每个基准一份，记录：**官方来源 URL、许可、体量、访问要求、上游版本**，以及上游数据布局的细节。
这是给人看的参考文档；给 agent 读的精简版在 `knosis/cards/`（`knosis.describe(name)` 返回的就是它）。

**仓库不放数据。** 这些卡片的作用是让取数过程可审计 ——
谁能拿、拿的时候要遵守什么、拿到的应该是什么版本。

| 基准 | 访问 | 许可 | 取数方式 |
| --- | --- | --- | --- |
| [ngdbench](ngdbench.md) | 公开 | **未声明** | HF 直连 |
| [relbench](relbench.md) | 公开 | MIT（代码）/ CC BY-SA 4.0（集合）/ **逐库另有条款** | HF 直连 |
| [burr](burr.md) | 公开 | **未声明** | git clone |
| [newtonbench](newtonbench.md) | 公开 | MIT（代码）/ CC BY-NC-SA 4.0（论文） | git clone |
| [llm-srbench](llm-srbench.md) | **gated** | MIT（代码）/ CC BY 4.0（论文）/ **产物未声明** | HF（需 HF_TOKEN） |
| [alphabench](alphabench.md) | 公开 | MIT（代码）/ **行情数据未声明** | git clone + 自下 Qlib 行情 |
| [kramabench](kramabench.md) | 公开 | **代码未声明** / 数据 CC BY-NC-4.0（未合并的更正） | git clone |
| bibench | 公开 | **未声明** | git clone + git lfs pull（约 4 GB） |
| text | 本地 | 随语料 | 本地路径 |
