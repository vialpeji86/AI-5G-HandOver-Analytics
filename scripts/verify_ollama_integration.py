"""Verify that LocalHOAgent completes a real Ollama tool call."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_ho_analysis.agent import LocalHOAgent  # noqa: E402
from ai_ho_analysis.analysis import HOAnalyzer  # noqa: E402
from ai_ho_analysis.configuration import OllamaConfig  # noqa: E402
from ai_ho_analysis.data_loader import load_table  # noqa: E402
from ai_ho_analysis.schema_inference import infer_ho_schema  # noqa: E402


def main() -> int:
    analyzer = HOAnalyzer()
    analyzer.set_ho_data(load_table(ROOT / "data" / "sample_ho_relations.csv"))
    analyzer.set_map_data(load_table(ROOT / "data" / "sample_du_locations.csv"))
    config = OllamaConfig.from_env()
    agent = LocalHOAgent(analyzer, config)

    reply = agent.handle(
        "Use the lookup_xnap_guidance tool to explain TXnRELOCprep. "
        "Do not answer without calling the tool."
    )
    print(f"Model: {config.model}")
    print(f"Backend: {reply.backend}")
    print(f"Action: {reply.action}")
    print(f"Rows returned: {0 if reply.table is None else len(reply.table)}")
    print(f"Response: {reply.text}")

    if not reply.backend.startswith("ollama:"):
        print(f"Ollama error: {agent.last_ollama_error}", file=sys.stderr)
        return 1
    if reply.action != "xnap_knowledge" or reply.table is None or reply.table.empty:
        print("Ollama responded but did not execute the expected XnAP tool.", file=sys.stderr)
        return 2

    analyzer.run()
    data_reply = agent.handle(
        "Use get_analysis_view with view top_failures and limit 5. "
        "Do not answer without calling the tool."
    )
    print(f"Data backend: {data_reply.backend}")
    print(f"Data action: {data_reply.action}")
    print(f"Data rows returned: {0 if data_reply.table is None else len(data_reply.table)}")
    if not data_reply.backend.startswith("ollama:"):
        print(f"Ollama data-tool error: {agent.last_ollama_error}", file=sys.stderr)
        return 3
    if (
        data_reply.action != "top_failures"
        or data_reply.table is None
        or data_reply.table.empty
    ):
        print("Ollama did not execute the expected analysis-view tool.", file=sys.stderr)
        return 4

    offender_reply = agent.handle(
        "Use get_analysis_view with view source_offenders and limit 5. "
        "Do not answer without calling the tool."
    )
    print(f"Offender backend: {offender_reply.backend}")
    print(f"Offender action: {offender_reply.action}")
    print(f"Offender rows returned: {0 if offender_reply.table is None else len(offender_reply.table)}")
    if not offender_reply.backend.startswith("ollama:"):
        print(f"Ollama offender-tool error: {agent.last_ollama_error}", file=sys.stderr)
        return 5
    if (
        offender_reply.action != "source_offenders"
        or offender_reply.table is None
        or offender_reply.table.empty
        or "Unique_Peers" not in offender_reply.table.columns
    ):
        print("Ollama did not execute the Source-offender view correctly.", file=sys.stderr)
        return 6

    lte_frame = pd.DataFrame(
        {
            "DAY": ["5/15/2023"],
            "SITE": ["SYNTHETIC_LTE_SITE"],
            "ENODEB": [252257],
            "EUTRANCELL": [1],
            "ENODEB_TARGET": [253347],
            "CELL_TARGET": [3],
            "CoverageHole": [0],
            "TooEarlyHoFailure": [40],
            "TooLateHoRlfBeforeTriggering": [13311],
            "TooLateHoRlfAfterTriggering": [630],
            "PingpongHandover": [1193],
        }
    )
    inference = infer_ho_schema(lte_frame)
    analyzer.set_ho_data(lte_frame, inference.mapping)
    analyzer.run()
    lte_reply = agent.handle(
        "Use get_analysis_view with view failure_types and limit 5. "
        "Do not answer without calling the tool."
    )
    print(f"LTE backend: {lte_reply.backend}")
    print(f"LTE action: {lte_reply.action}")
    print(f"LTE rows returned: {0 if lte_reply.table is None else len(lte_reply.table)}")
    if not lte_reply.backend.startswith("ollama:"):
        print(f"Ollama LTE-tool error: {agent.last_ollama_error}", file=sys.stderr)
        return 7
    if (
        lte_reply.action != "failure_types"
        or lte_reply.table is None
        or lte_reply.table.empty
        or lte_reply.table.iloc[0]["Failure_Type"]
        != "TooLateHoRlfBeforeTriggering"
    ):
        print("Ollama did not execute the LTE failure-type view correctly.", file=sys.stderr)
        return 8

    analyzer.set_ho_data(load_table(ROOT / "data" / "sample_ho_relations.csv"))
    analyzer.set_map_data(load_table(ROOT / "data" / "sample_du_locations.csv"))
    analyzer.run()
    chart_reply = agent.handle(
        "Use create_custom_chart with view source_offenders, chart_type horizontal_bar, "
        "metric Total_Failures, and top_n 5. Do not answer without calling the tool."
    )
    print(f"Chart backend: {chart_reply.backend}")
    print(f"Chart action: {chart_reply.action}")
    print(f"Chart rows returned: {0 if chart_reply.table is None else len(chart_reply.table)}")
    if not chart_reply.backend.startswith("ollama:"):
        print(f"Ollama chart-tool error: {agent.last_ollama_error}", file=sys.stderr)
        return 9
    if chart_reply.action != "create_chart" or not chart_reply.visualization:
        print("Ollama did not create the expected chart specification.", file=sys.stderr)
        return 10

    map_reply = agent.handle(
        "Use create_filtered_map with metric Failures, top_n 50, min_distance_km 10, "
        "min_failures 1, and min_attempts 0. Do not answer without calling the tool."
    )
    print(f"Map backend: {map_reply.backend}")
    print(f"Map action: {map_reply.action}")
    print(f"Map rows returned: {0 if map_reply.table is None else len(map_reply.table)}")
    if not map_reply.backend.startswith("ollama:"):
        print(f"Ollama map-tool error: {agent.last_ollama_error}", file=sys.stderr)
        return 11
    if (
        map_reply.action != "create_map"
        or map_reply.table is None
        or map_reply.table.empty
        or not map_reply.visualization
    ):
        print("Ollama did not create the expected filtered map specification.", file=sys.stderr)
        return 12

    print(
        "PASS: Ollama called XnAP/3GPP, analytics, offender, LTE, chart, and map tools successfully."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
