from pathlib import Path

import pytest

from ai_ho_analysis.data_loader import load_table


ROOT = Path(__file__).resolve().parents[1]


def test_csv_loader_preserves_synthetic_marker() -> None:
    frame = load_table(ROOT / "data" / "sample_du_locations.csv")
    assert set(frame["DATA_CLASSIFICATION"]) == {"SYNTHETIC"}
    assert frame["SITE_NAME"].str.startswith("SYNTH-").all()


def test_unsupported_extension_is_rejected(tmp_path) -> None:
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        load_table(path)
