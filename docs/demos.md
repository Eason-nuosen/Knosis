# Demo results

Each dataset entry was run end to end once, at small scale. The agent proposes, verifies and revises knowledge;
Knosis records the evidence and scores both the knowledge and the downstream task.
Units, evidence, outlines and knowledge graphs from these runs can be browsed on the demo site: https://eason-nuosen.github.io/Knosis/

**Each setting is a single run on a small number of tasks. The numbers show that the pipeline works and what behavior appears;
they are not statistical conclusions.** Workspaces are local and not part of the repository.

## 1. One full run per dataset

Setup: Codex (`gpt-6.1-sol`, reasoning effort medium) in driver mode,
`knosis ws run <ws> --stage explore extract refine decide --rounds 2 --consolidate`
(consolidation steps: dedup, conflict handling, organize). Each workspace took 21 to 37 minutes.

| Dataset | Setting | Test result | Knowledge (active / all, usage units, skills) | Consolidation operations |
| --- | --- | --- | --- | --- |
| NGDBench ngd-fin | curated set, dev 10 / test 20 | EM 0.60, F1 0.72 (reference: Cypher on the noisy graph, EM 0.10) | 50 / 51 (3 contested), 17, 1 | narrow 9 |
| TabArena healthcare_insurance_expenses | dev 100 | RMSE 4000, MAE 2296, R² 0.880 (training-mean reference RMSE 11558) | 21 / 35, 13, 1 | narrow 18, rewrite 12, status 12 |
| RelBench rel-f1 driver-top3 | val split as dev | AUROC 0.837 (trivial baseline 0.5) | 52 / 60, 29, 1 | narrow 8 |
| BI-Bench project 149612320 | dev 1 / test 2 | 2/2 | 50 / 53, 8, 1 | narrow 6, conflict marked 4 |
| KramaBench archeology | dev 3 / test 9 | 4/9 | 64 / 68 (14 contested), 20, 3 | merge 1, narrow 11 |
| Burr micro/basic | dev 3 / test 9 | 9/9; class / relation / attribute F1 all 1.0 | 72 / 79, 20, 4 | narrow 11 |
| LLM-SRBench lsr_synth_matsci | dev 2 / test 3 | Acc₀.₁ 1/3, OOD 3/3 | 41 / 52, 16, 1 | narrow 4, rewrite 1 |
| NewtonBench m0_gravity | dev 2 / test 4 | 4/4 | 45 / 48, 19, 1 | none (the agent found no duplicates or conflicts) |
| AlphaBench evaluate | dev 10 / test 30 | signal accuracy 0.33 (all-Noise reference 0.23), RankIC Spearman 0.53 | 56 / 58, 16, 1 | narrow 13, rewrite 1 |
| text (Knosis docs/) | no tasks | 71 units; source resolution rate and citation check both 1.0 | 70 / 71, 0, 2 | narrow 8, rewrite 1 |
| SpreadsheetBench all | dev 5 / test 15 instructions | soft 0.711, hard 0.60 (reference: input returned unchanged, soft 0.111) | 57 / 60 (5 contested), 25, 6 | narrow 9, rewrite 1 |

Observations:

- **Conflict handling mostly narrows conditions.** Most runs rewrote conditions in this step; retraction by new evidence and
  supersession were rare. Only BI-Bench kept a pair of units marked with `conflicts_with` (the candidate involved was retracted).
- **Dedup rarely fires.** Agents already merged duplicates during refine (BI-Bench 1, Burr 4); consolidation merged one more on KramaBench.
- **`contested` takes effect.** On NGDBench (3) and KramaBench (14), usage units were marked contested because dev statistics showed
  that citing the knowledge went with wrong answers; contested units are not selected by default.
- **Organize** passed acceptance in every run (outlines of 13 to 25 sections, 3 to 4 levels); it added no induced units
  (those were written during refine).
- **NGDBench** uses 30 hand-checked questions (`-o curated=ngd-fin-demo`): the upstream natural-language questions often disagree with
  their Cypher / GT (dropped constants, flipped negations, wrong relation or endpoint). Share of questions whose text does not contain all
  Cypher constants or does not mention the relations used: NGD-Fin 72.6% (of 8250), NGD-Bi 67.4% (27440), NGD-MCP 40.1% (12500),
  NGD-Econ 3.0% (2757), NGD-Prime 0.0% (23165). The curated questions were rewritten to match the Cypher semantics and recomputed on
  the clean graph.
- **SpreadsheetBench** (real Excel-forum requests, 3 test cases per instruction, formulas recalculated with LibreOffice before scoring;
  35.6 minutes): cell-level instructions 0.74 / 0.62 soft / hard (13), sheet-level 0.50 / 0.50 (2). Dev feedback went from 2/5
  instructions fully correct on the first submission to 5/5 in refine round 1. Most failures are value type and format: a date written
  as the text '21/06/2022' where a date is expected, '15 Nov 2021' the other way round, 'GOOD' vs 'Good'. Three usage units were marked
  contested because dev statistics showed that tasks applying the "formula cache repair" procedure were answered wrongly.

