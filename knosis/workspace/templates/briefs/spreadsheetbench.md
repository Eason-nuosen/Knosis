# SpreadsheetBench — $scenario

## 数据是什么

`data/<指令 id>/` 下是每条指令的输入表格：`1_input.xlsx`、`2_input.xlsx`、`3_input.xlsx` 是同一条指令的 3 个测试用例
（同一类表格，数据或表格位置不同）。表格来自 Excel 论坛的真实求助帖，常见表头不在第一行、一个 sheet 里有多块数据、
合并单元格、文本形式的数字或日期等情况。数据可能含噪声；哪些是噪声、如何处理，由你判断。
Python 环境已装 openpyxl；工具 `sheet` 可查看表格结构，并用 LibreOffice 重算公式（见 `TOOLS.md`）。

## 下游任务是什么

每道题是一条自然语言指令（`instruction`），要求修改表格：在指定位置算出结果（Cell-Level），或对整块数据做变换（Sheet-Level）。
`answer_position` 给出答案所在的区域（如 `'Sheet1'!D2:D20`，多段用逗号分隔；不写 sheet 时指第一个 sheet）。
`tasks/dev.jsonl` 有 $n_dev 条开发指令，测试指令（$n_test 条）在 decide 阶段给出；本工作区共 $n_cell 条 Cell-Level、$n_sheet 条 Sheet-Level。
开发与测试是**不同的指令**：知识要能迁移到没见过的指令上。

每条指令的 3 个用例都要交：把改好的表格另存（不要改 `data/` 里的原文件），交付 `predictions.jsonl`，每行
`{"id": 指令 id, "answer": {"1": "<输出路径>", "2": "...", "3": "..."}}`，路径相对 `predictions.jsonl` 所在目录
（如 `outputs/<id>/1_output.xlsx`）。保留原有的 sheet 名与表格内容，只做指令要求的修改。

评测：每个输出文件先用 LibreOffice 打开、重算公式并另存，再只比较 `answer_position` 内的单元格**值**
（数值保留 2 位小数，日期按 Excel 序列号，空串等于空，类型不同即不等；不比颜色与格式）。
写公式或写值都可以，但公式必须在 LibreOffice 里算出正确结果；用 `knosis tool run sheet -- recalc` 可以先确认。
指标：soft = 各指令用例通过率的平均，hard = 3 个用例全部通过的指令占比。

## 知识应该服务什么

让没见过的指令也做得对：表格布局与数据块的定位方法、常见的数据坑（文本数字、合并单元格、空行）、
各类操作（查找、匹配、汇总、筛选、删除、重排）的可靠做法、openpyxl / LibreOffice 的实际行为与限制，都可以写成知识。
知识应当可复用，不应缓存具体指令的答案。
