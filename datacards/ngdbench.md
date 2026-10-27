# NGDBench

| Item | Value |
| --- | --- |
| Paper | NGDBench: Towards Neural Graph Data Management |
| arXiv | **2603.05529** (v1 2026-02-27; v2 2026-05-29) |
| Authors | Yufei Li, Yisen Gao, Jiaxuan Xiong, Jiaxin Bai, Shijie Zhong, Haoyu Huang, Zhongwei Xie, Hong Ting Tsang, Yangqiu Song (HKUST-KnowComp) |
| Code | https://github.com/HKUST-KnowComp/NGDBench |
| Data | https://huggingface.co/datasets/FeifeiCS/NGDBench |
| Access | Public, not gated, no request needed |
| **License** | **Not declared** (see below) |
| Upstream version | `NGDBenchV1` and `NGDBenchV1_1`; **V1.1 is the default** |
| HF last updated | 2026-08-27 |

## License

**No license statement could be found.** Verified:

- The HF data card's YAML front-matter has only `tags: [NeuralDatabase]` and
  `size_categories: [100M<n<1B]`, **with no `license:` field**;
  the HF API `cardData` has no license key either.
- The GitHub repo root has no `LICENSE` / `LICENSE.md` / `LICENSE.txt` / `COPYING`
  (all 404); the About panel has no license badge.

**Treat as "all rights reserved": do not bundle it into any redistributed artifact.**
The upstream data has its own terms too (NGD-BI derives from LDBC SNB BI, NGD-Prime from PrimeKG).

## Obtaining

```bash
knosis download ngdbench --include 'NGDBenchV1_1/NGDFin/*'   # one domain only
knosis download ngdbench --include 'NGDBenchV1_1/*'          # all of V1.1
```

**Do not pull the whole repo.** The HF size category is `100M<n<1B`, and the NGD-BI domain alone is several GB.
Scenario keys (`ngd-bi`, `ngd-fin`, `ngd-prime`, `ngd-mcp`, `ngd-econ`) are matched case-insensitively against directory names
(the casing of directory names on disk is inconsistent).

**Do not use `load_dataset("FeifeiCS/NGDBench")` from HF `datasets`.** The repo's data card has no
`config_name` / `data_files`, so the HF `datasets` auto-loader fails or does the wrong thing.
It is a plain file dump.

**⚠️ Use `huggingface-cli` or `hf_hub_download`, not bare `curl`.**
The repo has an LFS config; `curl` on a large `.gpickle` may return only the LFS pointer text instead of the data.
`knosis download` uses `huggingface_hub.snapshot_download` and gets the real data.

## Size

| Category | NGD-BI | NGD-Fin | NGD-Prime | NGD-MCP | NGD-Econ |
| --- | --- | --- | --- | --- | --- |
| Nodes (true graph) | 2,997,352 | 10,865 | 129,312 | 181,689 | 33,164 |
| Edges (true graph) | 17,196,776 | 57,818 | 8,100,498 | 351,263 | 63,757 |
| Edges (perturbed) | 17,971,365 | 60,476 | 8,465,124 | 351,263 | 63,757 |

Query counts: non-aggregate analytics **58,321**, aggregate analytics **25,703**, management **6,110**.

**Note the node-count asymmetry**: the perturbed graph has **exactly the same node count** as the true graph; only the edge count grows (BI / Fin / Prime).
Noise acts mainly at the edge level (and attribute level), not by inserting new nodes.

## Layout

```
NGDBenchV1_1/
├── NGDBi/                       # ⚠️ lowercase i in V1.1 (NGDBI in V1)
│   ├── graph/{ldbc_snb_bi.gpickle, ldbc_snb_bi_noise_20260128_015455.gpickle}
│   ├── noise_info/*_{noisy_edges,noisy_nodes,records}.json
│   └── query/{complex_query_agg, complex_query_noagg,
│              management_query_agg, management_query_noagg}.json
├── NGDFin/    graph/…  noise_info/…  query/ (same four as above)
├── NGDPrime/  graph/…  noise_info/…  query/{management_query_agg, management_query_noagg,
│                                             query_results_agg, query_results_noagg}
├── NGDMcp/    graph/mcp_tragectory_40pct_without_concept.graphml   # ⚠️ graphml, not gpickle
│              kg_extraction/qwen2.5-14b-instruct_…json
│              query/complex_query_{agg,noagg}_judged_finalkeep[_with_nlp].json
└── NGDEcon/   graph/multiEcon.gpickle
               kg_extraction/qwen2.5-14b-instruct_multi_financial.json
               query/{complex_query_agg, complex_query_noagg}.json
```

