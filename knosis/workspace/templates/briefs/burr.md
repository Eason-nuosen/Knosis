# Burr — $scenario

## What the data is

Relational databases: `.sql` files are PostgreSQL table definitions (DDL, some also with INSERTs of instance data), and `.csv` files are table instance data.
$layout. Each question corresponds to one database (the question's `files` lists its files).
The data may contain noise (e.g. ambiguous naming, missing constraints); what counts as noise and how to handle it is up to you.

## What the downstream task is

For each database, write its mapping to an ontology: which concepts (classes) the database contains, which relations hold between concepts, which properties the concepts have,
and which tables, columns and joins each of them comes from. `tasks/dev.jsonl` has $n_dev dev questions; the test questions ($n_test) are given in the decide stage.

Deliver `predictions.jsonl`, one line `{"id": question id, "answer": mapping}` each, with the mapping in Burr's JSON format:

```json
{"classes": [{"id": "<instance URI pattern; reference columns with @@table.column@@, e.g. thing/@@t.id@@>", "class": "<class name>", "name": "<mapping name, defaults to the class name>",
              "condition": "<optional, SQL condition>", "join": ["<optional, a.x = b.y>"], "subClassOf": "<optional, parent class>"}],
 "object_properties": [{"property": "<relation name>", "belongsToClassMap": "<mapping name>", "refersToClassMap": "<mapping name>",
                        "join": ["a.x = b.y"], "condition": "<optional>"}],
 "data_properties": [{"property": "<property name>", "belongsToClassMap": "<mapping name>", "type": "<string|integer|...>",
                      "column": "<table.column>", "sqlExpression": "<optional, SQL expression used instead of column>"}]}
```

Evaluation (ported from the upstream Burr evaluator): precision / recall / F1 for classes, relations and properties, under two conventions:
**mapping-based** checks whether the mapped data agrees (columns in the URI pattern, conditions, joins, column / expression);
**name-based** checks whether class names, relation names and property names (and the names of their owning classes) agree.

You may first write the structure as an ontology under `kb/knowledge/ontology/` (OSI three layers) and then convert it to the delivery format above; this is not required.

## What the knowledge should serve

Make unseen databases mapped more accurately: common patterns from table structure to concepts, how to infer concepts and relations from keys, foreign keys, naming and instance data,
which tables are association tables, how inheritance shows up, and so on can all be written as knowledge. Knowledge should be reusable; it should not cache answers to specific test questions.
