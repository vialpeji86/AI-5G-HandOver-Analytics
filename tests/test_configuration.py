import pytest

from ai_ho_analysis import AnalysisConfig


def test_default_thresholds_are_ordered() -> None:
    config = AnalysisConfig()
    assert config.review_handover_km < config.long_handover_km
    assert config.top_relations == 50


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
