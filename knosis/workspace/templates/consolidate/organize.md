# Consolidation 3/3: build the knowledge system

Knowledge layer root: `$base` ($n_units active κ, $n_skills skills, $n_inactive inactive).
Goal: link scattered single-hop knowledge (each unit about only one object or one-step relation) into a clear thread, written to `$base/kb/outline.yaml`.

## Inputs

- `$base/kb/knowledge/units.jsonl`, `$base/kb/skills/*/SKILL.md`, `$base/evidence/ledger.jsonl`;
  you can inspect them with `knosis knowledge select --ws $base --include-inactive`, `knosis knowledge trace <id> --ws $base`.
- A draft generated automatically by scope: `$draft` (`knosis knowledge outline --ws $base --draft` shows the rendered result).
- $existing

## Requirements

1. Hierarchy from top to bottom: **scenario** (task, goal, and the usage meta-knowledge and skills useful for it) → **relations between data** (structure between entities / tables / variables)
   → **the data itself** (overall dataset regularities, specific objects). method can be a separate "methods" branch, or hang under the scenario that uses it.
   Group by meaning, not mechanically by scope or file only; put knowledge on the same topic together; a section usually has 2 to 15 units.
2. Each section has a `title` and a `summary` (one or two sentences: what the knowledge in this section covers and which kind of task it is useful for). **The summary only summarizes what the member units already say**;
   it adds no assertions and no speculation beyond the numbers; correctness is still determined by the units and evidence.
3. Every active κ and skill (`skill:<name>`) goes into at least one section; it can go into several. Ontology units (`ontology/...`) need not be listed one by one.
   Retracted, inactive and merged units may only go into sections with `archive: true`, or be left out.
4. Dedup and contradiction handling were done in the previous two steps; for anything you still find suspicious, write it in the `notes` of its section (list the ids and reasons), without changing the original units.
5. **Induction**: if, while linking, several single-hop pieces of knowledge can be combined into a higher-level regularity (several specific objects → an overall dataset regularity; several successful practices → method),
   you may add induced units to `kb/knowledge/units.jsonl`: `provenance` is `derived`, `derived_from` lists all original units (at least two),
   `status` is `inferred` (when it can be verified, verify as usual and record evidence before changing it to verified). Induce only when you are truly confident, and do not change the original units.
6. Apart from induced units, do not modify `units.jsonl`, evidence or skills; write the outline to `kb/outline.yaml`. See the draft and the example below for the format.

```yaml
title: <name of this knowledge system>
summary: <one or two sentences>
sections:
  - id: scene-gravity
    title: "Scenario: discovering power laws from controlled experiments"
    summary: ...
    units: [skill:discover-positive-power]
    sections:
      - id: scene-gravity/method
        title: Methods for estimating the exponent
        summary: ...
        units: [extract/single-axis-scaling, extract/log-domain-check]
  - id: archive
    title: Retracted
    archive: true
    units: [extract/all-inverse-square]
```

## Acceptance check

`knosis knowledge outline --ws $base` has no "Uncategorized" section at the end, and `knosis knowledge check --ws $base` introduces no new problems$check_note.
Finally, explain in two or three sentences how the thread is organized and what you induced.
