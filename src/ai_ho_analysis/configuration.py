"""Runtime configuration for handover analysis."""

from __future__ import annotations

import os
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


@dataclass(frozen=True)
class OllamaConfig:
    """Local Ollama runtime settings for the tool-calling assistant."""

    enabled: bool = True
    model: str = "llama3.2:3b"
    host: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 90.0
    max_tool_rounds: int = 4

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Ollama model cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Ollama timeout_seconds must be positive")
        if self.max_tool_rounds < 1:
            raise ValueError("Ollama max_tool_rounds must be at least 1")

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        """Load settings without sending configuration or data to a cloud service."""
        enabled = os.getenv("AI_HO_OLLAMA_ENABLED", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        return cls(
            enabled=enabled,
            model=os.getenv("AI_HO_OLLAMA_MODEL", "llama3.2:3b").strip(),
            host=os.getenv("AI_HO_OLLAMA_HOST", "http://127.0.0.1:11434").strip(),
            timeout_seconds=float(os.getenv("AI_HO_OLLAMA_TIMEOUT", "90")),
            max_tool_rounds=int(os.getenv("AI_HO_OLLAMA_MAX_TOOL_ROUNDS", "4")),
        )
