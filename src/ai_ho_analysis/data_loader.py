from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd


SUPPORTED_EXT = {".csv", ".txt", ".tsv", ".xls", ".xlsx", ".xlsm"}


def _clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    seen: dict[str, int] = {}
    cleaned: list[str] = []
    for index, value in enumerate(out.columns, start=1):
        header = str(value).strip() or f"UNNAMED_{index}"
        seen[header] = seen.get(header, 0) + 1
        if seen[header] > 1:
            header = f"{header}_{seen[header]}"
        cleaned.append(header)
    out.columns = cleaned
    return out


def _read_delimited(path: Path) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=encoding)
        except Exception as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError(f"Could not read delimited file {path.name}: {'; '.join(errors)}")


def _read_best_excel_sheet(path: Path) -> pd.DataFrame:
    workbook = pd.ExcelFile(path)
    candidates: list[tuple[int, pd.DataFrame]] = []
    for sheet in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet)
        if frame.empty and len(frame.columns) == 0:
            continue
        nonempty_columns = sum(not str(column).startswith("Unnamed") for column in frame.columns)
        score = nonempty_columns * 1000 + min(len(frame), 999)
        candidates.append((score, frame))
    if not candidates:
        raise ValueError(f"Excel workbook has no readable data sheets: {path.name}")
    return max(candidates, key=lambda item: item[0])[1]


def load_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXT:
        raise ValueError(f"Unsupported file type: {ext}")
    if ext in {".csv", ".txt", ".tsv"}:
        return _clean_headers(_read_delimited(p))
    return _clean_headers(_read_best_excel_sheet(p))


def load_many(paths: List[str | Path]) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for item in paths:
        p = Path(item)
        if p.suffix.lower() in SUPPORTED_EXT and p.exists():
            data[p.name] = load_table(p)
    return data
