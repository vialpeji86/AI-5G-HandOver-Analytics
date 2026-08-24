from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd


def export_professional_xlsx(sheets: Dict[str, pd.DataFrame], out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe = name[:31]
            df.to_excel(writer, sheet_name=safe, index=False)

        wb = writer.book
        for ws in wb.worksheets:
            max_row = ws.max_row
            max_col = ws.max_column
            for c in range(1, max_col + 1):
                cell = ws.cell(row=1, column=c)
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = cell.fill.copy(fill_type="solid", start_color="0F4C81", end_color="0F4C81")

            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{ws.cell(max_row, max_col).coordinate}"

            for col in ws.columns:
                values = [str(x.value) if x.value is not None else "" for x in col[:1000]]
                width = min(max((len(v) for v in values), default=10) + 2, 42)
                ws.column_dimensions[col[0].column_letter].width = max(12, width)

            headers = [ws.cell(row=1, column=i).value for i in range(1, max_col + 1)]
            pct_cols = [
                i for i, h in enumerate(headers, start=1) if isinstance(h, str) and ("Rate" in h or "%" in h or "Coverage" in h)
            ]
            dist_cols = [i for i, h in enumerate(headers, start=1) if isinstance(h, str) and "Distance" in h]

            for c in pct_cols:
                for r in range(2, max_row + 1):
                    ws.cell(row=r, column=c).number_format = "0.00%"
            for c in dist_cols:
                for r in range(2, max_row + 1):
                    ws.cell(row=r, column=c).number_format = "0.00"

    return out
