# Text corpus (any document collection → schema-free KG)

## Source

No fixed origin: the user points to their own corpus directory: `load_dataset("text", path="./corpus")`.
The corpus itself is not bound by the Knosis license; Knosis only reads, never writes.
The extractor is pluggable: by default it only chunks; real extractors such as AutoSchemaKG are passed in as a function:
`load_dataset("text", path=..., extractor=fn)`, `fn(doc_id, text) -> Iterable[Unit]`.

## Description

Turns a pile of documents into a schema-free knowledge graph. This is the only entry in Knosis where "load directly produces knowledge units":
text has no schema to attach to first, so extraction itself is graph construction.

**What it produces** (all in `ds.units`)

- `doc` units: one per document, with `π` pointing to the file path. With `dedup=True` (the default),
  reposted copies whose normalized content is identical are collapsed and recorded in `ds.schema["duplicates"]`;
  without deduplication, L2 support counts and aggregation would be distorted.
- `chunk` units: chunks cut by `chunk_chars`, with `π` locating `doc_id#start-end`.
  L2 grounding relies on this to get back to the original text.
- When `extractor` is given: additionally the units returned by the extractor (e.g. `entity` / `triple`),
  with relation phrases kept as **open vocabulary**.

**Key conventions**

- The relation vocabulary is open; **do not assume fixed relation types**. Normalization is L2's job;
  doing it here would discard the original phrases, which then cannot be traced back to the original text.
- The extraction configuration and model version should be written into every unit's `provenance`: when the model changes, you should know the knowledge changed.
- `condition` is empty by default. Knowledge from text often carries conditions (time, region, applicable subjects),
  but currently nobody annotates them; do not pretend it is unconditional.

**Pitfalls**

- Unit ids come from relative paths; after deleting or modifying files, rerunning changes the ids.
- Size: run on a subdirectory first. Extraction time is linear in corpus size.
- Non-UTF-8 files are skipped.

**Good for**: giving an agent a traceable, chunk-locatable base map of background knowledge.
**Not good for**: serving as a source for fact verification; there is no GT here, and everything extracted is `observed`.
