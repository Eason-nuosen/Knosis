# SpreadsheetBench — $scenario

## What the data is

`data/<instruction id>/` holds the input spreadsheets for each instruction: `1_input.xlsx`, `2_input.xlsx` and `3_input.xlsx` are 3 test cases of the same instruction
(the same kind of spreadsheet, with different data or table positions). The spreadsheets come from real help-request posts on Excel forums; headers not on the first row, multiple data blocks in one sheet,
merged cells, numbers or dates stored as text, and similar situations are common. The data may contain noise; what counts as noise and how to handle it is up to you.
The Python environment has openpyxl installed; the `sheet` tool can inspect spreadsheet structure and recalculate formulas with LibreOffice (see `TOOLS.md`).

## What the downstream task is

Each question is a natural-language instruction (`instruction`) asking you to modify the spreadsheet: compute results at a specified location (Cell-Level), or transform a whole data block (Sheet-Level).
`answer_position` gives the region where the answer goes (e.g. `'Sheet1'!D2:D20`, multiple ranges separated by commas; without a sheet name it refers to the first sheet).
`tasks/dev.jsonl` has $n_dev dev instructions; the test instructions ($n_test) are given in the decide stage; this workspace has $n_cell Cell-Level and $n_sheet Sheet-Level instructions in total.
Dev and test are **different instructions**: the knowledge must transfer to instructions you have not seen.

All 3 cases of each instruction must be delivered: save the modified spreadsheets as new files (do not modify the original files in `data/`), and deliver `predictions.jsonl`, one line
`{"id": instruction id, "answer": {"1": "<output path>", "2": "...", "3": "..."}}` each, with paths relative to the directory containing `predictions.jsonl`
(e.g. `outputs/<id>/1_output.xlsx`). Keep the original sheet names and spreadsheet contents, and make only the modifications the instruction asks for.

Evaluation: each output file is first opened in LibreOffice, its formulas recalculated and the file re-saved; then only the cell **values** within `answer_position` are compared
(numbers rounded to 2 decimal places, dates as Excel serial numbers, empty string equals empty, different types are unequal; colors and formatting are not compared).
You may write formulas or values, but formulas must compute the correct result in LibreOffice; you can check first with `knosis tool run sheet -- recalc`.
Metrics: soft = average case pass rate over instructions, hard = fraction of instructions whose 3 cases all pass.

## What the knowledge should serve

Make unseen instructions done correctly as well: methods for locating table layouts and data blocks, common data pitfalls (numbers as text, merged cells, blank rows),
reliable ways to perform each kind of operation (lookup, matching, aggregation, filtering, deletion, reordering), and the actual behavior and limitations of openpyxl / LibreOffice can all be written as knowledge.
Knowledge should be reusable; it should not cache answers to specific instructions.
