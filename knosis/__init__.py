"""Knosis —— 面向 agent 的知识底座。四层 + 工作区：

    knosis.data        数据层：统一入口 load_dataset，所有数据集返回 Dataset
    knosis.knowledge   知识层：κ 单元（units.jsonl）+ 本体子层（Ossie 三文件）
    knosis.tools       工具层：SQL / 表画像 / join 发现 / ULTRA / TabPFN，统一 TOOL.md + run.py
    knosis.decision    决策层：decide 产物的评测与知识使用统计
    knosis.workspace   工作区：explore → extract → refine → decide 的编排与验收

    from knosis import load_dataset
    ds = load_dataset("ngdbench", "ngd-fin")
"""

from .data import Dataset, Task, Unit, data_dir, describe, list_datasets, list_scenarios, load_dataset, read, register

__all__ = [
    "load_dataset", "list_datasets", "list_scenarios", "describe", "register",
    "Dataset", "Task", "Unit", "data_dir", "read",
]
__version__ = "0.3.0"
