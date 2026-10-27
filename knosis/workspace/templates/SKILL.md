---
name: knosis
description: Use in a Knosis workspace, or when the user wants to use Knosis to analyze data, find noise, and extract and verify reusable knowledge (including ontologies); it does not replace ordinary data analysis.
---

Knosis provides a traceable, explicit knowledge layer; the agent in this session is the executor and does not need to launch another agent.

**When there is an MCP server named knosis** (a personal knowledge base installed with `knosis install --kb`): before starting a non-trivial task, call
`knowledge_outline` once to see the knowledge system, then use `knowledge_select` (a few keywords, space-separated) to find knowledge relevant to the task;
inferred / contested knowledge is a hint, verify it before using it. Findings that are truly verified and useful later can be recorded with `knowledge_add`;
the rest need not be recorded manually; `knosis kb collect` collects them uniformly after the session ends.

In a workspace containing `BRIEF.md` and `.knosis/state.json`, read BRIEF and AGENTS.md,
and use `knosis ws next .` to get the current stage's goal, inputs, deliverables and acceptance criteria.
After finishing the deliverables, run `knosis ws check .`; on failure, fix according to the reported problems.
The stages are explore → extract → refine; each refine round saves a snapshot upon passing the acceptance check;
when the user decides to stop improving, use `knosis ws goto . decide` to enter the downstream task.

Outside a workspace, when the user needs this workflow, you can run
`knosis ws init <dataset> <scenario> --out <directory> [--kb <knowledge base>]` (`knosis list` shows supported datasets).
`knosis tool list` and the workspace's `TOOLS.md` provide available tools (SQL, table profiling, join discovery, equation fitting, ULTRA, TabPFN, etc.).

The knowledge layer has two parts: `kb/` holds knowledge (`kb/knowledge/units.jsonl`, `kb/knowledge/ontology/`, `kb/skills/`, `kb/outline.yaml`),
`evidence/` holds sources and verification (`evidence/ledger.jsonl`, `evidence/checks/`, `evidence/feedback/`).
Every κ must have a unique id, content, form, provenance, status.
form is finding/fact/rule/formula/schema/tool/procedure; status is observed/inferred/verified/contested/retracted/stale/merged.
scope has two layers: object knowledge instance / relation / dataset; meta-knowledge method (how to obtain knowledge) / usage (how to make good use of knowledge, supported by feedback or ablation).
Record one piece of evidence per verification (support/refute/undetermined/not_applicable): put executable checks into `check` and then run
`knosis knowledge verify`; for others use `knosis knowledge evidence add`; verified requires supporting evidence, and a refuted unit must change status.
Use `knosis knowledge select` to pick knowledge per task (contested is not returned by default), and `knosis knowledge trace <id>` to see the evidence chain;
when `kb/outline.yaml` exists, first use `knosis knowledge outline` to see the knowledge system.
Write "how to apply knowledge to solve a kind of question" as `kb/skills/<name>/SKILL.md` (it says how to do it); whether it is effective is written as a usage unit.
Consolidation: duplicates become merged + merged_into; contradictions get narrow the condition / retract / superseded_by / conflicts_with + contested;
`knosis knowledge consolidate` does dedup, contradiction handling and building the knowledge system in order; when there is too much knowledge, compress with `knosis knowledge compact [--topic <topic>]`.
Record condition, derived_from, and the number of verification supports and counterexamples; locate sources to rows, columns, nodes or edges of data files;
tool sources are `tool:<name>@<version>(...)`; join multiple sources with ` ; `.
Structural knowledge can be written as an ontology under `kb/knowledge/ontology/` (three OSI layers); a κ references ontology elements with `about`.
Tool output inferred is not fact; after retracting a unit, set derived knowledge to stale or retracted.

Do not modify `data/`; write code and notes into the current stage directory. Test questions appear only in decide;
do not search for test GT outside the workspace, do not run `knosis eval`, and do not cache answers to specific questions as knowledge in advance.