Formats: `.gpickle` (pickled NetworkX, dominant), `.graphml` (MCP only), `.json`.
**No parquet / CSV / SQLite.**

**⚠️ Deserializing a `.gpickle` executes arbitrary code**, and each domain was pickled under a specific NetworkX / Python
version, so cross-version loads often fail. `ds.read("clean")` unpickles directly; do this only for trusted files.

## Record structure (verified, NGD-BI V1.1 non-aggregate questions)

```json
{
  "template_type": "pipelined",
  "query": "MATCH (a:Organisation {id: 367})-[:Organisation_isLocatedIn_Place]->(b:Place) …",
  "clean_answer": [{"b.url": "…", "c.id": 1455}],
  "noise_answer": [{"b.url": "…", "c.id": 1455}],
  "same_as_cleangraph": true,
  "nlp": "Find an organisation located in a place with id 367, …",
  "template_id": "pipelined_T001"
}
```

**Both `clean_answer` and `noise_answer` are precomputed and shipped with the data**:
scoring needs no Neo4j; just compare the model output against them.
`same_as_cleangraph` is a precomputed boolean telling you whether noise changed the answer (a ready-made difficulty filter).
Answers are **lists of dicts keyed by Cypher return aliases**; compare with set semantics, ignoring order.

## How Knosis uses it

- Loader (`knosis/data/loaders/ngdbench.py`): `load_dataset("ngdbench", "<domain>", version="NGDBenchV1_1")`
  (default `ngd-fin`). Files: `clean` / `perturbed` graph (a file whose name contains `_noise_` is the perturbed one),
  plus `noise_info` / `kg_extraction` when present. One task per record in every `query/*.json`
  (for NGD-MCP, a file with a `_with_nlp` sibling is skipped); the answer is the first of `clean_answer` / `gnd` / `answer`,
  the input is `nlp`, else `query`, else `steps`; the Cypher and `noise_answer` stay in `meta`.
- Exporter (`knosis/workspace/exporters/ngdbench.py`): the agent gets the **perturbed** graph as `data/graph.gpickle`
  (or a copy of the clean graph if there is no perturbed one), with node/edge attribute keys restricted to those of the clean graph
  so noise traces (`is_noise`, `noise_similarity`, `original_name` etc.) do not leak. Only `complex_query*` / `query_results*`
  tasks are exported (management questions are not). Options: `question="cypher"` (NL question + Cypher, default) or `"nl"`
  (NL only, keeping only questions whose NL text is complete); `noise_report` (makes `noise.jsonl` a required deliverable);
  `curated` (a hand-checked task set in `exporters/curated/<name>.yaml`, NL only); default `dev=50`.
  About six evenly spaced tasks become in-brief examples and are held out.
- Scorer (`knosis/decision/graph_qa.py`): `answer_set_em` / `answer_set_f1` (scalars become singleton sets, dict rows compare values only,
  so aliases need not match the Cypher `RETURN`), `missing`, `by_kind`, and the same metrics split into `noise_affected` / `noise_unaffected`
  (whether `noise_answer` differs from the gold). The reference `noisy_graph_answer` is the score of copying `noise_answer`.
  The knowledge scorer grades `stages/4_decide/noise.jsonl` claims by precision / recall / F1 per category against a diff of the clean and perturbed graphs.

## Known issues

- **Domain directory names differ from the paper's names**: the paper says `NGD-BI`, disk has `NGDBi` (V1.1) / `NGDBI` (V1).
  MCP is `NGDMcp`. A loader must handle the mapping; Knosis matches case-insensitively.
- **Timestamps in perturbed file names are unstable**: `20260126`, `20260128_015455`, `20260127_113349`
  all differ: **glob `*_noise_*.gpickle`, do not hardcode**.
- **Answer field names vary by domain**: structured domains use `clean_answer` / `noise_answer`,
  unstructured domains use `gnd` / `answer`; and **MCP's `gnd` is a string**
  (e.g. `"varied keyword search"`), not a result set.
- **`gnd` does not exist in the V1.1 structured files**, even though the HF card tells you to use it.
- **V1 and V1.1 differ greatly in layout and query file names** (V1 has a `judge_query*.json`
  Boolean bucket, `management_mix.json`, `complex_query_agg_pair.json`, etc.).
  **Specify the version directory explicitly.**
- The release contains development leftovers: `NGDFin/query/__pycache__/query.cpython-313.pyc`,
  the misspelled `mcp_tragectory`, the inconsistently cased `Primekg`.
- The upstream README says "every **structured** dataset provides a clean and perturbed pair";
  this is accurate: **MCP and Econ have no pair**, only one graph.
