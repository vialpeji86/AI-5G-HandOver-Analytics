"""Runtime configuration for handover analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisConfig:
    """Thresholds used to classify distance-related handover behavior."""

    long_handover_km: float = 10.0
    review_handover_km: float = 5.0
    top_relations: int = 50

    def __post_init__(self) -> None:
        if self.review_handover_km < 0:
            raise ValueError("review_handover_km must be non-negative")
        if self.long_handover_km <= self.review_handover_km:
            raise ValueError("long_handover_km must be greater than review_handover_km")
        if self.top_relations < 1:
            raise ValueError("top_relations must be at least 1")
