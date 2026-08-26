"""Professional, dependency-free Tkinter dashboard for failure analytics."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import pandas as pd

from .models import AnalysisResult
from .exporter import export_professional_xlsx


COLORS = ("#0B5ED7", "#00A6A6", "#F59E0B", "#DC3545", "#7C3AED", "#5C6B7A")


class FailureDashboard:
    VIEW_CONFIG = {
        "Failure Types": (
            "failure_types",
            "Failure_Type",
            ["Total_Failures", "Failure_Share", "Affected_Relations"],
        ),
        "Source Offenders": (
            "source_offenders",
            "Source_ID",
            ["Total_Failures", "Unique_Peers", "Fail_Rate"],
        ),
        "Target Offenders": (
            "target_offenders",
            "Target_ID",
            ["Total_Failures", "Unique_Peers", "Fail_Rate"],
        ),
    }

    def __init__(self, parent: Any, result: AnalysisResult) -> None:
        self.result = result
        self.window = tk.Toplevel(parent)
        self.window.title("HO Failure Intelligence Dashboard")
        self.window.geometry("1420x850")
        self.window.minsize(1080, 700)
        self.window.configure(bg="#F3F6FB")

        self.view_var = tk.StringVar(value="Failure Types")
        self.metric_var = tk.StringVar(value="Total_Failures")
        self.top_var = tk.IntVar(value=10)

        self._build()
        self.window.after_idle(self.refresh)

    def _build(self) -> None:
        root = ttk.Frame(self.window, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(4, weight=1)

        ttk.Label(
            root,
            text="HO Failure Intelligence Dashboard",
            font=("Segoe UI", 18, "bold"),
            foreground="#0B2A5B",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            root,
            text="Failure mix, multi-peer Source offenders, and shared Target exposure",
            foreground="#4A6FAE",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        controls = ttk.Frame(root)
        controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(controls, text="View").pack(side="left")
        view_combo = ttk.Combobox(
            controls,
            textvariable=self.view_var,
            values=list(self.VIEW_CONFIG),
            state="readonly",
            width=20,
        )
        view_combo.pack(side="left", padx=(6, 16))
        view_combo.bind("<<ComboboxSelected>>", self._view_changed)
        ttk.Label(controls, text="Metric").pack(side="left")
        self.metric_combo = ttk.Combobox(
            controls, textvariable=self.metric_var, state="readonly", width=20
        )
        self.metric_combo.pack(side="left", padx=(6, 16))
        self.metric_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Label(controls, text="Top N").pack(side="left")
        top_combo = ttk.Combobox(
            controls,
            textvariable=self.top_var,
            values=[5, 10, 15, 20, 30, 50],
            state="readonly",
            width=6,
        )
        top_combo.pack(side="left", padx=(6, 16))
        top_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(controls, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(controls, text="Export Current View...", command=self._export_current).pack(
            side="right"
        )

        cards = ttk.Frame(root)
        cards.grid(row=3, column=0, columnspan=2, sticky="new", pady=(0, 10))
        for index in range(4):
            cards.columnconfigure(index, weight=1)
        totals = [
            ("Total Failures", self._total_failures()),
            ("Failure Types", len(self.result.failure_types)),
            ("Source Offenders", len(self.result.source_offenders)),
            ("Target Offenders", len(self.result.target_offenders)),
        ]
        for index, (label, value) in enumerate(totals):
            card = tk.Frame(cards, bg="white", highlightbackground="#D8E1EC", highlightthickness=1)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 5))
            tk.Label(
                card, text=label, bg="white", fg="#5C6B7A", font=("Segoe UI", 10)
            ).pack(anchor="w", padx=12, pady=(10, 2))
            tk.Label(
                card,
                text=f"{value:,.0f}",
                bg="white",
                fg="#0B2A5B",
                font=("Segoe UI", 20, "bold"),
            ).pack(anchor="w", padx=12, pady=(0, 10))

        bar_box = ttk.LabelFrame(root, text="Ranked View")
        bar_box.grid(row=4, column=0, sticky="nsew", padx=(0, 6))
        self.bar_canvas = tk.Canvas(bar_box, bg="white", highlightthickness=0, height=360)
        self.bar_canvas.pack(fill="both", expand=True, padx=6, pady=6)

        pie_box = ttk.LabelFrame(root, text="Failure Mix")
        pie_box.grid(row=4, column=1, sticky="nsew", padx=(6, 0))
        self.pie_canvas = tk.Canvas(pie_box, bg="white", highlightthickness=0, height=360)
        self.pie_canvas.pack(fill="both", expand=True, padx=6, pady=6)

        table_box = ttk.LabelFrame(root, text="Dashboard Data")
        table_box.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        root.rowconfigure(5, weight=1)
        self.table = ttk.Treeview(table_box, show="headings", height=9)
        yscroll = ttk.Scrollbar(table_box, orient="vertical", command=self.table.yview)
        xscroll = ttk.Scrollbar(table_box, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        self._view_changed()

    def _total_failures(self) -> float:
        if self.result.failure_types.empty:
            return 0.0
        return float(
            pd.to_numeric(
                self.result.failure_types.get("Total_Failures"), errors="coerce"
            ).sum()
        )

    def _view_changed(self, _event: Any = None) -> None:
        _attribute, _label, metrics = self.VIEW_CONFIG[self.view_var.get()]
        self.metric_combo["values"] = metrics
        if self.metric_var.get() not in metrics:
            self.metric_var.set(metrics[0])
        self.refresh()

    def _current_data(self) -> tuple[pd.DataFrame, str, str]:
        attribute, label_column, _metrics = self.VIEW_CONFIG[self.view_var.get()]
        frame = getattr(self.result, attribute).copy()
        metric = self.metric_var.get()
        if metric in frame.columns:
            frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
            frame = frame.sort_values(metric, ascending=False, na_position="last")
        return frame.head(max(1, int(self.top_var.get()))), label_column, metric

    def refresh(self) -> None:
        frame, label_column, metric = self._current_data()
        self._draw_bars(frame, label_column, metric)
        self._draw_failure_mix()
        self._populate_table(frame)

    @staticmethod
    def _format_metric(metric: str, value: float) -> str:
        if "Rate" in metric or "Share" in metric:
            return f"{value:.1%}"
        return f"{value:,.0f}"

    def _draw_bars(self, frame: pd.DataFrame, label_column: str, metric: str) -> None:
        canvas = self.bar_canvas
        canvas.delete("all")
        width = max(680, canvas.winfo_width())
        height = max(330, canvas.winfo_height())
        if frame.empty or label_column not in frame.columns or metric not in frame.columns:
            canvas.create_text(width / 2, height / 2, text="No data available", fill="#5C6B7A")
            return
        values = pd.to_numeric(frame[metric], errors="coerce").fillna(0)
        maximum = max(float(values.max()), 1e-12)
        left = 210
        right = 90
        top = 18
        row_height = max(22, min(42, (height - 35) / max(1, len(frame))))
        for index, ((_, row), value) in enumerate(zip(frame.iterrows(), values)):
            y = top + index * row_height
            label = str(row[label_column])
            if len(label) > 29:
                label = label[:26] + "..."
            canvas.create_text(left - 8, y + 9, text=label, anchor="e", fill="#243B53")
            bar_width = (width - left - right) * (float(value) / maximum)
            canvas.create_rectangle(
                left,
                y,
                left + max(2, bar_width),
                y + 18,
                fill=COLORS[index % len(COLORS)],
                outline="",
            )
            canvas.create_text(
                left + max(4, bar_width) + 6,
                y + 9,
                text=self._format_metric(metric, float(value)),
                anchor="w",
                fill="#0B2A5B",
                font=("Segoe UI", 9, "bold"),
            )

    def _draw_failure_mix(self) -> None:
        canvas = self.pie_canvas
        canvas.delete("all")
        all_failures = self.result.failure_types.copy()
        frame = all_failures.head(5).copy()
        if frame.empty:
            canvas.create_text(200, 160, text="No failure types available", fill="#5C6B7A")
            return
        all_values = pd.to_numeric(
            all_failures["Total_Failures"], errors="coerce"
        ).fillna(0)
        total = float(all_values.sum())
        if total <= 0:
            return
        other = float(all_values.iloc[5:].sum())
        if other > 0:
            frame = pd.concat(
                [
                    frame,
                    pd.DataFrame(
                        [{"Failure_Type": "Other", "Total_Failures": other}]
                    ),
                ],
                ignore_index=True,
            )
        values = pd.to_numeric(frame["Total_Failures"], errors="coerce").fillna(0)
        width = max(400, canvas.winfo_width())
        size = min(220, max(150, canvas.winfo_height() - 90))
        x0, y0 = 25, 25
        start = 90.0
        for index, ((_, row), value) in enumerate(zip(frame.iterrows(), values)):
            extent = -360.0 * float(value) / total
            color = COLORS[index % len(COLORS)]
            canvas.create_arc(
                x0,
                y0,
                x0 + size,
                y0 + size,
                start=start,
                extent=extent,
                fill=color,
                outline="white",
                width=2,
            )
            start += extent
            legend_x = min(width - 220, x0 + size + 25)
            legend_y = 30 + index * 42
            canvas.create_rectangle(
                legend_x, legend_y, legend_x + 14, legend_y + 14, fill=color, outline=""
            )
            label = str(row["Failure_Type"])
            if len(label) > 25:
                label = label[:22] + "..."
            canvas.create_text(
                legend_x + 20,
                legend_y,
                text=label,
                anchor="nw",
                fill="#243B53",
                font=("Segoe UI", 9, "bold"),
            )
            canvas.create_text(
                legend_x + 20,
                legend_y + 18,
                text=f"{float(value) / total:.1%}",
                anchor="nw",
                fill="#5C6B7A",
            )
        inner = size * 0.48
        offset = (size - inner) / 2
        canvas.create_oval(
            x0 + offset,
            y0 + offset,
            x0 + offset + inner,
            y0 + offset + inner,
            fill="white",
            outline="white",
        )
        canvas.create_text(
            x0 + size / 2,
            y0 + size / 2 - 8,
            text=f"{total:,.0f}",
            fill="#0B2A5B",
            font=("Segoe UI", 16, "bold"),
        )
        canvas.create_text(
            x0 + size / 2,
            y0 + size / 2 + 14,
            text="failures",
            fill="#5C6B7A",
        )

    def _populate_table(self, frame: pd.DataFrame) -> None:
        self.table.delete(*self.table.get_children())
        self.table["columns"] = list(frame.columns)
        for column in frame.columns:
            self.table.heading(column, text=column)
            self.table.column(column, width=145, anchor="w")
        for _, row in frame.iterrows():
            values = []
            for value in row.tolist():
                if isinstance(value, float) and math.isfinite(value):
                    values.append(f"{value:.4g}")
                else:
                    values.append(value)
            self.table.insert("", "end", values=values)

    def _export_current(self) -> None:
        frame, _label_column, _metric = self._current_data()
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Dashboard View",
            defaultextension=".xlsx",
            initialfile=f"{self.view_var.get().replace(' ', '_')}.xlsx",
            filetypes=[("Excel Workbook", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                frame.to_csv(path, index=False)
            else:
                export_professional_xlsx({"Dashboard_View": frame}, path)
        except Exception as exc:
            messagebox.showerror("Dashboard Export", str(exc), parent=self.window)


def open_failure_dashboard(parent: Any, result: AnalysisResult) -> FailureDashboard:
    return FailureDashboard(parent, result)


class CustomChartWindow:
    """Interactive chart initialized from an assistant-created visualization specification."""

    CHART_TYPES = ("Horizontal Bar", "Vertical Bar", "Line", "Donut")

    def __init__(
        self,
        parent: Any,
        frame: pd.DataFrame,
        specification: dict[str, Any],
    ) -> None:
        self.source = frame.copy()
        self.window = tk.Toplevel(parent)
        self.window.title(str(specification.get("title", "AI Custom HO Chart")))
        self.window.geometry("1180x760")
        self.window.minsize(900, 620)
        self.window.configure(bg="#F3F6FB")

        numeric = [
            str(column)
            for column in self.source.columns
            if pd.to_numeric(self.source[column], errors="coerce").notna().any()
        ]
        labels = [str(column) for column in self.source.columns]
        if not labels:
            labels = [str(self.source.columns[0])] if len(self.source.columns) else []
        metric = str(specification.get("metric", ""))
        label = str(specification.get("label_column", ""))
        chart_type = str(specification.get("chart_type", "horizontal_bar"))
        display_type = {
            "horizontal_bar": "Horizontal Bar",
            "vertical_bar": "Vertical Bar",
            "line": "Line",
            "donut": "Donut",
            "pie": "Donut",
        }.get(chart_type, "Horizontal Bar")
        self.title = str(specification.get("title", "AI Custom HO Chart"))
        self.entity_name = str(specification.get("entity_name", "Items"))
        self.title_var = tk.StringVar(value=self.title)
        self.chart_type_var = tk.StringVar(value=display_type)
        self.metric_var = tk.StringVar(value=metric if metric in numeric else (numeric[0] if numeric else ""))
        self.label_var = tk.StringVar(value=label if label in labels else (labels[0] if labels else ""))
        self.top_var = tk.IntVar(value=max(1, min(100, int(specification.get("top_n", 10)))))
        self._numeric_columns = numeric
        self._label_columns = labels
        self._build()
        self.window.after_idle(self.refresh)

    def _build(self) -> None:
        root = ttk.Frame(self.window, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=4)
        root.rowconfigure(4, weight=2)

        ttk.Label(
            root,
            textvariable=self.title_var,
            font=("Segoe UI", 18, "bold"),
            foreground="#0B2A5B",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            root,
            text="Generated from deterministic HO analytics · controls remain editable",
            foreground="#4A6FAE",
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        controls = ttk.Frame(root)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        settings = (
            ("Chart", self.chart_type_var, self.CHART_TYPES, 16),
            ("Label", self.label_var, self._label_columns, 24),
            ("Metric", self.metric_var, self._numeric_columns, 22),
            ("Top N", self.top_var, [5, 10, 15, 20, 30, 50, 100], 7),
        )
        for label, variable, values, width in settings:
            ttk.Label(controls, text=label).pack(side="left")
            combo = ttk.Combobox(
                controls,
                textvariable=variable,
                values=values,
                state="readonly",
                width=width,
            )
            combo.pack(side="left", padx=(5, 12))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(controls, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(controls, text="Export Data...", command=self._export).pack(side="right")

        chart_box = ttk.LabelFrame(root, text="Visualization")
        chart_box.grid(row=3, column=0, sticky="nsew")
        self.canvas = tk.Canvas(chart_box, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)

        table_box = ttk.LabelFrame(root, text="Selected Data")
        table_box.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(table_box, show="headings", height=7)
        scrollbar = ttk.Scrollbar(table_box, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _current_data(self) -> pd.DataFrame:
        metric = self.metric_var.get()
        frame = self.source.copy()
        if metric in frame.columns:
            frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
            frame = frame.dropna(subset=[metric]).sort_values(metric, ascending=False)
        return frame.head(max(1, int(self.top_var.get())))

    def refresh(self) -> None:
        frame = self._current_data()
        dynamic_title = (
            f"Top {len(frame)} {self.entity_name} by {self.metric_var.get()}"
        )
        self.title_var.set(dynamic_title)
        self.window.title(dynamic_title)
        self.canvas.delete("all")
        self._populate_table(frame)
        label = self.label_var.get()
        metric = self.metric_var.get()
        if frame.empty or label not in frame.columns or metric not in frame.columns:
            self.canvas.create_text(450, 220, text="No chartable data", fill="#5C6B7A")
            return
        values = pd.to_numeric(frame[metric], errors="coerce").fillna(0).tolist()
        labels = [str(value) for value in frame[label].tolist()]
        chart_type = self.chart_type_var.get()
        if chart_type == "Horizontal Bar":
            self._draw_horizontal(labels, values, metric)
        elif chart_type == "Vertical Bar":
            self._draw_vertical(labels, values, metric, connect=False)
        elif chart_type == "Line":
            self._draw_vertical(labels, values, metric, connect=True)
        else:
            self._draw_donut(labels, values, metric)

    def _draw_horizontal(self, labels: list[str], values: list[float], metric: str) -> None:
        width = max(850, self.canvas.winfo_width())
        height = max(360, self.canvas.winfo_height())
        maximum = max([abs(float(value)) for value in values] + [1e-12])
        left, right, top = 230, 100, 22
        row_height = max(22, min(44, (height - 45) / max(1, len(values))))
        for index, (label, value) in enumerate(zip(labels, values)):
            y = top + index * row_height
            shown = label if len(label) <= 32 else label[:29] + "..."
            self.canvas.create_text(left - 8, y + 10, text=shown, anchor="e", fill="#243B53")
            bar_width = (width - left - right) * abs(float(value)) / maximum
            self.canvas.create_rectangle(
                left,
                y,
                left + max(2, bar_width),
                y + 20,
                fill=COLORS[index % len(COLORS)],
                outline="",
            )
            self.canvas.create_text(
                left + max(4, bar_width) + 6,
                y + 10,
                text=FailureDashboard._format_metric(metric, float(value)),
                anchor="w",
                fill="#0B2A5B",
                font=("Segoe UI", 9, "bold"),
            )

    def _draw_vertical(
        self,
        labels: list[str],
        values: list[float],
        metric: str,
        *,
        connect: bool,
    ) -> None:
        width = max(850, self.canvas.winfo_width())
        height = max(360, self.canvas.winfo_height())
        left, right, top, bottom = 70, 35, 30, 90
        maximum = max([abs(float(value)) for value in values] + [1e-12])
        plot_width = width - left - right
        plot_height = height - top - bottom
        slot = plot_width / max(1, len(values))
        points: list[tuple[float, float]] = []
        self.canvas.create_line(left, top, left, top + plot_height, fill="#A8B6C6")
        self.canvas.create_line(left, top + plot_height, width - right, top + plot_height, fill="#A8B6C6")
        for index, (label, value) in enumerate(zip(labels, values)):
            x = left + slot * (index + 0.5)
            y = top + plot_height * (1 - abs(float(value)) / maximum)
            points.append((x, y))
            if not connect:
                half = min(30, slot * 0.32)
                self.canvas.create_rectangle(
                    x - half,
                    y,
                    x + half,
                    top + plot_height,
                    fill=COLORS[index % len(COLORS)],
                    outline="",
                )
            shown = label if len(label) <= 16 else label[:13] + "..."
            self.canvas.create_text(x, top + plot_height + 10, text=shown, anchor="n", angle=25)
            self.canvas.create_text(
                x,
                max(12, y - 5),
                text=FailureDashboard._format_metric(metric, float(value)),
                anchor="s",
                fill="#0B2A5B",
                font=("Segoe UI", 8, "bold"),
            )
        if connect and points:
            flattened = [coordinate for point in points for coordinate in point]
            if len(points) > 1:
                self.canvas.create_line(*flattened, fill="#0B5ED7", width=3, smooth=True)
            for index, (x, y) in enumerate(points):
                self.canvas.create_oval(
                    x - 5,
                    y - 5,
                    x + 5,
                    y + 5,
                    fill=COLORS[index % len(COLORS)],
                    outline="white",
                )

    def _draw_donut(self, labels: list[str], values: list[float], metric: str) -> None:
        total = float(sum(max(0.0, float(value)) for value in values))
        if total <= 0:
            self.canvas.create_text(450, 220, text="Values must be positive", fill="#5C6B7A")
            return
        height = max(360, self.canvas.winfo_height())
        size = min(280, height - 60)
        x0, y0, start = 45, 30, 90.0
        for index, (label, value) in enumerate(zip(labels, values)):
            positive = max(0.0, float(value))
            extent = -360.0 * positive / total
            color = COLORS[index % len(COLORS)]
            self.canvas.create_arc(
                x0, y0, x0 + size, y0 + size, start=start, extent=extent,
                fill=color, outline="white", width=2,
            )
            start += extent
            legend_x, legend_y = x0 + size + 40, 36 + index * 34
            self.canvas.create_rectangle(
                legend_x, legend_y, legend_x + 13, legend_y + 13, fill=color, outline=""
            )
            shown = label if len(label) <= 28 else label[:25] + "..."
            self.canvas.create_text(
                legend_x + 20,
                legend_y + 6,
                text=f"{shown} · {positive / total:.1%}",
                anchor="w",
                fill="#243B53",
            )
        inner = size * 0.5
        offset = (size - inner) / 2
        self.canvas.create_oval(
            x0 + offset, y0 + offset, x0 + offset + inner, y0 + offset + inner,
            fill="white", outline="white",
        )
        self.canvas.create_text(
            x0 + size / 2,
            y0 + size / 2,
            text=FailureDashboard._format_metric(metric, total),
            fill="#0B2A5B",
            font=("Segoe UI", 15, "bold"),
        )

    def _populate_table(self, frame: pd.DataFrame) -> None:
        self.table.delete(*self.table.get_children())
        self.table["columns"] = list(frame.columns)
        for column in frame.columns:
            self.table.heading(column, text=column)
            self.table.column(column, width=145, anchor="w")
        for _, row in frame.iterrows():
            self.table.insert("", "end", values=list(row))

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Chart Data",
            defaultextension=".xlsx",
            initialfile="AI_Custom_Chart_Data.xlsx",
            filetypes=[("Excel Workbook", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not path:
            return
        frame = self._current_data()
        try:
            if path.lower().endswith(".csv"):
                frame.to_csv(path, index=False)
            else:
                export_professional_xlsx({"Chart_Data": frame}, path)
        except Exception as exc:
            messagebox.showerror("Chart Export", str(exc), parent=self.window)


def open_custom_chart(
    parent: Any,
    frame: pd.DataFrame,
    specification: dict[str, Any],
) -> CustomChartWindow:
    return CustomChartWindow(parent, frame, specification)
