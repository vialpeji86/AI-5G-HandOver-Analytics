import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_committed_sample_rows_are_explicitly_synthetic() -> None:
    for path in sorted((ROOT / "data").glob("sample_*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows, f"{path.name} must not be empty"
        assert {row["DATA_CLASSIFICATION"] for row in rows} == {"SYNTHETIC"}


def test_sample_identifiers_use_reserved_demo_range() -> None:
    locations = ROOT / "data" / "sample_du_locations.csv"
    with locations.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["DU"].startswith("900000") for row in rows)
    assert all(row["SITE_NAME"].startswith("SYNTH-") for row in rows)
