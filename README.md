# AI-5G-HandOver-Analytics

Local-first 5G handover intelligence for engineers who need to identify failed,
long-distance, and potentially overshooting source–target relations quickly.


<img width="1680" height="1050" alt="image" src="https://github.com/user-attachments/assets/afe73c05-cb50-4306-8091-c73117f61205" />


> **Privacy:** every file committed under `data/` is simulated. The repository contains no
> production DU identifiers, customer site names, or operational coordinates.

## What it does

- Imports HO KPI and DU-location files from CSV, TXT, XLS, or XLSX.
- Detects source and target relations and aggregates attempts, successes, and failures.
- Calculates source-to-target distance with the Haversine formula.
- Classifies relations into distance bands and highlights long handovers.
- Ranks top failures and high-volume long-distance relations.
- Identifies missing source or target coordinates.
- Provides a local intent-driven assistant for natural-language analysis requests.
- Adds standards-aware XnAP explanations and evidence-based diagnostic guidance.
- Generates interactive OSM HTML maps, KMZ profiles, and formatted Excel reports.
- Runs locally without cloud AI services or paid APIs.

## Repository structure

```text
AI-5G-HandOver-Analytics/
├── data/                         # Synthetic examples only
├── scripts/                      # Repository privacy checks
├── src/ai_ho_analysis/           # Installable application package
│   ├── analysis.py               # Core HO and distance analysis
│   ├── configuration.py          # Analysis thresholds
│   ├── models.py                 # Public result models
│   ├── agent.py                  # Local natural-language assistant
│   ├── kpi_knowledge.py          # HO KPI knowledge base
│   ├── xnap_knowledge.py         # ETSI/3GPP XnAP diagnostic knowledge
│   ├── data_loader.py            # CSV/Excel ingestion
│   ├── exporter.py               # Professional XLSX reports
│   ├── map_analysis.py           # HTML and KMZ map outputs
│   ├── ui.py                     # Tkinter desktop interface
│   └── cli.py                    # Command-line entry point
├── tests/
├── main.py
├── pyproject.toml
└── README.md
```
<img width="1680" height="1050" alt="image" src="https://github.com/user-attachments/assets/51aae3d4-2e83-4747-9489-c7eeb2ad099b" />

## Quick start

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e .
python main.py
```

On macOS, `run_ai_5g_handover_analytics.command` provides the same guided setup.

## Try the included synthetic data

```bash
ai-5g-handover-analytics \
  --ho data/sample_ho_relations.csv \
  --locations data/sample_du_locations.csv \
  --output outputs/sample_report.xlsx
```

The command prints the executive summary and creates a multi-sheet Excel report.

## Standards-aware assistant

The local assistant includes an explainable diagnostic layer based on
[ETSI TS 138 423 V16.9.0 / 3GPP TS 38.423 Release 16](https://www.etsi.org/deliver/etsi_ts/138400_138499/138423/16.09.00_60/ts_138423v160900p.pdf).
It can explain handover preparation, `TXnRELOCprep`, `TXnRELOCoverall`, Handover Cancel,
UE Context Release, Failure Indication, Handover Report types, Mobility Settings Change,
and selected Cause IE families.

Example assistant requests:

```text
explain TXnRELOCprep
explain HO too early vs wrong cell
explain no radio resources in target
standards diagnosis
xnap diagnosis
```

The standards layer is a diagnostic lens. It does not claim that vendor PM counters map
one-to-one to XnAP messages or Cause IE values; engineers should confirm counter semantics
with the applicable vendor documentation and protocol traces.

## Expected input

The HO relation file requires:

```text
DU, SECTOR, CARRIER, TGTDU, TGTSECTOR, TGTCARRIER, Attempts
```

`GNB`, `TGTGNB`, `DUNAME`, success counters, and detailed failure counters are optional but
recommended. The location file supports either:

```text
DU, LAT, LON, SITE_NAME
```

where `DU` is the full gNodeB+DU identifier, or the legacy cell-level mapping format documented
in the application.

## Analysis defaults

| Setting | Default |
|---|---:|
| Review-distance threshold | 5 km |
| Long-handover threshold | 10 km |
| Top relations returned | 50 |

CLI flags can override these thresholds without changing source code.

## Development

```bash
pip install -e ".[dev]"
pytest
python scripts/privacy_check.py
```

See [PRIVACY.md](PRIVACY.md) before adding any dataset. Contributions are welcome under the
terms in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT © 2026 Victor Perez
