from pathlib import Path

import pytest

from ai_ho_analysis import HOAnalyzer
from ai_ho_analysis.data_loader import load_table


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_analyzer() -> HOAnalyzer:
    analyzer = HOAnalyzer()
    analyzer.set_ho_data(load_table(ROOT / "data" / "sample_ho_relations.csv"))
    analyzer.set_map_data(load_table(ROOT / "data" / "sample_du_locations.csv"))
    return analyzer
