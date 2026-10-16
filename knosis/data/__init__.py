"""数据层：统一入口 `load_dataset`，所有数据集返回同一个 `Dataset`。"""

from .dataset import DATA_DIR, Dataset, Task, Unit, card, data_dir, read
from .loaders import LOADERS, register

__all__ = [
    "load_dataset", "list_datasets", "list_scenarios", "describe", "register",
    "Dataset", "Task", "Unit", "DATA_DIR", "data_dir", "read",
]


def load_dataset(name: str, scenario: str | None = None, **kw) -> Dataset:
    """`load_dataset("relbench", "rel-f1")`；其余参数原样传给该数据集的 loader。"""
    fn = LOADERS[name]
    return fn(scenario, **kw) if scenario is not None else fn(**kw)


def list_datasets() -> list[str]:
    return list(LOADERS)


def list_scenarios(name: str) -> list[str]:
    s = LOADERS[name].scenarios
    return list(s() if callable(s) else s)


def describe(name: str) -> str:
    return card(name)
