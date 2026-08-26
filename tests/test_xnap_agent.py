import pandas as pd

from ai_ho_analysis.agent import LocalHOAgent
from ai_ho_analysis.analysis import HOAnalyzer
from ai_ho_analysis.configuration import OllamaConfig
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
    reply = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False)).handle(
        "explain TXnRELOCprep"
    )

    assert reply.action == "xnap_knowledge"
    assert reply.table is not None
    assert "TXnRELOCprep" in set(reply.table["Topic"])
    assert MAPPING_CAVEAT in reply.text


def test_xnap_diagnosis_uses_loaded_analysis_result(sample_analyzer) -> None:
    sample_analyzer.run()
    reply = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False)).handle("xnap diagnosis")

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


class FakeOllamaClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_ollama_agent_calls_existing_xnap_tool(sample_analyzer) -> None:
    client = FakeOllamaClient(
        [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "lookup_xnap_guidance",
                                "arguments": {"query": "TXnRELOCprep"},
                            }
                        }
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "TXnRELOCprep protects the preparation phase; validate timer evidence."
                    ),
                }
            },
        ]
    )
    config = OllamaConfig(model="test-tools", max_tool_rounds=3)

    reply = LocalHOAgent(sample_analyzer, config, client).handle("Explain TXnRELOCprep")

    assert reply.backend == "ollama:test-tools"
    assert reply.action == "xnap_knowledge"
    assert reply.table is not None
    assert "TXnRELOCprep" in set(reply.table["Topic"])
    assert len(client.calls) == 2
    assert client.calls[0]["tools"]
    tool_messages = [m for m in client.calls[1]["messages"] if m["role"] == "tool"]
    assert tool_messages
    assert "deterministic application code" in tool_messages[0]["content"]


def test_ollama_failure_falls_back_to_existing_local_logic(sample_analyzer) -> None:
    class FailingClient:
        def chat(self, **_kwargs):
            raise ConnectionError("Ollama is not running")

    reply = LocalHOAgent(
        sample_analyzer,
        OllamaConfig(model="missing-model"),
        FailingClient(),
    ).handle("explain TXnRELOCprep")

    assert reply.backend == "rules-fallback"
    assert reply.action == "xnap_knowledge"
    assert reply.table is not None


def test_ollama_domain_answer_without_tool_call_is_rejected(sample_analyzer) -> None:
    client = FakeOllamaClient(
        [{"message": {"role": "assistant", "content": "Invented XnAP answer"}}]
    )
    agent = LocalHOAgent(
        sample_analyzer,
        OllamaConfig(model="test-tools", max_tool_rounds=1),
        client,
    )

    reply = agent.handle("Explain XnAP TXnRELOCprep")

    assert reply.backend == "rules-fallback"
    assert reply.action == "xnap_knowledge"
    assert "without calling a tool" in (agent.last_ollama_error or "")


def test_compact_model_receives_only_the_relevant_explicit_tool(sample_analyzer) -> None:
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False))

    tools = agent._select_tool_schemas(
        "Use get_analysis_view with view top_failures and limit 5"
    )

    assert [tool["function"]["name"] for tool in tools] == ["get_analysis_view"]


def test_data_tool_returns_table_without_a_second_model_round(sample_analyzer) -> None:
    sample_analyzer.run()
    client = FakeOllamaClient(
        [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_analysis_view",
                                "arguments": {"view": "top_failures", "limit": 5},
                            }
                        }
                    ],
                }
            }
        ]
    )
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(model="test-tools"), client)

    reply = agent.handle("Use get_analysis_view to show top failures")

    assert reply.backend == "ollama:test-tools"
    assert reply.action == "top_failures"
    assert reply.table is not None
    assert len(client.calls) == 1


def test_agent_exposes_source_and_target_offender_views(sample_analyzer) -> None:
    sample_analyzer.run()
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False))

    source_reply = agent.handle("Show source offenders")
    target_reply = agent.handle("Show target offenders")

    assert source_reply.action == "source_offenders"
    assert source_reply.table is not None and not source_reply.table.empty
    assert "Unique_Peers" in source_reply.table.columns
    assert target_reply.action == "target_offenders"
    assert target_reply.table is not None and not target_reply.table.empty


