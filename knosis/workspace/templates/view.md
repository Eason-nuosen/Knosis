# Visualize the knowledge base

Knowledge layer root: `$base`. Goal: write a web page `$page` that lets people understand this knowledge base in a browser: what knowledge there is, how it is organized, and what the evidence is.

## Available content

$forms

Get the computed forms with commands: `knosis knowledge graph --ws $base --view derivation` (derivation graph: derived_from / merged_into /
superseded_by), `--view cards` (rule and formula cards grouped by object), `--view graph`, `--view flows`;
`knosis knowledge outline --ws $base` renders the outline as markdown; `knosis knowledge trace <id> --ws $base` shows the evidence chain of a piece of knowledge.
$request
## Requirements

1. The page must answer: how many parts the knowledge has and what each covers (outline); which objects there are and what relations (knowledge graph, drawn as nodes and edges); how to do a kind of task
   (flow, drawn as steps and branches); which knowledge is derived from, merged into or replaced by which (derivation graph); the content, form, condition, status and evidence of each piece of knowledge.
   Do not draw forms the knowledge base does not have, and do not fabricate; all content comes from the files above; nodes, edges and steps display the knowledge unit ids they reference,
   and clicking shows that unit's content and evidence.
2. Self-contained and usable offline: embed the data directly in the page, inline scripts, styles and graphics, load nothing from the network (no CDN), and it must work when opened via `file://`.
   You may draw the graphs yourself with inline SVG or canvas.
3. Usable when there is a lot of knowledge: a search box filters by id / content; inactive units (merged / stale / retracted) are hidden by default and can be toggled on.
4. It is recommended to write a generator script `view/build.py` (reads the files above and generates `$page`) and then run it, so that the page can be regenerated after knowledge updates; you may also write the HTML directly.
5. After writing, run `knosis knowledge view --ws $base --check`: it loads the page in a headless browser and reports JavaScript errors during loading and network resources;
   if there are problems, fix them until the output is OK. Fields in the data may be missing (no condition, no evidence, etc.); rendering must tolerate this.
6. Only write the `view/` directory; do not modify any file under `kb/` or `evidence/`, and do not run consolidation or `ws` commands.

## Acceptance check

`$page` exists; it loads no resources from the network; there are no JavaScript errors during loading; the knowledge layer was not modified. Finally, explain in one or two sentences which views the page has.
