from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping, Optional

import pandas as pd

from .analysis import HOAnalyzer
from .configuration import OllamaConfig
from .kpi_knowledge import KPI_DEFS, failure_recommended_checks, find_kpi_matches
from .models import AnalysisResult
from .xnap_knowledge import (
    MAPPING_CAVEAT,
    XNAP_REFERENCE,
    XNAP_URL,
    build_standards_diagnostics,
    find_xnap_knowledge,
    kpi_protocol_lens,
    xnap_answer_table,
)


@dataclass
class AgentReply:
    text: str
    table: Optional[pd.DataFrame] = None
    action: Optional[str] = None
    backend: str = "rules"
    visualization: Optional[dict[str, Any]] = None
    visualization_data: Optional[pd.DataFrame] = None


class LocalHOAgent:
    """Local Ollama agent whose tools preserve deterministic HO/XnAP logic."""

    DIRECT_DATA_ACTIONS = frozenset(
        {
            "analysis",
            "summary",
            "top_failures",
            "distance_bands",
            "long_over_10km",
            "long_ho_table",
            "missing_targets",
            "filtered_query",
            "failure_types",
            "failure_detail",
            "source_offenders",
            "target_offenders",
            "create_chart",
            "create_map",
        }
    )

    def __init__(
        self,
        analyzer: HOAnalyzer,
        ollama_config: Optional[OllamaConfig] = None,
        ollama_client: Any = None,
    ) -> None:
        self.analyzer = analyzer
        self.ollama_config = ollama_config or OllamaConfig.from_env()
        self._ollama_client = ollama_client
        self.last_ollama_error: Optional[str] = None
        self._conversation: list[dict[str, str]] = []

    def _ensure_result(self) -> AnalysisResult:
        if not self.analyzer.last_result:
            raise ValueError("Please run analysis first.")
        return self.analyzer.last_result

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9\s><.=]", " ", text.lower()).strip()

    def _has_fuzzy(self, query: str, phrase: str, threshold: float = 0.78) -> bool:
        q = self._normalize(query)
        p = self._normalize(phrase)
        if p in q:
            return True
        # Avoid over-matching tiny tokens like "band" vs "and".
        if len(p.replace(" ", "")) <= 4:
            return p in q.split()
        q_tokens = q.split()
        p_tokens = p.split()
        if not p_tokens or not q_tokens:
            return False
        # Sliding token window to handle typos like "relqtion with more fails"
        w = len(p_tokens)
        for i in range(0, max(1, len(q_tokens) - w + 1)):
            chunk = " ".join(q_tokens[i : i + w])
            if SequenceMatcher(None, chunk, p).ratio() >= max(0.84, threshold):
                return True
        return SequenceMatcher(None, q, p).ratio() >= max(0.84, threshold)

    def _intent_score(self, query: str, patterns: list[str]) -> int:
        score = 0
        for pat in patterns:
            if self._has_fuzzy(query, pat):
                score += 1
        return score

    def _extract_top_n(self, qn: str, default: int = 50) -> int:
        m = (
            re.search(r"\btop\s+(\d+)\b", qn)
            or re.search(r"\b(\d+)\s+top\b", qn)
            or re.search(r"\bfirst\s+(\d+)\b", qn)
        )
        if m:
            return max(1, min(2000, int(m.group(1))))
        return default

    def _extract_numeric_filters(self, qn: str) -> dict[str, tuple[str, float]]:
        out: dict[str, tuple[str, float]] = {}
        patterns = [
            ("Distance_km", r"(distance|dist|km)\s*(>=|<=|>|<|=)\s*(\d+(\.\d+)?)"),
            ("Failures", r"(failures|fails|fail)\s*(>=|<=|>|<|=)\s*(\d+(\.\d+)?)"),
            ("Attempts", r"(attempts|att)\s*(>=|<=|>|<|=)\s*(\d+(\.\d+)?)"),
            ("Success", r"(success|succ)\s*(>=|<=|>|<|=)\s*(\d+(\.\d+)?)"),
            ("Fail_Rate", r"(fail rate|failure rate)\s*(>=|<=|>|<|=)\s*(\d+(\.\d+)?)"),
        ]
        for col, pat in patterns:
            m = re.search(pat, qn)
            if m:
                out[col] = (m.group(2), float(m.group(3)))

        # Natural-language shortcuts
        km = re.search(r"(over|above|more than)\s*(\d+(\.\d+)?)\s*km", qn)
        if km:
            out["Distance_km"] = (">", float(km.group(2)))
        km2 = re.search(r"(under|below|less than)\s*(\d+(\.\d+)?)\s*km", qn)
        if km2:
            out["Distance_km"] = ("<", float(km2.group(2)))
        for column, names in (
            ("Failures", "failures|fails|fail"),
            ("Attempts", "attempts|attempt"),
        ):
            above = re.search(
                rf"(?:{names})\s*(?:over|above|more than)\s*"
                rf"(\d+(?:\.\d+)?)(?![\d.]|\s*km)",
                qn,
            )
            below = re.search(
                rf"(?:{names})\s*(?:under|below|less than)\s*"
                rf"(\d+(?:\.\d+)?)(?![\d.]|\s*km)",
                qn,
            )
            if above:
                out[column] = (">", float(above.group(1)))
            elif below:
                out[column] = ("<", float(below.group(1)))
        return out

    def _extract_text_filters(self, qn: str) -> dict[str, str]:
        out: dict[str, str] = {}
        simple = [
            ("source", "Source_Site"),
            ("target", "Target_Site"),
        ]
        for key, col in simple:
            m = re.search(rf"{key}\s*(=|is|contains)?\s*([a-z0-9_\\-]+)", qn)
            if m:
                out[col] = m.group(2)

        carriers = re.search(r"(source carrier|target carrier|carrier)\s*(=|is)?\s*(\d+)", qn)
        if carriers:
            c = int(carriers.group(3))
            if "source" in carriers.group(1):
                out["Source_Carrier"] = str(c)
            elif "target" in carriers.group(1):
                out["Target_Carrier"] = str(c)
            else:
                out["CarrierAny"] = str(c)
        return out

    def _apply_op(self, s: pd.Series, op: str, val: float) -> pd.Series:
        if op == ">":
            return s > val
        if op == "<":
            return s < val
        if op == ">=":
            return s >= val
        if op == "<=":
            return s <= val
        return s == val

    def _extract_sort(self, qn: str) -> tuple[str, bool]:
        # asc bool: True means ascending
        if "sort by distance" in qn or "order by distance" in qn:
            return "Distance_km", ("asc" in qn or "lowest" in qn or "nearest" in qn)
        if "sort by attempts" in qn or "order by attempts" in qn or "most attempts" in qn:
            return "Attempts", False
        if "sort by fail rate" in qn or "order by fail rate" in qn:
            return "Fail_Rate", False
        if "sort by failures" in qn or "order by failures" in qn or "most failures" in qn:
            return "Failures", False
        # Default intent-oriented sort
        if "distance" in qn or "km" in qn:
            return "Distance_km", False
        if "attempt" in qn:
            return "Attempts", False
        return "Failures", False

    def _is_advanced_filter_request(self, qn: str) -> bool:
        keys = [
            "where",
            "filter",
            "source",
            "target",
            "carrier",
            "sector",
            "distance",
            "km",
            "attempt",
            "fail",
            "sort",
            "order by",
            "top ",
            ">",
            "<",
            "=",
        ]
        return any(k in qn for k in keys)

    def _kpi_catalog_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "KPI": k.name,
                    "Domain": k.domain,
                    "Stage": k.stage,
                    "Category": k.category,
                    "Formula": k.formula,
                    "Meaning": k.meaning,
                    "Recommended Checks": failure_recommended_checks(k.name),
                    "XnAP Lens": kpi_protocol_lens(k.stage)[0],
                    "XnAP Reference": kpi_protocol_lens(k.stage)[1],
                }
                for k in KPI_DEFS
            ]
        )

    def _kpi_logic_answer(self, query_raw: str, qn: str) -> Optional[AgentReply]:
        explain_triggers = [
            "what is",
            "what does",
            "explain",
            "meaning",
            "definition",
            "logic",
            "formula",
            "kpi",
            "what should i check",
            "recommend",
            "suggest",
            "root cause",
        ]
        if not any(t in qn for t in explain_triggers):
            return None

        matches = find_kpi_matches(query_raw)
        if matches:
            table = pd.DataFrame(
                [
                    {
                        "KPI": k.name,
                        "Domain": k.domain,
                        "Stage": k.stage,
                        "Category": k.category,
                        "Formula": k.formula,
                        "Meaning": k.meaning,
                        "Recommended Checks": failure_recommended_checks(k.name),
                        "XnAP Lens": kpi_protocol_lens(k.stage)[0],
                        "XnAP Reference": kpi_protocol_lens(k.stage)[1],
                    }
                    for k in matches
                ]
            )
            return AgentReply(
                text="KPI logic reference found. Here is the definition and formula mapping:",
                table=table,
                action="kpi_explain",
            )

        if "all kpi" in qn or "kpi catalog" in qn or "list kpi" in qn:
            return AgentReply(
                text=f"KPI catalog loaded ({len(KPI_DEFS)} definitions).",
                table=self._kpi_catalog_table(),
                action="kpi_catalog",
            )
        return None

    def _xnap_knowledge_answer(self, query_raw: str, qn: str) -> Optional[AgentReply]:
        triggers = (
            "xnap", "38 423", "38.423", "etsi", "handover preparation",
            "txnreloc", "handover cancel", "handover success", "ue context release",
            "failure indication", "handover report", "too early", "wrong cell",
            "ping pong", "ping-pong", "no radio resources", "target not allowed",
            "partial handover", "transport resource", "protocol error", "cause ie",
            "mobility settings",
        )
        if not any(trigger in qn for trigger in triggers):
            return None
        concepts, causes = find_xnap_knowledge(query_raw)
        table = xnap_answer_table(query_raw)
        scope = "matching standards guidance" if concepts or causes else "the XnAP mobility catalog"
        return AgentReply(
            text=(
                f"Standards-aware result from {XNAP_REFERENCE}: showing {scope}. "
                f"{MAPPING_CAVEAT} Official reference: {XNAP_URL}"
            ),
            table=table,
            action="xnap_knowledge",
        )

    def _standards_diagnostic_answer(self, qn: str) -> Optional[AgentReply]:
        triggers = (
            "standards diagnosis", "xnap diagnosis", "smart diagnosis",
            "root cause analysis", "diagnose failures", "why are handovers failing",
            "why ho fail", "recommend actions", "recommended checks",
        )
        if not any(trigger in qn for trigger in triggers):
            return None
        result = self._ensure_result()
        table = build_standards_diagnostics(self.analyzer.ho_df, result)
        return AgentReply(
            text=(
                "Standards-aware diagnostic generated. It separates preparation, execution, "
                "transport, protocol, mobility-robustness, and data-quality evidence. "
                f"{MAPPING_CAVEAT}"
            ),
            table=table,
            action="standards_diagnosis",
        )

    def _run_advanced_query(self, qn: str) -> AgentReply:
        result = self._ensure_result()
        df = result.relation_detail.copy()

        text_filters = self._extract_text_filters(qn)
        num_filters = self._extract_numeric_filters(qn)
        top_n = self._extract_top_n(qn, default=50)
        sort_col, asc = self._extract_sort(qn)

        # source/target site contains
        for col in ["Source_Site", "Target_Site"]:
            if col in text_filters and col in df.columns:
                term = str(text_filters[col]).lower()
                df = df[df[col].astype(str).str.lower().str.contains(term, na=False)]

        # carrier
        if "Source_Carrier" in text_filters and "Source_Carrier" in df.columns:
            df = df[df["Source_Carrier"].astype(str) == text_filters["Source_Carrier"]]
        if "Target_Carrier" in text_filters and "Target_Carrier" in df.columns:
            df = df[df["Target_Carrier"].astype(str) == text_filters["Target_Carrier"]]
        if "CarrierAny" in text_filters:
            c = text_filters["CarrierAny"]
            m1 = df["Source_Carrier"].astype(str) == c if "Source_Carrier" in df.columns else False
            m2 = df["Target_Carrier"].astype(str) == c if "Target_Carrier" in df.columns else False
            df = df[m1 | m2]

        # sector filters
        sm = re.search(r"source sector\s*(=|is)?\s*(\d+)", qn)
        tm = re.search(r"target sector\s*(=|is)?\s*(\d+)", qn)
        if sm and "Source_Sector" in df.columns:
            df = df[df["Source_Sector"] == int(sm.group(2))]
        if tm and "Target_Sector" in df.columns:
            df = df[df["Target_Sector"] == int(tm.group(2))]

        # numeric filters
        for col, (op, val) in num_filters.items():
            if col in df.columns:
                series = pd.to_numeric(df[col], errors="coerce")
                if col == "Fail_Rate" and val > 1:
                    # User may type 5 meaning 5%
                    val = val / 100.0
                df = df[self._apply_op(series, op, val)]

        if sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=asc, na_position="last")

        shown = df.head(top_n)
        if shown.empty:
            return AgentReply(
                text="No rows match your filters. Try relaxing conditions or running 'Show executive summary'.",
                table=shown,
                action="filtered_query",
            )
        return AgentReply(
            text=f"Applied dynamic filters successfully. Matching rows: {len(df)}. Showing top {len(shown)}.",
            table=shown,
            action="filtered_query",
        )

    def _analysis_view(
        self,
        view: str,
        limit: int = 50,
        source: str = "",
        target: str = "",
        failure_type: str = "",
    ) -> AgentReply:
        result = self._ensure_result()
        limit = max(1, min(2000, int(limit)))
        views: dict[str, tuple[str, pd.DataFrame, str]] = {
            "summary": ("Executive KPI summary:", result.summary, "summary"),
            "top_failures": (
                "Top HO relations by failure count (highest to lowest):",
                result.top_failures,
                "top_failures",
            ),
            "distance_bands": (
                "HO distribution by distance band:",
                result.distance_bands,
                "distance_bands",
            ),
            "long_relations": (
                "Long-distance HO relations prioritized by failures and attempts:",
                result.long_relations,
                "long_over_10km",
            ),
            "long_ho_table": (
                "Professional Long HO relation table:",
                result.long_ho_table,
                "long_ho_table",
            ),
            "missing_targets": (
                "Relations whose target location is missing:",
                result.missing_target_locations,
                "missing_targets",
            ),
            "failure_types": (
                "Failure-type ranking. Would you like the relation-level detail or an explanation "
                "and recommended checks for one failure type?",
                result.failure_types,
                "failure_types",
            ),
            "failure_detail": (
                "Relation-level failure detail. Would you like this filtered by Source, Target, "
                "or failure type?",
                result.failure_detail,
                "failure_detail",
            ),
            "source_offenders": (
                "Top Source offenders ranked by failures and number of affected targets. Would "
                "you like to drill into one Source or review its dominant failure type?",
                result.source_offenders,
                "source_offenders",
            ),
            "target_offenders": (
                "Top Target offenders ranked by failures and number of affected Sources. Would "
                "you like to drill into one Target or review its dominant failure type?",
                result.target_offenders,
                "target_offenders",
            ),
        }
        if view not in views:
            raise ValueError(f"Unknown analysis view: {view}")
        text, table, action = views[view]
        table = table.copy()
        filters = {
            "Source_ID": source,
            "Target_ID": target,
            "Failure_Type": failure_type,
        }
        applied: list[str] = []
        for column, value in filters.items():
            if value and column in table.columns:
                table = table[
                    table[column].astype(str).str.contains(value, case=False, na=False, regex=False)
                ]
                applied.append(f"{column} contains {value!r}")
        if applied:
            text = f"{text} Applied filters: {', '.join(applied)}."
        return AgentReply(text=text, table=table.head(limit), action=action)

    def _create_chart(
        self,
        view: str = "relations",
        chart_type: str = "horizontal_bar",
        metric: str = "Total_Failures",
        top_n: int = 10,
    ) -> AgentReply:
        result = self._ensure_result()
        configurations: dict[str, tuple[pd.DataFrame, str, str]] = {
            "source_offenders": (result.source_offenders, "Source_ID", "Total_Failures"),
            "target_offenders": (result.target_offenders, "Target_ID", "Total_Failures"),
            "failure_types": (result.failure_types, "Failure_Type", "Total_Failures"),
            "distance_bands": (result.distance_bands, "Distance_Band", "Failures"),
            "relations": (result.relation_detail, "Relation", "Failures"),
        }
        if view not in configurations:
            raise ValueError(f"Unknown chart view: {view}")
        frame, label_column, default_metric = configurations[view]
        frame = frame.copy()
        if view == "relations":
            frame[label_column] = (
                frame["Source_ID"].astype(str) + " → " + frame["Target_ID"].astype(str)
            )
        if metric not in frame.columns:
            metric = default_metric
        if metric not in frame.columns:
            raise ValueError(f"Chart metric is not available for {view}: {metric}")
        frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
        frame = frame.dropna(subset=[metric]).sort_values(metric, ascending=False)
        top_n = max(1, min(100, int(top_n)))
        available = len(frame)
        shown = frame.head(top_n)
        if shown.empty:
            return AgentReply(
                text="There is no chartable data for that request.",
                table=shown,
                action="create_chart",
            )
        entity_name = view.replace("_", " ").title()
        title = f"Top {len(shown)} {entity_name} by {metric}"
        availability_note = ""
        if available < top_n:
            availability_note = (
                f" You requested {top_n}, but this view contains only {available} distinct "
                f"{entity_name}; showing all available rows."
            )
            if view == "source_offenders":
                availability_note += (
                    " Try 'top Target offenders' or generic 'top offenders' to rank "
                    "Source→Target relations."
                )
        return AgentReply(
            text=(
                f"Created a customizable {chart_type.replace('_', ' ')} chart for {len(shown)} "
                f"{view.replace('_', ' ')} ranked by {metric}. You can change the chart type, "
                f"label, metric, or Top N in the chart window.{availability_note}"
            ),
            table=shown,
            action="create_chart",
            visualization={
                "kind": "chart",
                "view": view,
                "chart_type": chart_type,
                "metric": metric,
                "label_column": label_column,
                "top_n": top_n,
                "title": title,
                "entity_name": entity_name,
            },
            visualization_data=frame.head(100),
        )

    def _create_filtered_map(
        self,
        metric: str = "Failures",
        top_n: int = 50,
        min_distance_km: float = 0.0,
        min_failures: int = 0,
        min_attempts: int = 0,
    ) -> AgentReply:
        result = self._ensure_result()
        frame = result.relation_detail.copy()
        required_coordinates = ["src_lat", "src_lon", "tgt_lat", "tgt_lon"]
        if not all(column in frame.columns for column in required_coordinates):
            raise ValueError("The analyzed dataset does not contain map coordinates.")
        frame = frame.dropna(subset=required_coordinates)
        filters: list[str] = []
        if min_distance_km > 0 and "Distance_km" in frame.columns:
            frame = frame[
                pd.to_numeric(frame["Distance_km"], errors="coerce") >= min_distance_km
            ]
            filters.append(f"distance ≥ {min_distance_km:g} km")
        if min_failures > 0 and "Failures" in frame.columns:
            frame = frame[
                pd.to_numeric(frame["Failures"], errors="coerce").fillna(0) >= min_failures
            ]
            filters.append(f"failures ≥ {min_failures}")
        if min_attempts > 0 and "Attempts" in frame.columns:
            frame = frame[
                pd.to_numeric(frame["Attempts"], errors="coerce").fillna(0) >= min_attempts
            ]
            filters.append(f"attempts ≥ {min_attempts}")
        allowed_metrics = ("Failures", "Attempts", "Fail_Rate", "Distance_km")
        if metric not in allowed_metrics or metric not in frame.columns:
            metric = "Failures"
        frame = frame.sort_values(metric, ascending=False, na_position="last")
        top_n = max(1, min(2000, int(top_n)))
        shown = frame.head(top_n)
        if shown.empty:
            return AgentReply(
                text=(
                    "No mapped relations match those filters. Try reducing the distance, "
                    "failures, or attempts threshold."
                ),
                table=shown,
                action="create_map",
            )
        filter_text = ", ".join(filters) if filters else "all mapped relations"
        title = f"AI HO Map · {filter_text} · ranked by {metric}"
        return AgentReply(
            text=(
                f"Prepared a map with {len(shown)} relations using {filter_text}, ranked by "
                f"{metric}. The map shows Source→Target paths and the underlying attempts, "
                "failures, and distance."
            ),
            table=shown,
            action="create_map",
            visualization={
                "kind": "map",
                "metric": metric,
                "top_n": top_n,
                "min_distance_km": float(min_distance_km),
                "min_failures": int(min_failures),
                "min_attempts": int(min_attempts),
                "title": title,
            },
        )

    def _chart_from_prompt(self, qn: str) -> AgentReply:
        if "target" in qn and "offender" in qn:
            view = "target_offenders"
        elif "source" in qn and "offender" in qn:
            view = "source_offenders"
        elif "failure type" in qn or "failure distribution" in qn or "failures by" in qn:
            view = "failure_types"
        elif "distance band" in qn:
            view = "distance_bands"
        elif "relation" in qn and "offender" not in qn:
            view = "relations"
        else:
            view = "relations"

        if "pie" in qn or "donut" in qn:
            chart_type = "donut"
        elif "line" in qn:
            chart_type = "line"
        elif "vertical" in qn or "column chart" in qn:
            chart_type = "vertical_bar"
        else:
            chart_type = "horizontal_bar"

        if "unique peer" in qn or "affected peer" in qn:
            metric = "Unique_Peers"
        elif "fail rate" in qn or "failure rate" in qn:
            metric = "Fail_Rate"
        elif "attempt" in qn:
            metric = "Attempts"
        elif "distance" in qn and view == "relations":
            metric = "Distance_km"
        elif view in {"source_offenders", "target_offenders", "failure_types"}:
            metric = "Total_Failures"
        else:
            metric = "Failures"
        return self._create_chart(
            view=view,
            chart_type=chart_type,
            metric=metric,
            top_n=self._extract_top_n(qn, 10),
        )

    def _map_from_prompt(self, qn: str) -> AgentReply:
        numeric = self._extract_numeric_filters(qn)

        def requested_minimum(column: str) -> float:
            operator, value = numeric.get(column, (">=", 0.0))
            return value if operator in {">", ">=", "="} else 0.0

        min_distance = requested_minimum("Distance_km")
        min_failures = int(requested_minimum("Failures"))
        min_attempts = int(requested_minimum("Attempts"))
        if min_failures == 0 and any(
            phrase in qn for phrase in ("with fail", "only fail", "failed relation")
        ):
            min_failures = 1
        if "rank by distance" in qn or "longest" in qn:
            metric = "Distance_km"
        elif "rank by attempts" in qn or "most attempts" in qn:
            metric = "Attempts"
        elif "fail rate" in qn:
            metric = "Fail_Rate"
        else:
            metric = "Failures"
        return self._create_filtered_map(
            metric=metric,
            top_n=self._extract_top_n(qn, 50),
            min_distance_km=min_distance,
            min_failures=min_failures,
            min_attempts=min_attempts,
        )

    def _add_proactive_insights(self, reply: AgentReply) -> AgentReply:
        """Append concise, computed engineering observations to analytical replies."""
        if reply.action not in self.DIRECT_DATA_ACTIONS or self.analyzer.last_result is None:
            return reply
        if reply.table is not None and reply.table.empty:
            return reply
        result = self.analyzer.last_result
        observations: list[str] = []
        next_step = "Drill into the dominant failure type and validate its recommended checks."

        failure_types = result.failure_types
        if not failure_types.empty:
            top_failure = failure_types.iloc[0]
            failure_name = str(top_failure.get("Failure_Type", "Unknown"))
            failure_count = float(top_failure.get("Total_Failures", 0) or 0)
            failure_share = float(top_failure.get("Failure_Share", 0) or 0)
            observations.append(
                f"{failure_name} is the dominant failure: {failure_count:,.0f} events "
                f"({failure_share:.1%} of classified failures)."
            )
            checks = failure_recommended_checks(failure_name)
            if checks:
                next_step = f"For {failure_name}, start with: {checks}"

        total_failures = float(
            pd.to_numeric(
                failure_types.get("Total_Failures", pd.Series(dtype=float)), errors="coerce"
            ).sum()
        )
        if reply.action in {"source_offenders", "create_chart", "analysis", "summary"}:
            view = (reply.visualization or {}).get("view")
            if view in (None, "source_offenders") and not result.source_offenders.empty:
                source = result.source_offenders.iloc[0]
                source_failures = float(source.get("Total_Failures", 0) or 0)
                concentration = source_failures / total_failures if total_failures > 0 else 0.0
                observations.append(
                    f"Top Source {source.get('Source_ID', 'N/A')} contributes "
                    f"{source_failures:,.0f} failures ({concentration:.1%}) across "
                    f"{int(source.get('Unique_Peers', 0) or 0)} unique Targets."
                )
        if reply.action == "target_offenders" or (
            reply.action == "create_chart"
            and (reply.visualization or {}).get("view") == "target_offenders"
        ):
            if not result.target_offenders.empty:
                target = result.target_offenders.iloc[0]
                observations.append(
                    f"Top Target {target.get('Target_ID', 'N/A')} is shared by "
                    f"{int(target.get('Unique_Peers', 0) or 0)} Sources and accumulates "
                    f"{float(target.get('Total_Failures', 0) or 0):,.0f} failures."
                )
                next_step = (
                    "Compare the affected Sources against the Target's load, admission, "
                    "transport, and neighbor consistency."
                )
        if reply.action == "create_map" and reply.table is not None:
            mapped = reply.table
            distances = pd.to_numeric(mapped.get("Distance_km"), errors="coerce").dropna()
            failures = pd.to_numeric(mapped.get("Failures"), errors="coerce").fillna(0)
            if not distances.empty:
                observations.append(
                    f"The selected map spans {distances.min():.2f}–{distances.max():.2f} km "
                    f"and contains {failures.sum():,.0f} failures."
                )
            next_step = (
                "Inspect repeated long paths from one Source and Targets shared by several "
                "Sources; distance alone is a screening signal, not proof of overshooting."
            )

        try:
            summary = result.summary.set_index("KPI")["Value"]
            coverage = float(summary.get("Mapped Coverage", 1.0))
            if coverage < 0.8 and reply.action in {"analysis", "summary", "create_map"}:
                observations.append(
                    f"Only {coverage:.1%} of relations have usable distance mapping; geographic "
                    "conclusions may be incomplete."
                )
        except (KeyError, TypeError, ValueError):
            pass

        if not observations:
            return reply
        reply.text = (
            f"{reply.text}\n\nAI observations:\n- "
            + "\n- ".join(observations[:3])
            + f"\n\nSuggested next action: {next_step}"
        )
        return reply

    @staticmethod
    def _tool_schemas() -> list[dict[str, Any]]:
        """Schemas exposed to Ollama; execution remains inside this process."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_handover_analysis",
                    "description": "Run the deterministic 5G handover analysis on loaded files.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_analysis_view",
                    "description": "Read a deterministic table from the latest completed analysis.",
                    "parameters": {
                        "type": "object",
                        "required": ["view"],
                        "properties": {
                            "view": {
                                "type": "string",
                                "description": (
                                    "Use relations for generic 'top offenders'. Use source_offenders "
                                    "or target_offenders only when the user explicitly names that side."
                                ),
                                "enum": [
                                    "summary",
                                    "top_failures",
                                    "distance_bands",
                                    "long_relations",
                                    "long_ho_table",
                                    "missing_targets",
                                    "failure_types",
                                    "failure_detail",
                                    "source_offenders",
                                    "target_offenders",
                                ],
                            },
                            "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
                            "source": {
                                "type": "string",
                                "description": "Optional Source ID substring filter",
                            },
                            "target": {
                                "type": "string",
                                "description": "Optional Target ID substring filter",
                            },
                            "failure_type": {
                                "type": "string",
                                "description": "Optional failure-counter name substring filter",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_handover_relations",
                    "description": (
                        "Filter and sort analyzed HO relations using the application's existing "
                        "query parser; use for site, carrier, distance, attempts, failures, "
                        "or rate filters."
                    ),
                    "parameters": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_custom_chart",
                    "description": (
                        "Create and open an interactive chart from deterministic HO results. "
                        "Use this whenever the user asks to graph, plot, chart, visualize, or "
                        "create a bar, line, pie, or donut graph."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "view": {
                                "type": "string",
                                "enum": [
                                    "source_offenders",
                                    "target_offenders",
                                    "failure_types",
                                    "distance_bands",
                                    "relations",
                                ],
                            },
                            "chart_type": {
                                "type": "string",
                                "enum": ["horizontal_bar", "vertical_bar", "line", "donut"],
                            },
                            "metric": {
                                "type": "string",
                                "description": (
                                    "Numeric metric such as Total_Failures, Failures, Attempts, "
                                    "Unique_Peers, Fail_Rate, or Distance_km"
                                ),
                            },
                            "top_n": {"type": "integer", "minimum": 1, "maximum": 100},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_filtered_map",
                    "description": (
                        "Create and open a Source-to-Target map filtered by minimum distance, "
                        "failures, and attempts. Use whenever the user asks to create, show, "
                        "or plot relations on a map."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "enum": ["Failures", "Attempts", "Fail_Rate", "Distance_km"],
                            },
                            "top_n": {"type": "integer", "minimum": 1, "maximum": 2000},
                            "min_distance_km": {"type": "number", "minimum": 0},
                            "min_failures": {"type": "integer", "minimum": 0},
                            "min_attempts": {"type": "integer", "minimum": 0},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "lookup_kpi_definition",
                    "description": (
                        "Look up KPI meaning, formula, stage, and XnAP lens in the local catalog."
                    ),
                    "parameters": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "lookup_xnap_guidance",
                    "description": (
                        "Retrieve standards-aware XnAP/3GPP procedure, timer, report, "
                        "and Cause IE guidance."
                    ),
                    "parameters": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "build_xnap_diagnosis",
                    "description": (
                        "Build the evidence-based XnAP/3GPP diagnostic from the latest analysis."
                    ),
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def _select_tool_schemas(self, prompt: str) -> list[dict[str, Any]]:
        """Reduce tool-choice ambiguity for compact local models."""
        schemas = self._tool_schemas()
        qn = self._normalize(prompt)
        explicit_names = {
            str(schema["function"]["name"]): schema for schema in schemas
        }
        for name, schema in explicit_names.items():
            if name in prompt.lower():
                return [schema]

        chart_terms = ("graph", "chart", "plot", "visualize", "bar graph", "pie", "donut")
        if any(term in qn for term in chart_terms):
            return [explicit_names["create_custom_chart"]]
        if any(term in qn for term in (" map", "map ", "mapping", "on map")):
            return [explicit_names["create_filtered_map"]]

        selected_names: set[str] = set()
        if any(term in qn for term in ("xnap", "3gpp", "38 423", "txnreloc", "cause ie")):
            selected_names.add(
                "build_xnap_diagnosis"
                if any(term in qn for term in ("diagnos", "root cause", "recommend"))
                else "lookup_xnap_guidance"
            )
        if any(term in qn for term in ("kpi", "formula", "definition")):
            selected_names.add("lookup_kpi_definition")
        if any(term in qn for term in ("run analysis", "start analysis", "process files")):
            selected_names.add("run_handover_analysis")
        if any(
            term in qn
            for term in (
                "summary",
                "top failure",
                "distance band",
                "long relation",
                "long ho table",
                "missing target",
                "failure type",
                "failure breakdown",
                "failure detail",
                "source offender",
                "target offender",
                "many target",
                "many source",
            )
        ):
            selected_names.add("get_analysis_view")
        if self._is_advanced_filter_request(qn) and any(
            term in qn for term in ("where", "filter", "sort", ">", "<", "=")
        ):
            selected_names.add("query_handover_relations")

        if not selected_names:
            return schemas
        return [schema for name, schema in explicit_names.items() if name in selected_names]

    def _execute_tool(self, name: str, arguments: Mapping[str, Any]) -> AgentReply:
        if name == "run_handover_analysis":
            return self._handle_deterministic("run analysis")
        if name == "get_analysis_view":
            return self._analysis_view(
                str(arguments.get("view", "summary")),
                int(arguments.get("limit", 50)),
                source=str(arguments.get("source", "")),
                target=str(arguments.get("target", "")),
                failure_type=str(arguments.get("failure_type", "")),
            )
        if name == "query_handover_relations":
            query = str(arguments.get("query", "")).strip()
            if not query:
                raise ValueError("query_handover_relations requires a query")
            return self._run_advanced_query(self._normalize(query))
        if name == "create_custom_chart":
            return self._create_chart(
                view=str(arguments.get("view", "relations")),
                chart_type=str(arguments.get("chart_type", "horizontal_bar")),
                metric=str(arguments.get("metric", "Total_Failures")),
                top_n=int(arguments.get("top_n", 10)),
            )
        if name == "create_filtered_map":
            return self._create_filtered_map(
                metric=str(arguments.get("metric", "Failures")),
                top_n=int(arguments.get("top_n", 50)),
                min_distance_km=float(arguments.get("min_distance_km", 0)),
                min_failures=int(arguments.get("min_failures", 0)),
                min_attempts=int(arguments.get("min_attempts", 0)),
            )
        if name == "lookup_kpi_definition":
            query = str(arguments.get("query", "")).strip()
            reply = self._kpi_logic_answer(f"explain {query}", self._normalize(f"explain {query}"))
            return reply or AgentReply(
                text="No matching KPI definition was found.", action="kpi_explain"
            )
        if name == "lookup_xnap_guidance":
            query = str(arguments.get("query", "")).strip()
            reply = self._xnap_knowledge_answer(f"xnap {query}", self._normalize(f"xnap {query}"))
            if reply is None:  # Defensive: the prefixed query should always trigger the catalog.
                raise ValueError("No XnAP guidance was found")
            return reply
        if name == "build_xnap_diagnosis":
            reply = self._standards_diagnostic_answer("xnap diagnosis")
            if reply is None:  # Defensive: fixed intent always triggers the diagnostic.
                raise ValueError("Could not build XnAP diagnosis")
            return reply
        raise ValueError(f"Ollama requested an unknown tool: {name}")

    @staticmethod
    def _reply_as_tool_json(reply: AgentReply) -> str:
        rows: list[dict[str, Any]] = []
        columns: list[str] = []
        row_count = 0
        if reply.table is not None:
            columns = [str(column) for column in reply.table.columns]
            row_count = len(reply.table)
            # Keep the model context bounded; the complete DataFrame is still returned to the UI.
            rows = json.loads(reply.table.head(30).to_json(orient="records", date_format="iso"))
        return json.dumps(
            {
                "action": reply.action,
                "message": reply.text,
                "row_count": row_count,
                "columns": columns,
                "rows": rows,
                "visualization": reply.visualization,
                "grounding": "Computed by local deterministic application code",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _message_value(message: Any, key: str, default: Any = None) -> Any:
        if isinstance(message, Mapping):
            return message.get(key, default)
        return getattr(message, key, default)

    @classmethod
    def _assistant_message_dict(cls, message: Any) -> dict[str, Any]:
        if isinstance(message, Mapping):
            return dict(message)
        if hasattr(message, "model_dump"):
            return message.model_dump(exclude_none=True)
        out = {"role": "assistant", "content": cls._message_value(message, "content", "")}
        tool_calls = cls._message_value(message, "tool_calls", None)
        if tool_calls:
            out["tool_calls"] = tool_calls
        return out

    @classmethod
    def _tool_call_parts(cls, tool_call: Any) -> tuple[str, dict[str, Any]]:
        function = cls._message_value(tool_call, "function", {})
        name = str(cls._message_value(function, "name", ""))
        arguments = cls._message_value(function, "arguments", {}) or {}
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        return name, dict(arguments)

    def _get_ollama_client(self) -> Any:
        if self._ollama_client is None:
            from ollama import Client

            self._ollama_client = Client(
                host=self.ollama_config.host,
                timeout=self.ollama_config.timeout_seconds,
            )
        return self._ollama_client

    def _requires_grounded_tool(self, prompt: str) -> bool:
        qn = self._normalize(prompt)
        domain_terms = (
            "analysis",
            "analyze",
            "handover",
            " ho ",
            "xnap",
            "3gpp",
            "38 423",
            "kpi",
            "relation",
            "failure",
            "fail",
            "distance",
            "carrier",
            "sector",
            "site",
            "overshoot",
            "txnreloc",
            "graph",
            "chart",
            "plot",
            "map",
        )
        padded = f" {qn} "
        return any(term in padded for term in domain_terms)

    def _handle_with_ollama(self, prompt: str) -> AgentReply:
        client = self._get_ollama_client()
        selected_tools = self._select_tool_schemas(prompt)
        selected_tool_names = ", ".join(
            str(schema["function"]["name"]) for schema in selected_tools
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a local 5G handover engineering assistant. For every question "
                    "about loaded data, KPI formulas, XnAP, or 3GPP, call the provided tools "
                    "and ground the answer only in their output. Never invent counters, "
                    "measurements, Cause IE mappings, or standards references. Distance is a "
                    "topology heuristic, not proof of overshooting. Keep answers concise and "
                    "operational and proactive. Surface concentration, dominant failure, multi-peer "
                    "exposure, geographic/data-quality caveats, and one useful engineering next "
                    "step when supported by tool output. After presenting a result, offer one short "
                    "relevant follow-up question about deeper detail, visualization, failure "
                    "explanation, or recommended checks. "
                    "For a domain request, your first response must contain a tool "
                    "call instead of an answer from model memory. Available tools for this request: "
                    f"{selected_tool_names}. You may call multiple tools."
                ),
            },
            *self._conversation[-6:],
            {"role": "user", "content": prompt},
        ]
        last_tool_reply: Optional[AgentReply] = None

        for _round in range(self.ollama_config.max_tool_rounds):
            response = client.chat(
                model=self.ollama_config.model,
                messages=messages,
                tools=selected_tools,
                stream=False,
                options={"temperature": 0.1, "num_predict": 256},
            )
            message = self._message_value(response, "message", response)
            messages.append(self._assistant_message_dict(message))
            tool_calls = self._message_value(message, "tool_calls", None) or []
            if not tool_calls:
                if last_tool_reply is None and self._requires_grounded_tool(prompt):
                    if _round + 1 < self.ollama_config.max_tool_rounds:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Your previous response did not call a tool. Do not answer from "
                                    "memory. Call exactly one available tool now. The available "
                                    f"tool names are: {selected_tool_names}."
                                ),
                            }
                        )
                        continue
                    raise RuntimeError(
                        "Ollama returned an ungrounded domain answer without calling a tool"
                    )
                content = str(self._message_value(message, "content", "")).strip()
                if not content and last_tool_reply is not None:
                    content = last_tool_reply.text
                return AgentReply(
                    text=content or "The local model returned an empty response.",
                    table=last_tool_reply.table if last_tool_reply else None,
                    action=last_tool_reply.action if last_tool_reply else "ollama_chat",
                    backend=f"ollama:{self.ollama_config.model}",
                    visualization=(last_tool_reply.visualization if last_tool_reply else None),
                    visualization_data=(
                        last_tool_reply.visualization_data if last_tool_reply else None
                    ),
                )

            for tool_call in tool_calls:
                name, arguments = self._tool_call_parts(tool_call)
                try:
                    if name == "create_custom_chart":
                        # Ollama selects the capability. Deterministic parsing keeps the user's
                        # entity, metric, chart type, and Top N authoritative.
                        last_tool_reply = self._chart_from_prompt(self._normalize(prompt))
                    elif name == "create_filtered_map":
                        last_tool_reply = self._map_from_prompt(self._normalize(prompt))
                    else:
                        last_tool_reply = self._execute_tool(name, arguments)
                    tool_content = self._reply_as_tool_json(last_tool_reply)
                except Exception as exc:
                    tool_content = json.dumps({"error": str(exc)}, ensure_ascii=False)
                messages.append({"role": "tool", "tool_name": name, "content": tool_content})

            # For data-table actions, Ollama has already performed its agentic
            # job by selecting and calling the tool. Return the authoritative
            # table immediately instead of making a compact model rewrite it.
            if last_tool_reply and last_tool_reply.action in self.DIRECT_DATA_ACTIONS:
                last_tool_reply.backend = f"ollama:{self.ollama_config.model}"
                return last_tool_reply

        if last_tool_reply is not None:
            last_tool_reply.backend = f"ollama:{self.ollama_config.model}"
            return last_tool_reply
        raise RuntimeError("Ollama exceeded the tool-call round limit without a result")

    def _handle_deterministic(self, prompt: str) -> AgentReply:
        q = prompt.strip().lower()
        qn = self._normalize(q)

        if self._intent_score(
            qn, ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        ) > 0 and len(qn.split()) <= 4:
            return AgentReply(
                text=(
                    "Hi. I am ready to help with your HO analysis. "
                    "You can start with:\n"
                    "- Run analysis\n"
                    "- Show top failures\n"
                    "- Show relations over 10 km\n"
                    "- Show long HO table\n"
                    "Or type a custom filter like: top 25 where distance > 10 km and fails >= 1"
                ),
                action="greeting",
            )

        diagnostic_answer = self._standards_diagnostic_answer(qn)
        if diagnostic_answer is not None:
            return diagnostic_answer

        xnap_answer = self._xnap_knowledge_answer(prompt.strip(), qn)
        if xnap_answer is not None:
            return xnap_answer

        kpi_answer = self._kpi_logic_answer(prompt.strip(), qn)
        if kpi_answer is not None:
            return kpi_answer

        if any(
            term in qn
            for term in ("graph", "chart", "plot", "visualize", "bar graph", "pie", "donut")
        ):
            return self._chart_from_prompt(qn)

        if any(term in qn for term in (" map", "map ", "mapping", "on map")):
            return self._map_from_prompt(qn)

        if self._intent_score(qn, ["run analysis", "analyze", "start analysis", "process files"]) > 0:
            result = self.analyzer.run()
            mapped = result.relation_detail["Distance_km"].notna().sum()
            total = len(result.relation_detail)
            missing_tgt = len(result.missing_target_locations)
            warn = ""
            if missing_tgt > 0:
                warn = (
                    f" Warning: {missing_tgt} relation(s) have missing TARGET location, "
                    "so distance could not be calculated for those rows."
                )
            return AgentReply(
                text=(
                    "Analysis completed successfully. "
                    f"I found {total} source-target relations and mapped distances for {mapped}."
                    f"{warn}"
                ),
                table=result.summary,
                action="analysis",
            )

        if any(
            phrase in qn
            for phrase in (
                "failure types",
                "failure type ranking",
                "failure breakdown",
                "failures by type",
                "failure distribution",
            )
        ):
            return self._analysis_view("failure_types", self._extract_top_n(qn, 100))

        if any(
            phrase in qn
            for phrase in ("failure detail", "detailed failures", "failure relation detail")
        ):
            text_filters = self._extract_text_filters(qn)
            failure_match = re.search(
                r"failure type\s*(?:=|is|contains)?\s*([a-z0-9_\-]+)", qn
            )
            return self._analysis_view(
                "failure_detail",
                self._extract_top_n(qn, 200),
                source=text_filters.get("Source_Site", ""),
                target=text_filters.get("Target_Site", ""),
                failure_type=failure_match.group(1) if failure_match else "",
            )

        if any(
            phrase in qn
            for phrase in (
                "source offenders",
                "source offender",
                "worst sources",
                "sources affecting many targets",
                "source with many targets",
            )
        ):
            return self._analysis_view("source_offenders", self._extract_top_n(qn, 50))

        if any(
            phrase in qn
            for phrase in (
                "target offenders",
                "target offender",
                "worst targets",
                "targets affecting many sources",
                "target with many sources",
            )
        ):
            return self._analysis_view("target_offenders", self._extract_top_n(qn, 50))

        # Advanced dynamic filter mode (priority)
        if self._is_advanced_filter_request(qn) and any(
            x in qn for x in ["where", "filter", "sort", "order by", ">", "<", "=", "top "]
        ):
            return self._run_advanced_query(qn)

        top_fail_score = self._intent_score(
            qn,
            [
                "top failures",
                "most failures",
                "relations with more failures",
                "relation with more fails",
                "more fails",
                "highest fails",
                "worst relations",
                "ms fallas",
            ],
        )
        if top_fail_score > 0 or ("fail" in qn and "relation" in qn):
            result = self._ensure_result()
            df = result.top_failures.head(20)
            return AgentReply(
                text="Top HO relations by failure count (highest to lowest):",
                table=df,
                action="top_failures",
            )

        if self._intent_score(qn, [">10km", "over 10km", "more than 10km", "10 km", "above 10 km"]) > 0:
            result = self._ensure_result()
            df = result.long_relations.head(50)
            if df.empty:
                return AgentReply(text="No relations above 10 km were found in the mapped dataset.")
            return AgentReply(
                text="These are the HO relations above 10 km, prioritized by failures and attempts:",
                table=df,
                action="long_over_10km",
            )

        if self._intent_score(
            qn,
            [
                "long ho table",
                "professional table",
                "show long ho",
                "show distance table",
                "tabla long ho",
            ],
        ) > 0:
            result = self._ensure_result()
            df = result.long_ho_table.head(1000)
            if df.empty:
                return AgentReply(text="No Long HO rows (>=5 km) were found with mapped coordinates.")
            return AgentReply(
                text="Professional Long HO table generated (source-target-distance-attempts/failures):",
                table=df,
                action="long_ho_table",
            )

        if self._intent_score(qn, ["summary", "kpi", "overview", "executive"]) > 0:
            result = self._ensure_result()
            return AgentReply(text="Executive KPI summary:", table=result.summary, action="summary")

        if self._intent_score(qn, ["distance bands", "band", "distribution", "distance distribution"]) > 0:
            result = self._ensure_result()
            return AgentReply(
                text="HO distribution by distance band:",
                table=result.distance_bands,
                action="distance_bands",
            )

        if self._intent_score(
            qn,
            [
                "missing target",
                "targets without location",
                "missing locations",
                "target without coordinates",
                "targets missing coordinates",
            ],
        ) > 0:
            result = self._ensure_result()
            df = result.missing_target_locations.head(200)
            if df.empty:
                return AgentReply(text="All targets have location coordinates available.")
            return AgentReply(
                text=f"I found {len(result.missing_target_locations)} relation(s) with missing target location.",
                table=df,
                action="missing_targets",
            )

        if self._intent_score(qn, ["help", "what can you do", "commands"]) > 0:
            return AgentReply(
                text=(
                    "I can run HO analysis and answer KPI-based requests. Try:\n"
                    "- Run analysis\n"
                    "- Show top failures\n"
                    "- Show relations over 10 km\n"
                    "- Show executive summary\n"
                    "- Show distance bands\n"
                    "- top 30 where source parkway and fails > 2\n"
                    "- filter target brentwood distance > 8 km sort by failures\n"
                    "- where source carrier 7 and attempts >= 100 sort by fail rate\n"
                    "- explain EndcIntraChgFail_DuTimeout_per_GNB\n"
                    "- show all kpi catalog\n"
                    "- explain TXnRELOCprep\n"
                    "- standards diagnosis\n"
                    "- explain HO too early vs wrong cell"
                    "\n- Create a bar graph with the top 5 Source offenders"
                    "\n- Create a map with failures and distance > 10 km"
                )
            )

        # Advanced dynamic filter mode (fallback)
        if self._is_advanced_filter_request(qn):
            return self._run_advanced_query(qn)

        return AgentReply(
            text=(
                "I can help with that. I did not fully understand the exact request yet.\n"
                "Try one of these:\n"
                "- Run analysis\n"
                "- Show top failures\n"
                "- Show executive summary\n"
                "- Show distance bands\n"
                "- Show long HO table\n"
                "- Create a bar graph with the top 5 offenders\n"
                "- Create a map with failures and distance > 10 km\n"
                "Or write a custom query: top 25 where distance > 10 km and fails >= 1"
            )
        )

    def handle(self, prompt: str) -> AgentReply:
        """Use Ollama tool calling when available, with deterministic local fallback."""
        if not prompt.strip():
            return AgentReply(text="Please enter a handover-analysis request.")
        if not self.ollama_config.enabled:
            reply = self._handle_deterministic(prompt)
        else:
            try:
                reply = self._handle_with_ollama(prompt)
                self.last_ollama_error = None
            except Exception as exc:
                self.last_ollama_error = str(exc)
                reply = self._handle_deterministic(prompt)
                reply.backend = "rules-fallback"
        reply = self._add_proactive_insights(reply)
        self._conversation.extend(
            [
                {"role": "user", "content": prompt.strip()[:2000]},
                {"role": "assistant", "content": reply.text[:3000]},
            ]
        )
        self._conversation = self._conversation[-8:]
        return reply
