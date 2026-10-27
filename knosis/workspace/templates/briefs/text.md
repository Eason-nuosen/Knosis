# Text corpus — $name

## What the data is

`data/` holds the raw corpus: $n_files files, $n_chars characters (relative paths kept as in the original):

$listing

The corpus may contain noise (duplicate, contradictory, wrong or outdated content); what counts as noise and how to handle it is up to you.

## What the downstream task is

This workspace has no downstream questions; the goal is to build an auditable knowledge layer from the corpus (κ units; structural content may also be written as an ontology).
The decide stage does not require delivering predictions; just run `knosis ws check .` to finish.

## What the knowledge should serve

Make later QA and analysis based on this corpus more reliable: entities, relations, events, numbers, rules and the conditions under which they hold can all be extracted.
The source of every piece of knowledge must be locatable in the original text: write `provenance` as `data/<file>#<start>-<end>` (character offsets, half-open interval, counted on the string after UTF-8 decoding);
join multiple sources with ` ; `. You may put a quotation from the original in `meta.quote`; it must appear in the cited span.
Evaluation looks only at the knowledge layer itself: whether sources can be located, whether quotations are accurate, and the composition of the units.
