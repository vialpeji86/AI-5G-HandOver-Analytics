import math


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
