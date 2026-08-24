from ai_ho_analysis.agent import LocalHOAgent
from ai_ho_analysis.xnap_knowledge import (
    MAPPING_CAVEAT,
    find_xnap_knowledge,
    kpi_protocol_lens,
)


def test_timer_query_returns_preparation_timer() -> None:
    concepts, causes = find_xnap_knowledge("explain TXnRELOCprep")

    assert [concept.name for concept in concepts] == ["TXnRELOCprep"]
    assert any(cause.cause == "TXnRELOCprep Expiry" for cause in causes)


def test_handover_report_query_returns_mobility_robustness_guidance() -> None:
    concepts, _ = find_xnap_knowledge("HO too early vs wrong cell")

    assert [concept.name for concept in concepts] == ["Handover Report"]


def test_kpi_stage_is_mapped_to_an_explainable_protocol_lens() -> None:
    lens, reference = kpi_protocol_lens("Preparation")

    assert "admission" in lens.lower()
    assert "8.2.1" in reference


def test_agent_can_explain_xnap_without_running_analysis(sample_analyzer) -> None:
    reply = LocalHOAgent(sample_analyzer).handle("explain TXnRELOCprep")

    assert reply.action == "xnap_knowledge"
    assert reply.table is not None
    assert "TXnRELOCprep" in set(reply.table["Topic"])
    assert MAPPING_CAVEAT in reply.text


def test_xnap_diagnosis_uses_loaded_analysis_result(sample_analyzer) -> None:
    sample_analyzer.run()
    reply = LocalHOAgent(sample_analyzer).handle("xnap diagnosis")

    assert reply.action == "standards_diagnosis"
    assert reply.table is not None
    assert not reply.table.empty
    assert {
        "Priority",
        "Signal",
        "Stage",
        "Standards-aware interpretation",
        "Recommended validation",
        "Reference",
    }.issubset(reply.table.columns)
    assert reply.table["Signal"].str.contains("failure|timeout|distance", case=False).any()
