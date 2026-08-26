from pathlib import Path

import pytest

from ai_ho_analysis.data_loader import load_table
from ai_ho_analysis.schema_inference import HOSchemaMapping, infer_ho_schema


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


def test_delimited_loader_detects_semicolon_format_and_trims_headers(tmp_path) -> None:
    path = tmp_path / "vendor_export.txt"
    path.write_text(
        " Source ; Target ; Failure Timeout \nA;B;3\n",
        encoding="utf-8",
    )

    frame = load_table(path)

    assert list(frame.columns) == ["Source", "Target", "Failure Timeout"]
    assert frame.iloc[0]["Failure Timeout"] == 3


def test_schema_inference_recognizes_vendor_du_target_and_failure_columns() -> None:
    frame = pytest.importorskip("pandas").DataFrame(
        {
            "DAY": ["08/01/2026"],
            "DU": [1001],
            "TGTDU": [1002],
            "EndcIntraChgAtt_per_GNB": [20],
            "EndcIntraChgSucc_per_GNB": [17],
            "EndcIntraChgFail_DuTimeout_per_GNB": [2],
            "EndcIntraChgPrepFail_UpTimeout": [1],
        }
    )

    inference = infer_ho_schema(frame)

    assert inference.mapping.source == "DU"
    assert inference.mapping.target == "TGTDU"
    assert inference.mapping.date == "DAY"
    assert set(inference.mapping.failure_columns) == {
        "EndcIntraChgFail_DuTimeout_per_GNB",
        "EndcIntraChgPrepFail_UpTimeout",
    }
    assert inference.mapping.required_missing() == []


def test_manual_mapping_supports_nonstandard_source_and_target_names() -> None:
    mapping = HOSchemaMapping(
        source="Node A",
        target="Node B",
        failure_columns=["Problem Counter"],
    )

    assert mapping.required_missing() == []


def test_schema_inference_matches_common_lte_header_variations() -> None:
    frame = pytest.importorskip("pandas").DataFrame(
        {
            "Report Date": ["08/26/2026"],
            "Source eNodeB": [252257],
            "EUTRAN Cell ID": [1],
            "Target eNodeB": [253347],
            "Target Cell": [3],
            "Coverage Gap": [4],
            "Ping Pong HO": [2],
        }
    )

    inference = infer_ho_schema(frame)

    assert inference.needs_review is False
    assert inference.mapping.source == "Source eNodeB"
    assert inference.mapping.source_cell == "EUTRAN Cell ID"
    assert inference.mapping.target == "Target eNodeB"
    assert inference.mapping.target_cell == "Target Cell"
    assert inference.mapping.date == "Report Date"
    assert inference.mapping.failure_columns == ["Coverage Gap", "Ping Pong HO"]
