"""Fail when publishable sample files appear to contain non-synthetic identifiers."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def check_locations(path: Path) -> list[str]:
    problems: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            if row.get("DATA_CLASSIFICATION") != "SYNTHETIC":
                problems.append(f"{path}:{line}: missing SYNTHETIC classification")
            if not row.get("SITE_NAME", "").startswith("SYNTH-"):
                problems.append(f"{path}:{line}: non-synthetic site name")
            if not row.get("DU", "").startswith("900000"):
                problems.append(f"{path}:{line}: DU outside reserved sample range")
    return problems


def check_relations(path: Path) -> list[str]:
    problems: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            if row.get("DATA_CLASSIFICATION") != "SYNTHETIC":
                problems.append(f"{path}:{line}: missing SYNTHETIC classification")
            if not row.get("DUNAME", "").startswith("SYNTH-"):
                problems.append(f"{path}:{line}: non-synthetic site name")
            for field in ("GNB", "TGTGNB"):
                if not row.get(field, "").startswith("900000"):
                    problems.append(f"{path}:{line}: {field} outside reserved sample range")
    return problems


def main() -> int:
    problems = check_locations(ROOT / "data" / "sample_du_locations.csv")
    problems += check_relations(ROOT / "data" / "sample_ho_relations.csv")
    if problems:
        print("Privacy check failed:")
        print("\n".join(f"- {item}" for item in problems))
        return 1
    print("Privacy check passed: all publishable sample rows are explicitly synthetic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
