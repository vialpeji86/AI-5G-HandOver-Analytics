import math

import pandas as pd

from ai_ho_analysis import HOAnalyzer
from ai_ho_analysis.schema_inference import HOSchemaMapping
from ai_ho_analysis.schema_inference import infer_ho_schema


def _summary_value(result, name: str) -> float:
    row = result.summary.loc[result.summary["KPI"] == name, "Value"]
    assert len(row) == 1
    return float(row.iloc[0])


def test_sample_analysis_maps_all_relations(sample_analyzer) -> None:
    result = sample_analyzer.run()

    assert len(result.relation_detail) == 13
    assert _summary_value(result, "Mapped Relations") == 13
    assert math.isclose(_summary_value(result, "Mapped Coverage"), 1.0)
    assert result.missing_target_locations.empty


def test_rates_are_derived_from_aggregated_counters(sample_analyzer) -> None:
    result = sample_analyzer.run()
    row = result.relation_detail.loc[
        (result.relation_detail["Source_GNB"] == 9000001)
        & (result.relation_detail["Target_GNB"] == 9000005)
    ].iloc[0]

    assert row["Attempts"] == 145
    assert row["Success"] == 101
    assert row["Failures"] == 44
    assert math.isclose(row["Fail_Rate"], 44 / 145)


def test_long_handover_output_contains_remote_synthetic_relation(sample_analyzer) -> None:
    result = sample_analyzer.run()

    assert not result.long_relations.empty
    assert (result.long_relations["Distance_km"] > 10).all()
    assert result.long_relations["Source_Site"].str.startswith("SYNTH-").all()
    assert result.long_relations["Target_Site"].str.startswith("SYNTH-").all()


def test_haversine_returns_zero_for_same_point(sample_analyzer) -> None:
    distance = sample_analyzer._haversine_km(
        lat1=[35.1], lon1=[-80.1], lat2=[35.1], lon2=[-80.1]
    )
    assert distance[0] == 0


def test_failure_views_rank_types_and_multi_peer_offenders(sample_analyzer) -> None:
    result = sample_analyzer.run()

    assert not result.failure_types.empty
    assert result.failure_types.iloc[0]["Failure_Type"] == (
        "EndcIntraChgFail_DuTimeout_per_GNB"
    )
    assert result.failure_types["Total_Failures"].sum() == result.relation_detail[
        "Failures"
    ].sum()
    assert {
        "Dominant_Failure_Type",
        "Unique_Peers",
        "Total_Failures",
    }.issubset(result.source_offenders.columns)
    assert not result.target_offenders.empty


def test_generic_source_target_input_runs_without_coordinates() -> None:
    frame = pd.DataFrame(
        {
            "Event Date": ["08/01/2026", "08/02/2026", "08/02/2026"],
            "Serving Node": ["SRC-A", "SRC-A", "SRC-B"],
            "Neighbor Node": ["TGT-1", "TGT-2", "TGT-1"],
            "HO Attempts": [20, 10, 8],
            "DU Timeout Failures": [3, 2, 1],
            "RRC Error Count": [1, 0, 2],
        }
    )
    mapping = HOSchemaMapping(
        source="Serving Node",
        target="Neighbor Node",
        attempts="HO Attempts",
        date="Event Date",
        failure_columns=["DU Timeout Failures", "RRC Error Count"],
    )
    analyzer = HOAnalyzer()
    analyzer.set_ho_data(frame, mapping)

    result = analyzer.run()

    assert len(result.relation_detail) == 3
    assert result.relation_detail["Failures"].sum() == 9
    source_a = result.source_offenders.loc[
        result.source_offenders["Source_ID"] == "SRC-A"
    ].iloc[0]
    assert source_a["Unique_Peers"] == 2
    assert source_a["Total_Failures"] == 6
    assert len(result.failure_types) == 2
    assert result.relation_detail["Distance_km"].isna().all()


