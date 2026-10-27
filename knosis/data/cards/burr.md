# Burr — learning ontologies from relational databases (DB → ontology mapping)

## Source

HPI Potsdam / SAP SE / Uni Augsburg. **Burr: A Benchmark for Ontology Learning from
Relational Databases**, Proc. ACM Manag. Data **3(6), Article 305, Dec 2025** (SIGMOD track),
DOI [10.1145/3769770](https://dl.acm.org/doi/10.1145/3769770).
Authors: Lukas Laskowski, Michael Hladik, Jan Portisch, Fabian Panse, Felix Naumann.
Repository https://github.com/HPI-Information-Systems/burr

**No arXiv preprint, no pip package, no HF dataset, no GitHub release.**
All data is in the git repository: `knosis download burr` does a `git clone`.
Upstream's own way of running it needs Docker + a live PostgreSQL (postgis) + a W&B key,
but **Knosis only reads files and does not need to start any service**.

**License: not declared.** The repository has no LICENSE / COPYING file, and the GitHub About panel has no license badge.
Treat it as "all rights reserved": do not repackage and redistribute, and credit upstream when citing. **The SAP enterprise data (`rba`)
is especially sensitive; mind compliance.**

Very small: 54 micro scenarios (each with `schema.sql` + `mapping.json`, usually plus one csv)
+ 4 real databases (Mondial 46 tables, NPD 70, ISWC 9, SAP RBA 7).
A few hundred MB overall.

Upstream's own description says 46 scenarios, the paper says 54, and the actual file tree has 58 leaf scenarios;
**the file tree is authoritative** (54 micro + 4 real databases).

## Description

What Burr tests: **given the schema of a relational database, can you correctly write its mapping to an ontology.**

Scenarios come in two kinds:
- **micro-benchmark** (54, in 8 categories): artificially constructed small, self-contained scenarios, each testing one modeling situation:
  no primary key, no foreign key, n:m relations, ternary relations, composite keys, degree of normalization, weak entities, hierarchy redundancy...
  Categories and counts: `basic` 12, `nm_tables` 9, `normalized` 8, `attributes` 7,
  `complex` 7, `hierarchy` 5, `one_to_n` 4, `one_to_one` 2.
- **real-world** (4): Mondial, NPD FactPages, ISWC, SAP RBA.

**Data layout** (note that micro and real-world have different shapes):

```
micro_benchmark/<category>/<subcategory>/<scenario>/     schema.sql, mapping.json, <scenario>_data.csv
real-world/<database>/                                   *.sql, mappings/*.json + meta.json
                                                         (exceptions: NPD and ISWC give only one .ttl)
```

**This benchmark's gold is `mapping.json`; it is the answer.**
So Knosis puts it in `tasks`, **never in `schema`, and never writes it into this description**.
The moment you access `ds.tasks` you have the answers; do not read them outside evaluation.

A mapping file has a four-key structure: `classes` / `object_properties` / `data_properties`
(plus the optional `translation_tables`). A class's `id` is a URI template that uses `@@table.column@@`
as a placeholder for the primary key; join conditions are written on the class mapping.

**Evaluation has 18 numbers**: {class, relation, attribute} × {precision, recall, F1} × {mapping-based, name-based},
two families. The difference between the two families is crucial:
- **mapping-based**: equality is decided by "mapped to the same SQL source + the same ontology concept", as a set / multiset comparison.
  This is the benchmark's contribution: different names with correct semantics count as correct.
- **name-based** (called "Lexical" in upstream's tables): literal name matching only.

The upstream README's tables use **C / R / A** for Class / Relation / Attribute,
and "Mapping" / "Lexical" for the two families; **the README never defines these abbreviations**,
so to understand them you have to read the code under `evaluator/metrics/`.

Good for: schema understanding, DB → ontology mapping, abstracting relational structure to the concept layer.
Not good for: using mapping.json as input; that is the answer, and using it amounts to copying.

Pitfalls:
- **Upstream's `docker-compose.yml` is broken**: it hard-codes the maintainer's local path
  `/home/lukas/burr/Burr/result:/results`, and sets `runtime: nvidia`,
  so it does not run at all on non-NVIDIA machines.
- **The default experiment config runs only real-world**; the micro-benchmark entries are all commented out in the config.
  To reproduce the paper's micro tables you have to edit the config yourself.
- **Ground truth comes in two formats**: Mondial and RBA give per-class `mappings/*.json`,
  while NPD and ISWC give a single D2RQ `.ttl`. The same parser reads both, but the shapes differ.
- **`pip install -e .` still needs a live Postgres**; there is no "read files only" path.
- Upstream's metrics code does `import wandb` at import time, which cannot be avoided even with `USE_WANDB=false`.
- The metrics file name is misspelled as `caclulate_metrics.py` (one l missing); keep this in mind when grepping.
- The repository is mixed with `.DS_Store`, an `old/` subdirectory and two `unfinished_*.sjson` files: lab artifacts, not release artifacts.
- A scenario's identifier is really its path: `<category>__<subcategory>__<scenario>`, e.g.
  `hierarchy__two_tables__reviewer_1`; real databases are `<database>__<variant>`, e.g. `real_world__mondial__fk`.
