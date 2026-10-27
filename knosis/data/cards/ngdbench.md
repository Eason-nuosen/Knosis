# NGDBench — QA on large-scale property graphs (clean / perturbed pairs)

## Source

HKUST-KnowComp, **NGDBench: Towards Neural Graph Data Management**, arXiv **2603.05529** (2026).
Code https://github.com/HKUST-KnowComp/NGDBench ;
data https://huggingface.co/datasets/FeifeiCS/NGDBench : public, **not gated**, no application needed.

Get it: `knosis download ngdbench`
(use `--include 'NGDBenchV1_1/NGDFin/*'` to fetch only one domain; do not pull the whole repo.)

**License: not declared.** The HuggingFace card has no `license` field, and the GitHub repository has no LICENSE / COPYING
file. Treat it as "all rights reserved": do not package it into any redistributed artifact, and credit upstream when citing.
The upstream data itself has separate terms (NGD-BI derives from LDBC SNB BI, NGD-Prime from PrimeKG).

Size: about 3.36 million nodes / 26.4 million edges / 90134 queries. Domains differ enormously:
NGD-BI alone has 3 million nodes / 17.2 million edges, while NGD-Fin has only 10 thousand nodes. Reserve disk space first.
The HF repository has two version directories, `NGDBenchV1/` and `NGDBenchV1_1/`; **V1.1 is used by default**.

## Description

NGDBench is a QA benchmark on large-scale property graphs, covering 5 domains:

| Domain (paper name) | Directory name on disk | Content |
| --- | --- | --- |
| NGD-BI | `NGDBi` (`NGDBI` in V1) | social / LDBC SNB BI |
| NGD-Fin | `NGDFin` | finance |
| NGD-Prime | `NGDPrime` | biomedical / PrimeKG |
| NGD-MCP | `NGDMcp` | tool-call traces |
| NGD-Econ | `NGDEcon` | company reports |

**When loading, match the domain name case-insensitively (`scenario="NGD-Fin"`); the inconsistent casing on disk is an upstream pitfall.**

Queries come in four categories, one file per category under V1.1: non-aggregate analysis, aggregate analysis, management non-aggregate, management aggregate.
Every question has **an NL question (field `nlp`) and the corresponding Cypher (field `query`)**. Management questions are **multi-step sequences**
(field `steps`); each step has an `operate_query` that changes state and a `valid_query` that asserts the result; they must be executed in order on one
mutable graph and cannot be treated as single queries.

**Key structure: the structured domains have paired clean and perturbed graphs.** The clean one is the latent true graph, the perturbed one
is the noised observable graph; both sit **in the same `graph/` directory**, distinguished only by file name suffix: the clean one has no suffix,
the perturbed one carries `_noise_<timestamp>`. **That timestamp is not stable across domains or versions; you must glob
`*_noise_*.gpickle` and not hard-code file names.** NGD-MCP and NGD-Econ **have no pairs**, only one graph.

**Answers are precomputed; there is no need to run Neo4j.** Every query record carries both `clean_answer` and `noise_answer`,
plus a precomputed boolean `same_as_cleangraph` telling you whether the noise changed the answer: a ready-made
difficulty / robustness filter, use it directly. **The score gap between the two versions is a "noise sensitivity" metric, not an error**:
do not fix it as a bug, and do not evaluate directly on the clean graph (that bypasses the benchmark's core setting).

⚠️ The graphs are `.gpickle` (pickled NetworkX). **Deserializing them is equivalent to executing arbitrary code**, and the repository has no
hashes to verify against. `ds.read("clean")` / `ds.read("perturbed")` unpickle directly; only do this for files you trust.

Good for: multi-hop queries, aggregate counting, Boolean verification, management operations on graphs, noise robustness.
Not good for: questions that need external world knowledge to answer (information not in the graph cannot be answered, and that is correct).

Pitfalls:
- **The perturbed graph carries traces of the noising, which amounts to leaking the answer**: edge attributes `is_noise` / `noise_similarity` / `relation`,
  node attributes `noise_similarity` / `original_name` (verified on NGD-Fin). Edges in the clean graph have only `label`.
  Before denoising or robustness experiments, first delete all attribute keys in the perturbed graph that the clean graph does not have.
- Domain directory names differ from the paper names; V1 and V1.1 differ in layout and query file names. **Specify the version directory explicitly.**
- Answer field names vary by domain: structured domains use `clean_answer` / `noise_answer`, unstructured domains use `gnd` / `answer`;
  moreover **MCP's `gnd` is a string** (e.g. "varied keyword search"), not a result set, with completely different semantics.
- Answers are **list-of-dict keyed by the Cypher return aliases**; compare with set semantics, ignoring order, not by direct list comparison.
- The GT for aggregate questions is a set or a number; mind deduplication and ordering rules, following the official convention.
- Relation phrases in the MCP / Econ domains are open-vocabulary; do not assume a fixed relation vocabulary; the BI / Fin / Prime domains have explicit schemas.
- The upstream release is mixed with development leftovers: `__pycache__/*.pyc`, `mcp_tragectory` (misspelled), `Primekg` (casing).

It is advisable to start with **NGD-Fin or NGD-Prime** (explicit schema, relatively manageable scale); NGD-BI is the largest.
Terminology: in the graph query context "hop" means the number of relation hops, and "aggregation" means count / sum / avg type operators.