def test_full_vendor_header_format_keeps_precise_dimensions_without_map() -> None:
    failure_columns = [
        "EndcIntraChgPrepFail_UpTimeout",
        "EndcIntraChgFail_CpFail_per_GNB",
        "EndcIntraChgFail_DuFail_per_GNB",
        "EndcIntraChgFail_DuTimeout_per_GNB",
        "EndcIntraChgFail_MenbFail_per_GNB",
        "EndcIntraChgFail_RrcTo_per_GNB",
        "EndcIntraChgFail_Tdcoverall_per_GNB",
        "EndcIntraChgFail_UpFail_per_GNB",
        "EndcIntraChgPrepFail_CpFail_per_GNB",
        "EndcIntraChgPrepFail_DuFail_per_GNB",
        "EndcIntraChgPrepFail_DuTimeout",
        "EndcIntraChgPrepFail_MenbFail_per_GNB",
        "EndcIntraChgPrepFail_UpFail_per_GNB",
    ]
    values = {
        "DAY": ["08/20/2026"],
        "GNB": [2419283],
        "DUNAME": ["SOURCE-A"],
        "DU": [3325],
        "SECTOR": [1],
        "CARRIER": [77],
        "TGTGNB": [2419284],
        "TGTDU": [3326],
        "TGTSECTOR": [2],
        "TGTCARRIER": [78],
        "EndcIntraChgAtt_per_GNB": [100],
        "EndcIntraChgPrepSucc_per_GNB": [93],
        "EndcIntraChgSucc_per_GNB": [90],
    }
    values.update({column: [index + 1] for index, column in enumerate(failure_columns)})
    frame = pd.DataFrame(values)
    mapping = infer_ho_schema(frame).mapping
    analyzer = HOAnalyzer()
    analyzer.set_ho_data(frame, mapping)

    result = analyzer.run()
    row = result.relation_detail.iloc[0]

    assert row["Source_ID"] == "2419283|3325"
    assert row["Target_ID"] == "2419284|3326"
    assert row["Source_Sector"] == 1
    assert row["Target_Carrier"] == 78
    assert row["Observed_Days"] == 1
    assert len(result.failure_types) == len(failure_columns)


def test_lte_mro_format_is_inferred_as_composite_source_target_and_failure_types() -> None:
    frame = pd.DataFrame(
        {
            "DAY": ["5/15/2023"],
            "SITE": ["LITHOPOLIS_DT"],
            "ENODEB": [252257],
            "EUTRANCELL": [1],
            "CARRIER": [1],
            "NEIGHBORCELL": [64856835],
            "ENODEB_TARGET": [253347],
            "CELL_TARGET": [3],
            "CoverageHole": [0],
            "TooEarlyHoFailure": [40],
            "TooLateHoRlfBeforeTriggering": [13311],
            "TooLateHoRlfAfterTriggering": [630],
            "PingpongHandover": [1193],
        }
    )
    inference = infer_ho_schema(frame)
    analyzer = HOAnalyzer()
    analyzer.set_ho_data(frame, inference.mapping)

    result = analyzer.run()
    row = result.relation_detail.iloc[0]

    assert inference.needs_review is False
    assert inference.mapping.source == "ENODEB"
    assert inference.mapping.source_cell == "EUTRANCELL"
    assert inference.mapping.target == "ENODEB_TARGET"
    assert inference.mapping.target_cell == "CELL_TARGET"
    assert set(inference.mapping.failure_columns) == {
        "CoverageHole",
        "TooEarlyHoFailure",
        "TooLateHoRlfBeforeTriggering",
        "TooLateHoRlfAfterTriggering",
        "PingpongHandover",
    }
    assert row["Source_ID"] == "252257|1"
    assert row["Target_ID"] == "253347|3"
    assert row["Source_Site"] == "LITHOPOLIS_DT"
    assert row["Failures"] == 15174
    assert result.failure_types.iloc[0]["Failure_Type"] == (
        "TooLateHoRlfBeforeTriggering"
    )