def test_failure_explanation_includes_recommended_checks(sample_analyzer) -> None:
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False))

    reply = agent.handle("What should I check for EndcIntraChgFail_DuTimeout_per_GNB?")

    assert reply.action == "kpi_explain"
    assert reply.table is not None
    assert "Recommended Checks" in reply.table.columns
    assert "DU alarms" in reply.table.iloc[0]["Recommended Checks"]


def test_agent_creates_custom_top_offender_chart_specification(sample_analyzer) -> None:
    sample_analyzer.run()
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False))

    reply = agent.handle("Create a bar graph with the 5 top offenders")

    assert reply.action == "create_chart"
    assert reply.visualization is not None
    assert reply.visualization["kind"] == "chart"
    assert reply.visualization["view"] == "relations"
    assert reply.visualization["top_n"] == 5
    assert reply.table is not None and len(reply.table) == 5
    assert reply.visualization_data is not None
    assert len(reply.visualization_data) > len(reply.table)
    assert "AI observations" in reply.text


def test_generic_offenders_does_not_collapse_to_single_source() -> None:
    frame = pd.DataFrame(
        {
            "Source": ["SOURCE-A"] * 6,
            "Target": [f"TARGET-{index}" for index in range(6)],
            "Failure Count": [60, 50, 40, 30, 20, 10],
        }
    )
    analyzer = HOAnalyzer()
    analyzer.set_ho_data(frame)
    analyzer.run()
    agent = LocalHOAgent(analyzer, OllamaConfig(enabled=False))

    generic = agent.handle("Create a bar graph with the top 5 offenders")
    explicit_source = agent.handle("Create a bar graph with the top 5 Source offenders")

    assert generic.visualization is not None
    assert generic.visualization["view"] == "relations"
    assert generic.table is not None and len(generic.table) == 5
    assert explicit_source.visualization is not None
    assert explicit_source.visualization["view"] == "source_offenders"
    assert explicit_source.table is not None and len(explicit_source.table) == 1
    assert "only 1 distinct Source Offenders" in explicit_source.text


def test_user_chart_parameters_override_inconsistent_ollama_arguments(sample_analyzer) -> None:
    sample_analyzer.run()
    client = FakeOllamaClient(
        [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "create_custom_chart",
                                "arguments": {
                                    "view": "source_offenders",
                                    "chart_type": "horizontal_bar",
                                    "metric": "Total_Failures",
                                    "top_n": 1,
                                },
                            }
                        }
                    ],
                }
            }
        ]
    )
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(model="test-tools"), client)

    reply = agent.handle("Create a bar graph with the top 5 offenders")

    assert reply.backend == "ollama:test-tools"
    assert reply.visualization is not None
    assert reply.visualization["view"] == "relations"
    assert reply.visualization["top_n"] == 5
    assert reply.table is not None and len(reply.table) == 5


def test_agent_creates_failure_map_over_ten_km(sample_analyzer) -> None:
    sample_analyzer.run()
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False))

    reply = agent.handle("Create a map only with fails and distance more than 10 km")

    assert reply.action == "create_map"
    assert reply.visualization is not None
    assert reply.visualization["kind"] == "map"
    assert reply.visualization["min_distance_km"] == 10
    assert reply.visualization["min_failures"] == 1
    assert reply.visualization["min_attempts"] == 0
    assert reply.table is not None and not reply.table.empty
    assert (reply.table["Distance_km"] >= 10).all()
    assert (reply.table["Failures"] >= 1).all()
    assert "Suggested next action" in reply.text


def test_compact_model_gets_only_custom_visualization_tool(sample_analyzer) -> None:
    agent = LocalHOAgent(sample_analyzer, OllamaConfig(enabled=False))

    chart_tools = agent._select_tool_schemas("Create a bar graph with top offenders")
    map_tools = agent._select_tool_schemas("Create a map over 10 km")

    assert [tool["function"]["name"] for tool in chart_tools] == ["create_custom_chart"]
    assert [tool["function"]["name"] for tool in map_tools] == ["create_filtered_map"]
