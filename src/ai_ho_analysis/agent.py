from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Optional

import pandas as pd

from .analysis import HOAnalyzer
from .kpi_knowledge import KPI_DEFS, find_kpi_matches
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


class LocalHOAgent:
    """Open-source, local intent-driven assistant for HO analysis."""

    def __init__(self, analyzer: HOAnalyzer) -> None:
        self.analyzer = analyzer

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
        m = re.search(r"\btop\s+(\d+)\b", qn) or re.search(r"\bfirst\s+(\d+)\b", qn)
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

    def handle(self, prompt: str) -> AgentReply:
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
                "Or write a custom query: top 25 where distance > 10 km and fails >= 1"
            )
        )
