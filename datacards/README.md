# Datacards

One card per benchmark, recording the **official source URL, license, size, access requirements and upstream version**,
plus details of the upstream data layout and how Knosis uses it.
These are reference documents for humans; the condensed agent-facing versions are in `knosis/data/cards/` (what `knosis.describe(name)` returns).

**The repository ships no data.** These cards make data acquisition auditable:
who may obtain it, what terms apply when obtaining it, and which version you should end up with.

| Benchmark | Access | License | How to obtain |
| --- | --- | --- | --- |
| [ngdbench](ngdbench.md) | Public | **Not declared** | HF direct |
| [relbench](relbench.md) | Public | MIT (code) / CC BY-SA 4.0 (collection) / **per-database terms** | HF direct |
| [burr](burr.md) | Public | **Not declared** | git clone |
| [newtonbench](newtonbench.md) | Public | MIT (code) / CC BY-NC-SA 4.0 (paper) | git clone |
| [llm-srbench](llm-srbench.md) | **gated** | MIT (code) / CC BY 4.0 (paper) / **artifacts not declared** | HF (needs HF_TOKEN) |
| [alphabench](alphabench.md) | Public | MIT (code) / **market data not declared** | git clone + Qlib market data downloaded separately |
| [kramabench](kramabench.md) | Public | **Code not declared** / data CC BY-NC-4.0 (unmerged correction) | git clone |
| bibench | Public | **Not declared** | git clone + git lfs pull (about 4 GB) |
| text | Local | Per corpus | Local path |
