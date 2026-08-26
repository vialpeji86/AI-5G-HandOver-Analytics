"""Flexible column-role inference for heterogeneous handover exports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


def normalize_column_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "source": (
        "sourceid",
        "source",
        "srcid",
        "src",
        "sourcecellid",
        "sourcecell",
        "servingcell",
        "localcellid",
        "sourceenodeb",
        "enodebsource",
        "sourcegnb",
        "enodeb",
        "eutrancell",
        "du",
    ),
    "target": (
        "targetid",
        "target",
        "tgtid",
        "tgt",
        "targetcellid",
        "targetcell",
        "neighborcell",
        "neighbourcell",
        "targetenodeb",
        "enodebtarget",
        "targetgnb",
        "celltarget",
        "tgtdu",
    ),
    "attempts": (
        "attempts",
        "attempt",
        "hoattempts",
        "handoverattempts",
        "endcintrachgattpergnb",
        "endcinterchgsrcattpergnb",
    ),
    "success": (
        "success",
        "successes",
        "hosuccess",
        "hosuccesses",
        "endcintrachgsuccpergnb",
        "endcinterchgsrcsuccpergnb",
    ),
    "date": ("day", "date", "datetime", "timestamp", "period", "reportdate"),
    "source_site": ("sourcesite", "srcsite", "duname", "site", "sourcename"),
    "target_site": ("targetsite", "tgtsite", "targetname", "tgtduname"),
    "source_cell": (
        "sourcecellid",
        "sourcecell",
        "srccellid",
        "eutrancell",
        "cellid",
        "cell",
    ),
    "target_cell": (
        "targetcellid",
        "targetcell",
        "tgtcellid",
        "celltarget",
        "neighborcellid",
    ),
}


@dataclass
class HOSchemaMapping:
    source: Optional[str] = None
    target: Optional[str] = None
    attempts: Optional[str] = None
    success: Optional[str] = None
    date: Optional[str] = None
    source_site: Optional[str] = None
    target_site: Optional[str] = None
    source_cell: Optional[str] = None
    target_cell: Optional[str] = None
    failure_columns: list[str] = field(default_factory=list)

    def required_missing(self) -> list[str]:
        missing = []
        if not self.source:
            missing.append("source")
        if not self.target:
            missing.append("target")
        if not self.failure_columns:
            missing.append("failure_columns")
        return missing


@dataclass
class SchemaInference:
    mapping: HOSchemaMapping
    confidence: dict[str, int]
    candidates: dict[str, list[str]]
    needs_review: bool
    notes: list[str]


def _numeric_ratio(series: pd.Series) -> float:
    nonempty = series.dropna()
    if nonempty.empty:
        return 0.0
    numeric = pd.to_numeric(nonempty, errors="coerce")
    return float(numeric.notna().mean())


def _role_candidates(columns: list[str], role: str) -> list[tuple[str, int]]:
    aliases = ROLE_ALIASES[role]
    ranked: list[tuple[str, int]] = []
    for column in columns:
        normalized = normalize_column_name(column)
        score = 0
        for index, alias in enumerate(aliases):
            if normalized == alias:
                score = max(score, 100 - min(index, 10))
            elif len(alias) >= 4 and alias in normalized:
                score = max(score, 82 - min(index, 10))
        if role == "source" and normalized.startswith(("src", "source", "serving")):
            score = max(score, 88)
        if role == "target" and normalized.startswith(("tgt", "target", "neighbor", "neighbour")):
            score = max(score, 88)
        if score:
            ranked.append((column, score))
    return sorted(ranked, key=lambda item: (-item[1], columns.index(item[0])))


def infer_failure_columns(df: pd.DataFrame, excluded: set[str] | None = None) -> list[str]:
    excluded = excluded or set()
    failure_tokens = (
        "fail",
        "failure",
        "timeout",
        "error",
        "reject",
        "drop",
        "unsuccess",
        "abort",
        "cancel",
        "coveragehole",
        "coveragegap",
        "tooearly",
        "toolate",
        "rlf",
        "pingpong",
        "wrongcell",
    )
    detected: list[str] = []
    for column in df.columns:
        if column in excluded:
            continue
        normalized = normalize_column_name(column)
        if any(token in normalized for token in failure_tokens) and _numeric_ratio(df[column]) >= 0.5:
            detected.append(str(column))
    return detected


def infer_ho_schema(df: pd.DataFrame) -> SchemaInference:
    columns = [str(column) for column in df.columns]
    mapping = HOSchemaMapping()
    confidence: dict[str, int] = {}
    candidates: dict[str, list[str]] = {}
    notes: list[str] = []

    for role in ROLE_ALIASES:
        ranked = _role_candidates(columns, role)
        candidates[role] = [column for column, _score in ranked]
        if ranked:
            setattr(mapping, role, ranked[0][0])
            confidence[role] = ranked[0][1]
            if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 8:
                notes.append(
                    f"{role} is ambiguous between {ranked[0][0]!r} and {ranked[1][0]!r}."
                )
        else:
            confidence[role] = 0

    # Recognize the common LTE MRO layout as composite eNodeB + cell IDs.
    normalized_lookup = {normalize_column_name(column): column for column in columns}
    if {"enodeb", "eutrancell"}.issubset(normalized_lookup):
        mapping.source = normalized_lookup["enodeb"]
        mapping.source_cell = normalized_lookup["eutrancell"]
        confidence["source"] = 99
        confidence["source_cell"] = 99
        notes = [note for note in notes if not note.startswith("source is ambiguous")]
    if {"enodebtarget", "celltarget"}.issubset(normalized_lookup):
        mapping.target = normalized_lookup["enodebtarget"]
        mapping.target_cell = normalized_lookup["celltarget"]
        confidence["target"] = 99
        confidence["target_cell"] = 99
        notes = [note for note in notes if not note.startswith("target is ambiguous")]

    def first_matching(predicate) -> Optional[str]:
        return next(
            (column for column in columns if predicate(normalize_column_name(column))),
            None,
        )

    source_node = first_matching(
        lambda name: (
            any(token in name for token in ("enodeb", "gnb", "sourcenode", "servingnode"))
            and not any(token in name for token in ("target", "tgt", "neighbor", "neighbour"))
        )
    )
    target_node = first_matching(
        lambda name: (
            any(token in name for token in ("enodeb", "gnb", "node"))
            and any(token in name for token in ("target", "tgt", "neighbor", "neighbour"))
        )
    )
    source_cell = first_matching(
        lambda name: (
            "eutrancell" in name
            or ("cell" in name and any(token in name for token in ("source", "src", "serving")))
        )
    )
    target_cell = first_matching(
        lambda name: (
            "celltarget" in name
            or ("cell" in name and any(token in name for token in ("target", "tgt")))
        )
    )
    if source_node and source_cell:
        mapping.source = source_node
        mapping.source_cell = source_cell
        confidence["source"] = 96
        confidence["source_cell"] = 96
        notes = [
            note
            for note in notes
            if not note.startswith(("source is ambiguous", "source_cell is ambiguous"))
        ]
    if target_node and target_cell:
        mapping.target = target_node
        mapping.target_cell = target_cell
        confidence["target"] = 96
        confidence["target_cell"] = 96
        notes = [
            note
            for note in notes
            if not note.startswith(("target is ambiguous", "target_cell is ambiguous"))
        ]

    # Do not reuse a primary Source/Target column as optional metadata.
    for optional_role in ("source_site", "target_site", "source_cell", "target_cell"):
        if getattr(mapping, optional_role) in {mapping.source, mapping.target}:
            setattr(mapping, optional_role, None)

    excluded = {
        column
        for column in (
            mapping.source,
            mapping.target,
            mapping.attempts,
            mapping.success,
            mapping.date,
            mapping.source_site,
            mapping.target_site,
            mapping.source_cell,
            mapping.target_cell,
        )
        if column
    }
    mapping.failure_columns = infer_failure_columns(df, excluded)
    candidates["failure_columns"] = mapping.failure_columns.copy()
    confidence["failure_columns"] = 95 if mapping.failure_columns else 0

    missing = mapping.required_missing()
    if missing:
        notes.append("Required mapping missing: " + ", ".join(missing))
    low_confidence = any(confidence.get(role, 0) < 80 for role in ("source", "target"))
    ambiguous = any("ambiguous" in note for note in notes)
    needs_review = bool(missing or low_confidence or ambiguous)
    return SchemaInference(mapping, confidence, candidates, needs_review, notes)


def apply_ho_mapping(df: pd.DataFrame, mapping: HOSchemaMapping) -> pd.DataFrame:
    """Create stable generic columns while preserving every original input column."""
    missing = mapping.required_missing()
    if missing:
        raise ValueError("Incomplete HO column mapping: " + ", ".join(missing))

    out = df.copy()
    out["__Source_ID"] = out[mapping.source].astype("string").fillna("")
    out["__Target_ID"] = out[mapping.target].astype("string").fillna("")
    if mapping.attempts:
        out["__Attempts"] = pd.to_numeric(out[mapping.attempts], errors="coerce").fillna(0)
    else:
        out["__Attempts"] = pd.NA
    if mapping.success:
        out["__Success"] = pd.to_numeric(out[mapping.success], errors="coerce").fillna(0)
    else:
        out["__Success"] = pd.NA
    if mapping.date:
        out["__Date"] = pd.to_datetime(out[mapping.date], errors="coerce")
    for column in mapping.failure_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    return out
