from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd


SUPPORTED_EXT = {".csv", ".txt", ".xls", ".xlsx"}


def load_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXT:
        raise ValueError(f"Unsupported file type: {ext}")
    if ext in {".csv", ".txt"}:
        return pd.read_csv(p)
    return pd.read_excel(p)


def load_many(paths: List[str | Path]) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for item in paths:
        p = Path(item)
        if p.suffix.lower() in SUPPORTED_EXT and p.exists():
            data[p.name] = load_table(p)
    return data
