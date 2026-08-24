"""Command-line interface for AI-5G-HandOver-Analytics."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .analysis import HOAnalyzer
from .configuration import AnalysisConfig
from .data_loader import load_table
from .exporter import export_professional_xlsx


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-5g-handover-analytics",
        description="Analyze 5G handover relations locally from KPI and DU-location files.",
    )
    parser.add_argument("--ho", type=Path, help="HO KPI input (.csv, .txt, .xls, .xlsx)")
    parser.add_argument("--locations", type=Path, help="DU location input")
    parser.add_argument("--output", type=Path, default=Path("outputs/ai_ho_report.xlsx"))
    parser.add_argument("--long-distance-km", type=float, default=10.0)
    parser.add_argument("--review-distance-km", type=float, default=5.0)
    parser.add_argument("--top", type=int, default=50, help="Maximum top relations")
    parser.add_argument("--gui", action="store_true", help="Launch the desktop interface")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gui or (args.ho is None and args.locations is None):
        from .ui import run_app

        run_app()
        return 0
    if args.ho is None or args.locations is None:
        raise SystemExit("--ho and --locations are required for command-line analysis")

    config = AnalysisConfig(
        long_handover_km=args.long_distance_km,
        review_handover_km=args.review_distance_km,
        top_relations=args.top,
    )
    analyzer = HOAnalyzer(config)
    analyzer.set_ho_data(load_table(args.ho))
    analyzer.set_map_data(load_table(args.locations))
    result = analyzer.run()
    output = export_professional_xlsx(analyzer.export_payload(), args.output)

    print(result.summary.to_string(index=False))
    print(f"\nReport created: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
