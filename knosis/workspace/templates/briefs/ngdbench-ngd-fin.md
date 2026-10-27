# NGD-Fin

## What the data is

An observed property graph from the financial domain, in the file `data/graph.gpickle`.
The graph type is `$graph_type`, with $n_nodes nodes and $n_edges edges.
Node ids look like `Account:9570149208163490`; node and edge types are both in the attribute `label`.
The statistics below come directly from the exported observed graph.

Node types and counts:

$node_types

Node attributes:

$attributes

Edge types and counts:

$edge_types

The observed graph may contain noise: wrong types or attribute values, outliers, extra or missing edges, etc. Explore the data yourself first; what counts as noise and how to handle it is up to you.

## What the downstream task is

Non-aggregate questions require multi-hop lookups; aggregate questions include counting, summing, averaging and comparison.
$query_help
Write nodes as id strings (e.g. `Account:1`).
Evaluation compares answer sets: order and duplicates are ignored, objects are compared by value only, and numbers are kept to 6 significant digits.
The following are task examples only and are not part of the final test; test questions are provided only in the decide stage.

$examples

## What the knowledge should serve

Make unseen questions of the same kind answered more accurately: knowledge about this graph's structure, values, regularities and trustworthiness can all be extracted.
Knowledge should be reusable; it should not cache answers to specific test questions.

$noise_section one assertion per line, pointing out one place in the observed graph that you believe differs from the true graph.

- `{"kind": "node_label", "node": "<node id>"}`: this node's `label` is wrong
- `{"kind": "node_attr", "node": "<node id>", "field": "<attribute name>"}`: this node's value for this attribute is wrong; omitting `field` means some attribute of the node is wrong
- `{"kind": "edge", "src": "<node id>", "dst": "<node id>", "key": <edge key>, "type": "added"}`: this edge should not exist in the observed graph;
  `"type": "relabel"` means the edge exists but its `label` is wrong; `type` may be omitted
- `{"kind": "missing_edge", "src": "<node id>", "dst": "<node id>", "label": "<edge type>"}`: an edge present in the true graph but missing from the observed graph

This file is evaluated separately as knowledge (precision and recall per category) and does not affect the QA score.
