# SpreadsheetBench —— 真实电子表格操作（OJ 风格多测试用例）

## 来源

中国人民大学等，**SpreadsheetBench: Towards Challenging Real World Spreadsheet Manipulation**，arXiv **2406.14991**，
NeurIPS 2024 Datasets and Benchmarks。仓库 https://github.com/RUCKBReasoning/SpreadsheetBench ；
数据 https://huggingface.co/datasets/KAKA22/SpreadsheetBench ；排行榜 https://spreadsheetbench.github.io/ 。
许可：CC BY-SA 4.0。

获取：从 HF 下载 `spreadsheetbench_912_v0.1.tar.gz`（约 96 MB，解压约 168 MB），解压到 `data/spreadsheetbench/`，
得到 `all_data_912_v0.1/{dataset.json, spreadsheet/<id>/<n>_<id>_{input,answer}.xlsx}`。

## 说明

- 912 条指令（Cell-Level 561、Sheet-Level 351），来自 ExcelForum、MrExcel 等 4 个论坛的真实帖子，GPT-4 改写、人工校验；
  答案由帖子回复里的公式或 VBA 应用到表格生成。905 条有 3 个测试用例（同一指令、不同数据或位置），共 2729 个。
- 评测只比较 `answer_position` 内单元格的值；上游先用 LibreOffice / Excel 重算公式（`open_spreadsheet.py`），
  再用 openpyxl `data_only=True` 读取比较。上游颜色比较的代码已注释掉。
- scenario：`all`、`cell`、`sheet`（按指令类型）。

## 陷阱

- **公式不重算**：openpyxl 写入的公式没有缓存值，不重算读出来是 None。Knosis 打分器评测前一律用 LibreOffice 重算
  （需要 LibreOffice；`KNOSIS_SOFFICE` 可指定路径）。LibreOffice 与 Excel 的个别函数结果可能不同。
- `answer_position` 写法不统一：sheet 名引号有时缺一边、小写列名、全角冒号、整列（`A:G`）、终点缺列名（`BD2:308`）；
  打分器都做了兼容。有的 sheet 名带首尾空格。
- 上游现行 `evaluation.py` 的 `proc_path` 指向输入文件（模型输出那一行被注释掉），直接运行等于拿输入和答案比。
- 有的答案带 TODAY() / NOW()（如按出生日期算年龄），缓存值是标注当天算的；打分器把这类答案文件与输出一起重算。
- 有的 `answer_position` 的 sheet 名与文件不一致（如 `Sheet 2` 对 `Sheet2`），上游脚本会直接判错；打分器按去空格、忽略大小写匹配。
- 少数指令带 `.xlsm`（宏），导出器默认跳过（`-o xlsm=true` 放开）。
- 原样交回输入表格也能拿到少量分（答案区本来就有部分正确值），评测报告里作为参照。
- Verified 400 子集（2025-12）每题只有 1 个用例、前几名已近饱和；本入口用 912 全集。
