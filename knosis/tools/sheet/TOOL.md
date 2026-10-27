---
name: sheet
version: "0.1"
kind: program
modality: [spreadsheet]
stage: [explore, extract, refine, decide]
license: "Apache-2.0 (bundled with Knosis)"
---

Spreadsheet (xlsx / xlsm) structure inspection and formula recalculation, with two subcommands:

- `inspect`: for each sheet, the used range, merged cells, number of data validations and conditional formats, number of formula cells, and for the requested region each cell's value, formula and number format.
  Formula cells also show the cached value (what openpyxl reads with `data_only=True`; formulas written by openpyxl have no cached value and read as None).
  Produces κ: one `schema` per sheet (used range, merged cells, formula count; observed).
- `recalc`: opens the file in LibreOffice, recalculates the formulas and saves a copy (the same processing as at evaluation time), then reads the recalculated values for `--range`.
  Use it to check what your own formulas will evaluate to at evaluation time. It produces no κ.

```bash
knosis tool run sheet -- inspect data/13-1/1_input.xlsx --out stages/1_explore/sheet_13-1
knosis tool run sheet -- inspect data/13-1/1_input.xlsx --range "LISTS!A1:E20" --out stages/1_explore/sheet_13-1
knosis tool run sheet -- recalc stages/4_decide/outputs/13-1/1_output.xlsx --range "LISTS!A3:D32" --out stages/4_decide/recalc
```

The result is written to `inspect.json` / `recalc.json` under `--out` and printed (truncated) to stdout.
`--range` uses the same syntax as SpreadsheetBench's `answer_position`: `A1:D10`, `'Sheet 1'!A1:D10`, multiple regions separated by commas;
without a sheet name the first sheet is used. Without `--range`, `inspect` lists at most the top-left 30 rows × 15 columns of each sheet.
Requires openpyxl; `recalc` requires LibreOffice (`KNOSIS_SOFFICE` can set the soffice path).
