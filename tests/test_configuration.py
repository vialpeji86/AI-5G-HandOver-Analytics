import pytest

from ai_ho_analysis import AnalysisConfig, OllamaConfig


def test_default_thresholds_are_ordered() -> None:
    config = AnalysisConfig()
    assert config.review_handover_km < config.long_handover_km
    assert config.top_relations == 50


def test_default_ollama_model_matches_desktop_setup() -> None:
    assert OllamaConfig().model == "llama3.2:3b"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"review_handover_km": -1},
        {"review_handover_km": 10, "long_handover_km": 10},
        {"top_relations": 0},
    ],
)
def test_invalid_thresholds_are_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        AnalysisConfig(**kwargs)


def test_ollama_configuration_can_be_overridden_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("AI_HO_OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.setenv("AI_HO_OLLAMA_ENABLED", "false")
    monkeypatch.setenv("AI_HO_OLLAMA_TIMEOUT", "30")

    config = OllamaConfig.from_env()

    assert config.model == "llama3.1:8b"
    assert config.enabled is False
    assert config.timeout_seconds == 30
