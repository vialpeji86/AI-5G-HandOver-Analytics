"""Public result models returned by the analysis engine."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class AnalysisResult:
    summary: pd.DataFrame
    relation_detail: pd.DataFrame
    top_failures: pd.DataFrame
    long_relations: pd.DataFrame
    distance_bands: pd.DataFrame
    missing_target_locations: pd.DataFrame
    long_ho_table: pd.DataFrame
    failure_types: pd.DataFrame
    failure_detail: pd.DataFrame
    source_offenders: pd.DataFrame
    target_offenders: pd.DataFrame
