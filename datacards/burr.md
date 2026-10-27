# Burr

| Item | Value |
| --- | --- |
| Full name | Burr: A Benchmark for Ontology Learning from Relational Databases |
| Venue | Proc. ACM Manag. Data **3(6), Article 305, Dec 2025** (SIGMOD track), presented at SIGMOD 2026 |
| DOI | [10.1145/3769770](https://dl.acm.org/doi/10.1145/3769770) · DBLP `journals/pacmmod/LaskowskiHPPN25` |
| Authors | Lukas Laskowski (HPI), Michael Hladik (SAP), Jan Portisch (SAP), Fabian Panse (Augsburg), Felix Naumann (HPI) |
| Code | https://github.com/HPI-Information-Systems/burr |
| arXiv | **No preprint found** (apparently submitted directly to ACM); unverified |
| Erratum | A correction in PACMMOD 4(1), Feb 2026 notes that the original title omitted "[Experiments & Analysis]" (seen only in search snippets, not verified directly) |
| Access | Public (git clone) |
| **License** | **Not declared** |
| Releases | **0** |
| Repo single commit | `530a5bc`, dated 2026-05-05 |

## License

**There is no LICENSE file.** Verified: `ls -a | grep -i licen` returns nothing;
the GitHub About panel has no license badge, no description, no topics.
**Reuse terms are unspecified**: treat as "all rights reserved".

**⚠️ Contains SAP enterprise data (`rba`)**, which is especially sensitive for compliance.

## Obtaining

```bash
knosis download burr     # git clone the upstream repo
```

**All data is in the git repo**: no pip package, no HF dataset, no release, no request form.
A clone gives you all the SQL, all the mapping JSON, and the evaluator.

Upstream's own runner needs Docker + a live PostgreSQL (`postgis/postgis:14-3.3`) +
a W&B key. **Knosis only reads files and starts no services.**

## Size (upstream gives three inconsistent figures; the file tree is authoritative)

| Source | Scenarios |
| --- | --- |
| README | "46 scenarios" |
| Paper abstract | 54 |
| **Actual file tree** | **54 micro + 4 real-world databases = 58 leaf scenarios** |

The 8 micro-benchmark categories (`find micro_benchmark -name schema.sql | wc -l` = 54):

| Category | Count | What it tests |
| --- | --- | --- |
| `basic` | 12 | Table / attribute / relation / no primary key / no foreign key baselines |
| `nm_tables` | 9 | n:m, ternary relations, composite keys, no constraints |
| `normalized` | 8 | 1NF/2NF/3NF, redundancy, multiple concepts in one table |
| `attributes` | 7 | Boolean relations, composite, multi-valued, obscure naming, weak entities |
| `complex` | 7 | `scenario_a`…`scenario_f` combinations |
| `hierarchy` | 5 | Fully redundant, denormalized, each-combination, normalized, two child tables |
| `one_to_n` | 4 | Binary n:1, with extra table, reflexive |
| `one_to_one` | 2 | Single relation vs. two relations |

The 4 real-world databases:

| key | Directory | Tables |
| --- | --- | --- |
| `mondial` | `real-world/mondial` | 46 |
| `npd` | `real-world/npd_factpages` | 70 |
| `iswc` | `real-world/iswc` | 9 |
| `rba` | `real-world/rba` | **7** (SAP enterprise data; one empty table removed) |

## Layout

```
micro_benchmark/<category>/<subcategory>/<scenario>/
    schema.sql            # DDL, usually with instance data too
    mapping.json          # **gold mapping (the answer)**
    <scenario>_data.csv   # instance rows (optional)
    mapping.ttl / test_mapping.ttl   # occasional D2RQ turtle variants

real-world/<database>/
    *.sql                 # schema (+ instance data)
    mappings/*.json       # mappings split by ontology class + meta.json   (mondial 20, rba 23)
    meta.json             # prefix declarations
    *.ttl                 # monolithic D2RQ ground truth          (npd, iswc)
```

Concrete path examples (from the file tree):
`micro_benchmark/basic/table/person/{schema.sql,mapping.json,person_basic.csv}`,
`micro_benchmark/attributes/multi_value_attributes/hobbies/{…,hobbies.csv,person.csv}`,
`real-world/mondial/mappings/{country.json,city.json,river.json,…,meta.json}`.

**⚠️ Ground truth comes in two forms**: mondial and rba give a per-class `mappings/*.json` directory;
**npd and iswc give a single D2RQ `.ttl`**. Upstream reads both with the same parser (`JsonMapping` / `D2RQMapping`),
so a loader must accept both.

## Scenario naming

There is no global naming scheme: **a scenario's name is its path**.
IDs derived by `ExperimentManager.start_experiments` look like
`f"{group}__{base_scenario}__{scenario}"`, e.g. `hierarchy__two_tables__reviewer_1`;
real-world databases are `<database>__<variant>`, e.g. `real_world__mondial__fk`.
The `SCENARIO` environment variable takes an **experiment config key** (default `base_experiment`), **not** a scenario name.

## Gold mapping structure

Four top-level keys (as in `evaluator/mapping_parser/mapping/JsonMapping.py::parse_mapping`):

```json
{
  "classes": [
    { "id": "author_@@author.aid@@",   // URI template; @@table.column@@ is the primary-key placeholder
      "class": "Author",
      "name": "AuthorPerson",          // class-map name, referenced by joins
      "prefix": "mondial",             // default "base"
      "subClassOf": ["Person"],
      "bNodeIdColumns": "…", "condition": "…", "join": ["…"], "translateWith": "…" }
  ],
  "object_properties": [
    { "property": "hasCity", "belongsToClassMap": "CountryFull",
      "refersToClass": "City",         // or "refersToClassMap"
      "join": ["city.country = country.code"], "inverseOf": "cityIn" }
  ],
  "data_properties": [
    { "property": "population", "belongsToClassMap": "CountryFull",
      "type": "integer", "column": "Country.Population" }
  ],
  "translation_tables": [ { "name": "…", "translations": {} } ]   // optional
}
```

The `meta.json` sidecar provides `relation_prefix` and `prefixes` (short name -> URI).
Upstream README, verbatim: *"For better readability, we decided to choose a `JSON` format,
which is automatically translated to `D2RQ`."*

## Metrics (18 numbers)

Two families × three element kinds × {precision, recall, F1} (F1 derived as `2PR/(P+R)`):

- **`mapping_based`** (called "Mapping" in the upstream tables): set/multiset comparison.
  Equality uses `concept_based_equality`: two mappings match iff they
  **map the same SQL source to the same ontology concept**, not because their names match.
  `precision = Σ min(count_ref, count_learned) / Σ count_learned`;
  `recall = Σ tp / Σ count_ref`. **This is the benchmark's contribution.**
- **`name_based`** (called "Lexical" in the tables): set comparison by pure **literal name matching**.

Element kinds (`evaluator/metrics/caclulate_metrics.py`):
`cls_*` (classes), `rel_*` (object properties), `attr_*` (data properties).

**⚠️ The upstream README tables use C / R / A for Class / Relation / Attribute,
and "Mapping" / "Lexical" for the two families, but the README never defines these abbreviations.**
You have to read the code to understand them. Sample values (Mondial / Ontop): mapping C 0.56, R 0.28, A 0.51;
lexical C 0.38, R 0.00, A 0.35.
The README also carries a correction banner: *"Values updated after correcting a small number of
missing database constraints in Mondial and NPD"*; copied tables with different numbers are stale.

## How Knosis uses it

- Loader (`knosis/data/loaders/burr.py`): a scenario is a real-world database name (`mondial`, `npd`, `iswc`, `rba`),
  a single micro scenario (e.g. `basic/table/person`), or a micro group: `micro` (all 54) or `micro/<category>`.
  One task per scenario; the input is the DDL (the smallest `.sql` whose name contains `schema` or `create`,
  else the smallest `.sql`), the answer is `mapping.json`, `mappings/*.json` (excluding `meta.json`), or `*.ttl`.
- Exporter (`knosis/workspace/exporters/burr.py`): the agent gets only the `.sql` and `.csv` files;
  gold mappings stay in the raw directory. A single scenario is one test task with no dev;
  a group defaults to about 1/4 of its scenarios as dev (at least 1). Output: `predictions.jsonl`.
- Scorer (`knosis/decision/burr.py`): a port of upstream `evaluator/metrics` and the `mapping_parser` comparison
  for JSON mappings (no LLM). Reports `{mapping_based,name_based}_{cls,rel,attr}_{precision,recall,f1}`;
  a task's `score` is the mean of the three `mapping_based` F1 values.
  **D2RQ `.ttl` ground truth (npd, iswc) is not supported by the scorer yet.**

## Known issues

- **`docker-compose.yml` is broken out of the box**: it hardcodes the maintainer's local path
  `/home/lukas/burr/Burr/result:/results` and sets `runtime: nvidia`, so it will not run on non-NVIDIA machines.
- **The default experiment config runs only `real_world`**: in `config_template.py` the micro-benchmark entries
  are all commented out, and only `d2rmapper` is enabled under `systems`.
  To reproduce the paper's micro tables you must edit the config.
- **`pip install -e .` still needs a live Postgres**, with every SQL file imported.
  **Upstream has no "read files only" path.**
- **W&B is pulled in at import time**: both `caclulate_metrics.py` and `ExperimentManager.py`
  start with `import wandb`, unavoidable even with `USE_WANDB=false`.
- **The metrics file name is misspelled `caclulate_metrics.py`** (missing an l); keep that in mind when grepping.
- The repo contains `.DS_Store`, an `old/` subdirectory, and two `unfinished_*.sjson`
  files: lab artifacts, not release artifacts.