## 2. Extracting knowledge from agent traces

Entry point: `knosis ws init traces <name> -o paths=<traces> [-o env=<data directory the traces ran against>]`.
Traces are normalized to ATIF v1.7 and knowledge cites them as `data/traces/<id>.json#step/<n>`.
The BRIEF asks the agent to treat what the trace says as that agent's claim, not as fact: re-check it when an environment is
available, otherwise keep it `inferred`. The scorer reports:

- `cites_trace`: share of units citing trace steps that exist;
- `env_verified`: share with supporting evidence that touched the environment;
- `trace_checked`: share only checked for consistency with the trace.

**A. Codex, from its own trace, with an environment.** The source trace is a Codex run answering the 20 NGDBench test questions
without knowledge (16 ATIF steps, 13 tool calls, test EM 0.65). Extraction had the same noisy graph as its environment.
explore → extract → refine took about 17 minutes and produced 37 units (4 method units) and 2 skills; 22 verified, 4 candidates
refuted and retracted; `env_verified` 0.97.

- Example: the trace claimed that repairing interest rates to the value shared within each (loanAmount, loanUsage) group fixed
  the anomalous rates. Recomputed on the environment, the repair changed 0 nodes (`explore/rate-repair-no-effect`), so the candidate
  "the group repair works" was refuted and retracted.
- Other units: node type follows the ID prefix (1008 nodes have conflicting labels), the parallel-edge count identity E=U+D,
  multiplicity of two-hop connections, quality screens for dates, categories and rates.

Transfer test: the extracted knowledge was merged into a knowledge base and inherited by a workspace that ran only decide on
10 questions the source trace never saw:

| Condition | Test EM (two runs) | EM on noise-affected questions |
| --- | --- | --- |
| No knowledge | 0.70 / 0.70 | 0.625 |
| Inherited trace knowledge (K_inherit) | 0.30 / 0.30 | 0.125 |

Per-question results were identical across the two runs, so the gap is not run-to-run noise. The noisy graph contains edges with
altered relations (e.g. a Person→Account edge labeled `Company_Own_Account`). Without knowledge, the agent repaired such edges from
the operation name and endpoint prefixes. The inherited knowledge correctly stated that most of the 7706 conflicting edges have no
unique repair, so the agent queried by the raw label without repairing and missed those edges. The knowledge was correct but harmful
for the task: the source trace had no answer feedback, so extraction could not learn which repair strategy helps, and no usage
knowledge existed. Knowledge extracted from feedback-free traces needs a usage check (dev feedback or ablation) before it is used
for decisions; verifying correctness alone is not enough.

**B. AppWorld traces, no environment.** Source: 6 Spotify trajectories of Qwen3.8-27B on test_normal (4 succeeded, 2 failed;
137 ATIF steps), from the agent-rsi project. Extraction took about 16 minutes and produced 43 units (6 retracted) and 3 skills.
`env_verified` 0, `trace_checked` 1.0: every check could only confirm that a claim matches the trace, so only method units were
marked verified and the rest stayed `inferred`.

Compared one by one against 356 Spotify units that the agent-rsi pipeline verified in the real environment (from other trajectories,
no overlapping scenarios):

| Against agent-rsi | Units |
| --- | --- |
| About the trace files themselves (truncation, visibility), not compared | 7 |
| Agree | 7 |
| agent-rsi is more precise, compatible | 5 |
| Not covered by agent-rsi | 18 |
| Contradict | 0 |

- Agreement examples: after login, `access_token` must be passed explicitly or the API returns 401; `play_music` takes at most one of
  song / album / playlist / queue_position; liked songs, the song library and downloaded songs are different sets.
- More precise in agent-rsi: `page_limit` above 20 returns 422 and the default behaves as 5. Such facts need experiments in the
  environment and cannot be seen in the trace.
- Not covered: task-outcome lessons ("every API call succeeded but the task failed", "partial success is not acceptance"),
  aggregation and set-reasoning methods, and phone app semantics.
- The comparison was made unit by unit by a sub-agent, without human review.

When a workspace is merged into a knowledge base, the cited traces are copied into `evidence/traces/` and sources are rewritten
to point there, so they still resolve after inheritance.

## Known limitations

- One run per setting on few tasks; most differences between conditions are within noise.
- GT isolation is soft: the raw data and the agent are on the same machine.
- KramaBench approximate-string questions and symbolic equivalence of equations are not judged by an LLM.
- For trace extraction, `env_verified` counts a check-based evidence entry as environment-backed when its inputs include environment
  files; `data_inputs` records all data files of the workspace, so this is generous.
