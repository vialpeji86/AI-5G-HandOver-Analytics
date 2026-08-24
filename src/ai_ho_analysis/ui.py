from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import sys
from typing import Dict, List, Tuple
import webbrowser

import pandas as pd

from .agent import LocalHOAgent
from .analysis import HOAnalyzer
from .data_loader import SUPPORTED_EXT, load_many
from .exporter import export_professional_xlsx
from .map_analysis import MAP_PROFILES, build_profile_map_html, export_profile_kmz


def _default_output_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path.home() / "Documents" / "AI-5G-HandOver-Analytics" / "outputs"
    return Path(__file__).resolve().parents[2] / "outputs"

class HOApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AI-5G HandOver Analytics — Handover Intelligence")
        self.root.geometry("1380x860")

        self.analyzer = HOAnalyzer()
        self.agent = LocalHOAgent(self.analyzer)
        self.loaded: Dict[str, pd.DataFrame] = {}
        self.file_roles: Dict[str, Tuple[str, int]] = {}
        self.primary_ho_var = tk.StringVar(value="")
        self.primary_map_var = tk.StringVar(value="")
        self.demo_mode = tk.BooleanVar(value=True)
        self.demo_delay_ms = tk.IntVar(value=320)
        self.map_profile_var = tk.StringVar(value="Top 10 Long HO Attempts")

        self._apply_theme()
        self._build_ui()

    def _apply_theme(self) -> None:
        self.root.configure(bg="#F3F6FB")
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#F3F6FB")
        style.configure("TLabel", background="#F3F6FB", foreground="#0B2A5B")
        style.configure("TLabelframe", background="#F3F6FB", foreground="#0B2A5B")
        style.configure("TLabelframe.Label", background="#F3F6FB", foreground="#0B2A5B")
        style.configure("TButton", background="#0B5ED7", foreground="white", padding=6)
        style.map("TButton", background=[("active", "#1B6FE3")])
        style.configure("Treeview.Heading", background="#0B5ED7", foreground="white")
        style.configure("Treeview", background="white", fieldbackground="white", foreground="#1A1A1A")

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=2)
        self.root.columnconfigure(1, weight=3)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=10)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="AI-5G HandOver Analytics", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            top,
            text="Developed by Victor Perez",
            font=("Segoe UI", 9),
            foreground="#4A6FAE",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        btns = ttk.Frame(top)
        btns.grid(row=0, column=2, sticky="e")
        ttk.Button(btns, text="Load Files", command=self._pick_files).pack(side="left", padx=4)
        ttk.Button(btns, text="Manual Coordinates", command=self._open_manual_location_dialog).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Run Analysis", command=lambda: self._chat_send("Run analysis")).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Export XLSX", command=self._export).pack(side="left", padx=4)
        ttk.Checkbutton(btns, text="Demo Flow", variable=self.demo_mode).pack(side="left", padx=(8, 0))

        self.warning_var = tk.StringVar(value="")
        warning_lbl = ttk.Label(
            self.root,
            textvariable=self.warning_var,
            foreground="#B00020",
            font=("Segoe UI", 13, "bold"),
            anchor="center",
            justify="center",
        )
        warning_lbl.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))

        left = ttk.Frame(self.root, padding=(10, 0, 5, 10))
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(9, weight=1)
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="Loaded Files", font=("Segoe UI", 10, "bold")).grid(
            row=2, column=0, sticky="w", pady=(0, 0)
        )
        self.file_tree = ttk.Treeview(
            left, columns=("file", "role", "confidence"), show="headings", height=6
        )
        self.file_tree.grid(row=3, column=0, sticky="nsew", pady=(4, 0))
        self.file_tree.heading("file", text="File")
        self.file_tree.heading("role", text="Detected Role")
        self.file_tree.heading("confidence", text="Confidence")
        self.file_tree.column("file", width=270, anchor="w")
        self.file_tree.column("role", width=110, anchor="center")
        self.file_tree.column("confidence", width=90, anchor="center")
        self.file_tree.tag_configure("conf_high", background="#E8F5E9")
        self.file_tree.tag_configure("conf_mid", background="#FFF8E1")
        self.file_tree.tag_configure("conf_low", background="#FDECEA")

        selector_frame = ttk.Frame(left)
        selector_frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        selector_frame.columnconfigure(1, weight=1)
        selector_frame.columnconfigure(3, weight=1)
        ttk.Label(selector_frame, text="Primary HO File").grid(row=0, column=0, sticky="w")
        self.primary_ho_combo = ttk.Combobox(
            selector_frame, textvariable=self.primary_ho_var, state="readonly"
        )
        self.primary_ho_combo.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        ttk.Label(selector_frame, text="Primary Map File").grid(row=0, column=2, sticky="w")
        self.primary_map_combo = ttk.Combobox(
            selector_frame, textvariable=self.primary_map_var, state="readonly"
        )
        self.primary_map_combo.grid(row=0, column=3, sticky="ew", padx=(6, 10))
        ttk.Button(selector_frame, text="Apply Selection", command=self._apply_primary_selection).grid(
            row=0, column=4, sticky="e"
        )

        quick_actions = ttk.Frame(left)
        quick_actions.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            quick_actions, text="Top Failures", command=lambda: self._chat_send("Show top failures")
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            quick_actions, text="Over 10 km", command=lambda: self._chat_send("Show relations over 10 km")
        ).pack(side="left", padx=5)
        ttk.Button(
            quick_actions, text="Executive Summary", command=lambda: self._chat_send("Show executive summary")
        ).pack(side="left", padx=5)
        ttk.Button(
            quick_actions, text="Distance Bands", command=lambda: self._chat_send("Show distance bands")
        ).pack(side="left", padx=5)

        map_frame = ttk.LabelFrame(left, text="Map Analysis (OSM)")
        map_frame.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        map_frame.columnconfigure(1, weight=1)
        ttk.Label(map_frame, text="Profile").grid(row=0, column=0, sticky="w", padx=(6, 4), pady=6)
        self.map_profile_combo = ttk.Combobox(
            map_frame,
            textvariable=self.map_profile_var,
            values=list(MAP_PROFILES.keys()),
            state="readonly",
        )
        self.map_profile_combo.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=6)
        ttk.Button(map_frame, text="Generate Map", command=self._generate_map).grid(
            row=0, column=2, padx=(0, 6), pady=6
        )
        ttk.Button(map_frame, text="Export KMZ", command=self._export_kmz_profile).grid(
            row=0, column=3, padx=(0, 6), pady=6
        )

        chat_frame = ttk.Frame(left)
        chat_frame.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        chat_frame.columnconfigure(0, weight=1)

        ttk.Label(
            chat_frame,
            text="Ask the AI assistant (type here):",
            font=("Segoe UI", 10, "bold"),
            foreground="#0B5ED7",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.chat_entry = ttk.Entry(chat_frame)
        self.chat_entry.grid(row=1, column=0, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self._chat_send())
        ttk.Button(chat_frame, text="Send", command=self._chat_send).grid(row=1, column=1, padx=(6, 0))
        self._set_chat_placeholder()
        self.chat_entry.bind("<FocusIn>", self._on_chat_focus_in)
        self.chat_entry.bind("<FocusOut>", self._on_chat_focus_out)

        decision_box = ttk.LabelFrame(left, text="AI Decision Live")
        decision_box.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        decision_box.columnconfigure(0, weight=1)

        self.decision_canvas = tk.Canvas(decision_box, height=120, bg="#F7FAFF", highlightthickness=0)
        self.decision_canvas.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))

        ttk.Label(decision_box, text="Decision Trace", font=("Segoe UI", 9, "bold")).grid(
            row=1, column=0, sticky="w", padx=6
        )
        self.decision_trace = tk.Text(decision_box, height=6, wrap="word")
        self.decision_trace.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 6))
        self._draw_decision_diagram(
            [
                ("Input", "idle"),
                ("Intent", "idle"),
                ("Data", "idle"),
                ("Engine", "idle"),
                ("Distance", "idle"),
                ("Output", "idle"),
            ]
        )

        self.chat_log = tk.Text(left, height=12, wrap="word")
        self.chat_log.grid(row=9, column=0, sticky="nsew", pady=(8, 0))
        self._append_chat(
            "assistant",
            "Hello. I am your local AI HO assistant. Load files and ask: 'Run analysis', 'Show top failures', or 'Show relations over 10 km'.",
        )

        right = ttk.Frame(self.root, padding=(5, 0, 10, 10))
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Results", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(right, text="Back to Summary", command=self._show_summary).grid(
            row=0, column=0, sticky="e"
        )

        self.tree = ttk.Treeview(right, show="headings")
        self.tree.grid(row=1, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(right, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll.grid(row=2, column=0, sticky="ew")

        # Drag-and-drop intentionally removed by design. Use "Load Files" button only.

    def _append_chat(self, role: str, text: str) -> None:
        self.chat_log.insert("end", f"{role.title()}: {text}\n\n")
        self.chat_log.see("end")

    def _set_chat_placeholder(self) -> None:
        self.chat_entry.delete(0, "end")
        self.chat_entry.insert(
            0, "Type a request... e.g. 'Run analysis' or 'top 20 where distance > 10 km'"
        )
        self.chat_entry.configure(foreground="#5C6B7A")

    def _on_chat_focus_in(self, _event) -> None:
        cur = self.chat_entry.get().strip()
        if cur.startswith("Type a request..."):
            self.chat_entry.delete(0, "end")
            self.chat_entry.configure(foreground="#0B2A5B")

    def _on_chat_focus_out(self, _event) -> None:
        if not self.chat_entry.get().strip():
            self._set_chat_placeholder()

    def _append_trace(self, text: str) -> None:
        self.decision_trace.insert("end", f"{text}\n")
        self.decision_trace.see("end")

    def _run_live_flow(self, states: list[tuple[str, str]], feedback: list[str]) -> None:
        labels = ["Input", "Intent", "Data", "Engine", "Distance", "Output"]
        current = [(x, "idle") for x in labels]
        self._draw_decision_diagram(current)
        self.root.update_idletasks()
        delay = max(120, int(self.demo_delay_ms.get()))
        for i, (label, final_state) in enumerate(states):
            if self.demo_mode.get():
                self.root.after(delay)
                self.root.update()
            # mark current step as running
            for j, (name, st) in enumerate(current):
                if name == label:
                    current[j] = (name, "run")
                    break
            self._draw_decision_diagram(current)
            if i < len(feedback):
                self._append_trace(feedback[i])
            self.root.update_idletasks()
            if self.demo_mode.get():
                self.root.after(delay)
                self.root.update()
            # finalize step
            for j, (name, st) in enumerate(current):
                if name == label:
                    current[j] = (name, final_state)
                    break
            self._draw_decision_diagram(current)
            self.root.update_idletasks()

    def _draw_decision_diagram(self, steps: list[tuple[str, str]]) -> None:
        self.decision_canvas.delete("all")
        x = 8
        y = 22
        w = 88
        h = 34
        gap = 6
        color_map = {
            "idle": ("#E3EAF3", "#5C6B7A"),
            "run": ("#FFE9A8", "#7A5B00"),
            "ok": ("#D7F5DD", "#1F6B35"),
            "warn": ("#FFE1E1", "#9E1B1B"),
        }
        for i, (label, state) in enumerate(steps):
            fill, text_c = color_map.get(state, color_map["idle"])
            self.decision_canvas.create_rectangle(x, y, x + w, y + h, fill=fill, outline="#B7C4D1", width=1)
            self.decision_canvas.create_text(x + w / 2, y + h / 2, text=label, fill=text_c, font=("Segoe UI", 8, "bold"))
            if i < len(steps) - 1:
                self.decision_canvas.create_line(x + w, y + h / 2, x + w + gap, y + h / 2, fill="#8BA1B8", width=2, arrow=tk.LAST)
            x += w + gap

    def _on_drop(self, event) -> None:
        raw = event.data
        parts = self.root.tk.splitlist(raw)
        paths = [str(Path(p)) for p in parts]
        self._load_paths(paths)

    def _pick_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select HO/Map files",
            filetypes=[("Data files", "*.csv *.txt *.xls *.xlsx")],
        )
        if files:
            self._load_paths(list(files))

    def _load_paths(self, paths: List[str]) -> None:
        loaded = load_many(paths)
        if not loaded:
            messagebox.showwarning("No files", "No supported files were found.")
            return

        self.loaded.update(loaded)
        self._refresh_file_roles()

        self._assign_dataframes()
        self._append_chat("assistant", f"Loaded {len(loaded)} file(s). Ready for analysis.")

    def _detect_role(self, df: pd.DataFrame) -> Tuple[str, int]:
        cols = set(df.columns)
        ho_hits = len({"DU", "SECTOR", "TGTDU", "TGTSECTOR", "CARRIER", "TGTCARRIER"} & cols)
        map_hits_legacy = len({"gnbduid", "sectorid", "carrierid", "Lat", "Lon"} & cols)
        map_hits_du = len({"DU", "LAT", "LON"} & cols)
        map_hits = max(map_hits_legacy, map_hits_du)
        if ho_hits >= 4 and ho_hits >= map_hits:
            conf = min(99, 60 + ho_hits * 6)
            return "HO Dataset", conf
        if map_hits_du == 3:
            return "Map Dataset", 99
        if map_hits_legacy >= 4 or map_hits_du >= 3:
            conf = min(99, 60 + map_hits * 8)
            return "Map Dataset", conf
        conf = min(70, 35 + max(ho_hits, map_hits) * 8)
        return "Unknown", conf

    def _confidence_tag(self, confidence: int) -> str:
        if confidence >= 85:
            return "conf_high"
        if confidence >= 65:
            return "conf_mid"
        return "conf_low"

    def _refresh_file_roles(self) -> None:
        self.file_tree.delete(*self.file_tree.get_children())
        self.file_roles.clear()
        ho_candidates: List[str] = []
        map_candidates: List[str] = []
        for name in sorted(self.loaded.keys()):
            role, confidence = self._detect_role(self.loaded[name])
            self.file_roles[name] = (role, confidence)
            self.file_tree.insert(
                "", "end", values=(name, role, f"{confidence}%"), tags=(self._confidence_tag(confidence),)
            )
            if role == "HO Dataset":
                ho_candidates.append(name)
            if role == "Map Dataset":
                map_candidates.append(name)

        self.primary_ho_combo["values"] = ho_candidates
        self.primary_map_combo["values"] = map_candidates
        if ho_candidates and self.primary_ho_var.get() not in ho_candidates:
            self.primary_ho_var.set(ho_candidates[0])
        if map_candidates and self.primary_map_var.get() not in map_candidates:
            self.primary_map_var.set(map_candidates[0])

    def _assign_dataframes(self) -> None:
        # Priority 1: explicit manual selection
        ho_name = self.primary_ho_var.get().strip()
        map_name = self.primary_map_var.get().strip()
        if ho_name in self.loaded:
            df = self.loaded[ho_name]
            cols = set(df.columns)
            if {"DU", "SECTOR", "TGTDU", "TGTSECTOR"}.issubset(cols):
                self.analyzer.set_ho_data(df)
                self._append_chat("assistant", f"Assigned HO dataset (manual): {ho_name}")
        if map_name in self.loaded:
            df = self.loaded[map_name]
            cols = set(df.columns)
            if {"gnbduid", "sectorid", "carrierid", "Lat", "Lon"}.issubset(cols) or {"DU", "LAT", "LON"}.issubset(cols):
                self.analyzer.set_map_data(df)
                self._append_chat("assistant", f"Assigned coordinates dataset (manual): {map_name}")

        # Priority 2: fallback auto-assignment
        for name, df in self.loaded.items():
            role, _ = self._detect_role(df)
            cols = set(df.columns)
            if not ho_name and role == "HO Dataset" and {"DU", "SECTOR", "TGTDU", "TGTSECTOR"}.issubset(cols):
                self.analyzer.set_ho_data(df)
                self._append_chat("assistant", f"Assigned HO dataset: {name}")
                ho_name = name
            if not map_name and role == "Map Dataset" and {"gnbduid", "sectorid", "carrierid", "Lat", "Lon"}.issubset(cols):
                self.analyzer.set_map_data(df)
                self._append_chat("assistant", f"Assigned coordinates dataset: {name}")
                map_name = name
            if (
                not map_name
                and role == "Map Dataset"
                and {"DU", "LAT", "LON"}.issubset(cols)
            ):
                self.analyzer.set_map_data(df)
                self._append_chat("assistant", f"Assigned coordinates dataset: {name}")
                map_name = name

    def _apply_primary_selection(self) -> None:
        if not self.loaded:
            self._append_chat("assistant", "No files loaded yet.")
            return
        self._assign_dataframes()
        self._append_chat("assistant", "Primary file selection applied.")

    def _show_table(self, df: pd.DataFrame) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(df.columns)

        for c in df.columns:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=140, anchor="w")

        for _, row in df.head(500).iterrows():
            values = []
            for v in row.tolist():
                if isinstance(v, float):
                    values.append(f"{v:.6g}")
                else:
                    values.append(v)
            self.tree.insert("", "end", values=values)

    def _show_table_popup(self, df: pd.DataFrame, title: str) -> None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("1280x760")
        win.transient(self.root)

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text=title, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        btns = ttk.Frame(frame)
        btns.grid(row=0, column=1, sticky="e")

        def _export_popup_df() -> None:
            path = filedialog.asksaveasfilename(
                title="Export Detailed View",
                defaultextension=".xlsx",
                initialfile="Detailed_Result_View.xlsx",
                filetypes=[("Excel Workbook", "*.xlsx"), ("CSV", "*.csv")],
            )
            if not path:
                return
            try:
                if path.lower().endswith(".csv"):
                    df.to_csv(path, index=False)
                else:
                    with pd.ExcelWriter(path, engine="openpyxl") as wr:
                        df.to_excel(wr, sheet_name="Detailed_View", index=False)
                self._append_chat("assistant", f"Detailed table exported: {path}")
            except Exception as exc:
                messagebox.showerror("Export", f"Could not export detailed table:\n{exc}")

        ttk.Button(btns, text="Export to Excel", command=_export_popup_df).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="left")

        tree = ttk.Treeview(frame, show="headings")
        tree.grid(row=1, column=0, columnspan=2, sticky="nsew")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.grid(row=1, column=2, sticky="ns")
        xscroll.grid(row=2, column=0, columnspan=2, sticky="ew")

        tree["columns"] = list(df.columns)
        for c in df.columns:
            tree.heading(c, text=c)
            tree.column(c, width=140, anchor="w")

        for _, row in df.head(2000).iterrows():
            values = []
            for v in row.tolist():
                if isinstance(v, float):
                    values.append(f"{v:.6g}")
                else:
                    values.append(v)
            tree.insert("", "end", values=values)

    def _show_summary(self) -> None:
        if self.analyzer.last_result is not None:
            self._show_table(self.analyzer.last_result.summary)
            self._append_chat("assistant", "Returned to the executive summary view.")
        else:
            self._append_chat("assistant", "No analysis available yet. Run analysis first.")

    def _generate_map(self) -> None:
        if self.analyzer.last_result is None:
            self._append_chat("assistant", "Run analysis first, then generate a map profile.")
            return
        profile = self.map_profile_var.get().strip()
        try:
            out_dir = _default_output_dir()
            out = build_profile_map_html(
                self.analyzer.last_result.relation_detail,
                profile_name=profile,
                out_html=out_dir / f"{profile.replace(' ', '_')}.html",
            )
            webbrowser.open(out.resolve().as_uri())
            self._append_chat("assistant", f"Map generated successfully: {out}")
        except Exception as exc:
            messagebox.showerror("Map Analysis", str(exc))

    def _export_kmz_profile(self) -> None:
        if self.analyzer.last_result is None:
            self._append_chat("assistant", "Run analysis first, then export a KMZ profile.")
            return
        profile = self.map_profile_var.get().strip()
        path = filedialog.asksaveasfilename(
            title="Export KMZ",
            defaultextension=".kmz",
            initialfile=f"{profile.replace(' ', '_')}.kmz",
            filetypes=[("Google Earth KMZ", "*.kmz")],
        )
        if not path:
            return
        try:
            out = export_profile_kmz(self.analyzer.last_result.relation_detail, profile, path)
            self._append_chat("assistant", f"KMZ exported successfully: {out}")
        except Exception as exc:
            messagebox.showerror("KMZ Export", str(exc))

    def _open_manual_location_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Manual Coordinates Input")
        win.geometry("420x220")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="DU (11 digits: GNB+DU)").grid(row=0, column=0, sticky="w", pady=4)
        du_entry = ttk.Entry(frame)
        du_entry.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Latitude").grid(row=1, column=0, sticky="w", pady=4)
        lat_entry = ttk.Entry(frame)
        lat_entry.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Longitude").grid(row=2, column=0, sticky="w", pady=4)
        lon_entry = ttk.Entry(frame)
        lon_entry.grid(row=2, column=1, sticky="ew", pady=4)

        status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=status_var, foreground="#2E7D32").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 4)
        )

        def _save() -> None:
            raw_du = du_entry.get().strip()
            raw_lat = lat_entry.get().strip()
            raw_lon = lon_entry.get().strip()
            du_digits = "".join(ch for ch in raw_du if ch.isdigit())
            if len(du_digits) != 11:
                messagebox.showerror("Manual Coordinates", "DU must be 11 digits (GNB+DU).")
                return
            try:
                du_full = int(du_digits)
                lat = float(raw_lat)
                lon = float(raw_lon)
            except Exception:
                messagebox.showerror("Manual Coordinates", "Latitude/Longitude must be numeric.")
                return
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                messagebox.showerror("Manual Coordinates", "Latitude/Longitude out of valid range.")
                return

            self.analyzer.upsert_manual_location(du_full, lat, lon)
            map_name = self.primary_map_var.get().strip()
            if map_name in self.loaded:
                self.loaded[map_name] = self.analyzer.map_df.copy() if self.analyzer.map_df is not None else self.loaded[map_name]
            else:
                self.loaded["Manual_DU_Locations.csv"] = (
                    self.analyzer.map_df.copy() if self.analyzer.map_df is not None else pd.DataFrame()
                )
                self.primary_map_var.set("Manual_DU_Locations.csv")

            self._refresh_file_roles()
            self._assign_dataframes()
            status_var.set(f"Saved DU {du_full} successfully.")
            self._append_chat("assistant", f"Manual location saved for DU {du_full}. Re-run analysis.")

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btn_row, text="Save", command=_save).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Close", command=win.destroy).pack(side="left", padx=4)

    def _chat_send(self, text: str | None = None) -> None:
        raw = self.chat_entry.get().strip() if text is None else text
        if text is None and raw.startswith("Type a request..."):
            raw = ""
        msg = raw.strip()
        if not msg:
            return
        if text is None:
            self.chat_entry.delete(0, "end")
            self.chat_entry.configure(foreground="#0B2A5B")

        self._append_chat("user", msg)
        self._append_trace(f"User input: {msg}")
        self._run_live_flow(
            states=[("Input", "ok"), ("Intent", "ok")],
            feedback=[
                "Phase 1/6: Input captured and normalized.",
                "Phase 2/6: Intent classification in progress.",
            ],
        )
        try:
            reply = self.agent.handle(msg)
            self._append_chat("assistant", reply.text)
            action = reply.action or "generic"
            self._append_trace(f"Intent detected: {action}")
            data_ok = self.analyzer.ho_df is not None and self.analyzer.map_df is not None
            self._append_trace(f"Data check: {'OK' if data_ok else 'Missing dataset(s)'}")
            warn_state = "ok"
            feedback_extra = []
            if self.analyzer.last_result is not None:
                s = self.analyzer.last_result.summary
                try:
                    miss_tgt = int(pd.to_numeric(s.loc[s["KPI"] == "Relations Missing Target Location", "Value"], errors="coerce").fillna(0).iloc[0])
                except Exception:
                    miss_tgt = 0
                self._append_trace(f"Distance validation: {miss_tgt} target relation(s) missing coordinates")
                if miss_tgt > 0:
                    warn_state = "warn"
                try:
                    miss_src = int(pd.to_numeric(s.loc[s["KPI"] == "Relations Missing Source Location", "Value"], errors="coerce").fillna(0).iloc[0])
                except Exception:
                    miss_src = 0
                self._append_trace(f"Source validation: {miss_src} source relation(s) missing coordinates")
                mapped = int(pd.to_numeric(s.loc[s["KPI"] == "Mapped Relations", "Value"], errors="coerce").fillna(0).iloc[0])
                total = int(pd.to_numeric(s.loc[s["KPI"] == "Total HO Relations", "Value"], errors="coerce").fillna(0).iloc[0])
                self._append_trace(f"Coverage: {mapped}/{total} relations mapped with distance")
                feedback_extra.append(f"Distance QA: mapped {mapped}/{total}; missing targets: {miss_tgt}.")
            if reply.action == "analysis" and self.analyzer.last_result is not None:
                s = self.analyzer.last_result.summary
                try:
                    miss_src = int(
                        pd.to_numeric(
                            s.loc[s["KPI"] == "Relations Missing Source Location", "Value"], errors="coerce"
                        ).fillna(0).iloc[0]
                    )
                except Exception:
                    miss_src = 0
                if miss_src > 0:
                    self.warning_var.set(
                        f"WARNING: {miss_src} RELATION(S) MISSING SOURCE COORDINATES. DISTANCE KPIs MAY BE INCOMPLETE."
                    )
                else:
                    self.warning_var.set("")
            self._run_live_flow(
                states=[
                    ("Data", "ok" if data_ok else "warn"),
                    ("Engine", "ok" if reply.action == "analysis" else "ok"),
                    ("Distance", warn_state),
                    ("Output", "ok"),
                ],
                feedback=[
                    "Phase 3/6: Data integrity checks completed.",
                    "Phase 4/6: HO analysis engine executed.",
                    "Phase 5/6: Distance KPI validation finalized.",
                    "Phase 6/6: Professional output rendered.",
                ] + feedback_extra[:0],
            )
            self._append_trace("Response generated and rendered.")
            if reply.table is not None and not reply.table.empty:
                if reply.action in {"long_over_10km", "custom_distance"} or len(reply.table.columns) > 18:
                    self._show_table_popup(reply.table, "Detailed Result View")
                else:
                    self._show_table(reply.table)
        except Exception as exc:
            self._draw_decision_diagram(
                [
                    ("Input", "ok"),
                    ("Intent", "warn"),
                    ("Data", "warn"),
                    ("Engine", "warn"),
                    ("Distance", "warn"),
                    ("Output", "warn"),
                ]
            )
            self._append_trace(f"Error: {exc}")
            self._append_chat("assistant", f"Error: {exc}")

    def _export(self) -> None:
        try:
            payload = self.analyzer.export_payload()
        except Exception as exc:
            messagebox.showerror("Export", str(exc))
            return

        path = filedialog.asksaveasfilename(
            title="Export Report",
            defaultextension=".xlsx",
            initialfile="AI_5G_HandOver_Analytics_Report.xlsx",
            filetypes=[("Excel Workbook", "*.xlsx")],
        )
        if not path:
            return

        out = export_professional_xlsx(payload, path)
        self._append_chat("assistant", f"Professional report exported: {out}")


def run_app() -> None:
    root = tk.Tk()
    app = HOApp(root)
    root.mainloop()
