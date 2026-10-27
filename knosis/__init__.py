"""Knosis: a knowledge substrate for agents. Four layers plus a workspace:

    knosis.data        data layer: single entry point load_dataset; every dataset returns a Dataset
    knosis.knowledge   knowledge layer: κ units (units.jsonl) + ontology sublayer (Ossie three-file format)
    knosis.tools       tool layer: SQL / table profiling / join discovery / ULTRA / TabPFN, each a TOOL.md + run.py
    knosis.decision    decision layer: scoring decide outputs and knowledge-usage statistics
    knosis.workspace   workspace: orchestration and acceptance of explore → extract → refine → decide

    from knosis import load_dataset
    ds = load_dataset("ngdbench", "ngd-fin")
"""

from .data import Dataset, Task, Unit, data_dir, describe, list_datasets, list_scenarios, load_dataset, read, register

__all__ = [
    "load_dataset", "list_datasets", "list_scenarios", "describe", "register",
    "Dataset", "Task", "Unit", "data_dir", "read",
]
__version__ = "1.0.0"
