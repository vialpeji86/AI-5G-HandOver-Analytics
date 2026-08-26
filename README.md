# AI-5G-HandOver-Analytics

Local-first 5G handover intelligence for engineers who need to identify failed,
long-distance, and potentially overshooting source–target relations quickly.


<img width="1680" height="1050" alt="image" src="https://github.com/user-attachments/assets/afe73c05-cb50-4306-8091-c73117f61205" />


> **Privacy:** every file committed under `data/` is simulated. The repository contains no
> production DU identifiers, customer site names, or operational coordinates.

## What it does

- Imports HO KPI and DU-location files from CSV, TXT, XLS, or XLSX.
- Infers Source, Target, attempts, success, date, cell/site identifiers, and multiple failure
  counters from heterogeneous vendor headers.
- Provides a manual column-mapping dialog whenever automatic matching is ambiguous.
- Detects source and target relations and aggregates attempts, successes, and failures.
- Calculates source-to-target distance with the Haversine formula.
- Classifies relations into distance bands and highlights long handovers.
- Ranks top failures and high-volume long-distance relations.
- Ranks failure types, Source offenders affecting many Targets, and Target offenders affecting
  many Sources, with relation-level drill-down.
- Includes a customizable professional Failure Dashboard with ranked horizontal bars, failure-mix
  donut chart, KPI cards, Top-N selection, metric selection, and exportable dashboard tables.
- Identifies missing source or target coordinates.
- Provides a local Ollama assistant with tool calling for natural-language analysis requests.
- Adds standards-aware XnAP explanations and evidence-based diagnostic guidance.
- Generates interactive OSM HTML maps, KMZ profiles, and formatted Excel reports.
- Runs locally without cloud AI services or paid APIs; Ollama is optional at runtime because the
  deterministic assistant remains available as an automatic fallback.

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
ollama pull llama3.2:3b
python main.py
```

On macOS, `run_ai_5g_handover_analytics.command` provides the same guided setup.
Start the Ollama application/service before opening the analytics app. The interface reports the
active backend after each request.

## Try the included synthetic data

```bash
ai-5g-handover-analytics \
  --ho data/sample_ho_relations.csv \
  --locations data/sample_du_locations.csv \
  --output outputs/sample_report.xlsx
```

The command prints the executive summary and creates a multi-sheet Excel report.

## Standards-aware assistant

`LocalHOAgent` uses Ollama (`llama3.2:3b` by default) to select local tools. The tools execute the
existing pandas analysis, KPI catalog, and XnAP/3GPP knowledge functions; the model does not
replace those calculations. Tool results are returned to Ollama for a concise engineering
explanation, while the complete deterministic DataFrame is shown in the interface.

Available tool families include:

- Run the handover analysis.
- Retrieve executive, failure, distance, long-HO, and missing-location views.
- Retrieve failure-type, detailed-failure, Source-offender, and Target-offender views.
- Filter relations by site, carrier, distance, attempts, failures, or failure rate.
- Look up KPI definitions and formulas.
- Retrieve XnAP guidance and build evidence-based standards diagnostics.

If the Python client, Ollama service, or requested model is unavailable, the same request is routed
through the previous local intent engine automatically. No operational file is uploaded.

The standards layer includes an explainable diagnostic lens based on
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
show failure types
show source offenders
show target offenders
show failure detail for source 2419283|3325
what should I check for EndcIntraChgFail_DuTimeout_per_GNB?
create a bar graph with the 5 top Source offenders
create a donut chart of failure types
create a map only with failures and distance more than 10 km
create a map with attempts more than 100 ranked by distance
```

Visualization requests are executable assistant actions, not image-only answers. Chart requests
open an interactive window where the chart type, label, metric, and Top N remain editable. Map
requests generate a filtered Source-to-Target OSM HTML view using minimum distance, failures, and
attempts thresholds plus the requested ranking metric.

For analytical tables, charts, and maps, the assistant also adds computed observations such as
dominant-failure share, top-offender concentration, multi-peer exposure, geographic coverage
limitations, and a recommended next engineering check. These comments are derived from the local
analysis output rather than from model memory.

The standards layer is a diagnostic lens. It does not claim that vendor PM counters map
one-to-one to XnAP messages or Cause IE values; engineers should confirm counter semantics
with the applicable vendor documentation and protocol traces.

### Ollama configuration

The defaults work with a local Ollama installation. Override them when needed:

```bash
export AI_HO_OLLAMA_MODEL="llama3.2:3b"
export AI_HO_OLLAMA_HOST="http://127.0.0.1:11434"
export AI_HO_OLLAMA_TIMEOUT="90"
export AI_HO_OLLAMA_MAX_TOOL_ROUNDS="4"
export AI_HO_OLLAMA_ENABLED="1"
python main.py
```

Set `AI_HO_OLLAMA_ENABLED=0` to use only the deterministic local intent engine.

Verify the complete local model → tool → XnAP result loop with:

```bash
python scripts/verify_ollama_integration.py
```

The command exits successfully only when the response reports an `ollama:` backend and returns
the deterministic `xnap_knowledge` table.

## Flexible input and manual mapping

The importer accepts `.csv`, `.txt`, `.tsv`, `.xls`, `.xlsx`, and `.xlsm`, detects common
delimiters/encodings, and selects the most likely populated Excel sheet. An HO file needs only:

```text
Source identifier, Target identifier, one or more numeric failure counters
```

Attempts, success, date/period, Source/Target site, and Source/Target cell identifiers are optional.
The existing detailed format (`DU`, `SECTOR`, `CARRIER`, `TGTDU`, `TGTSECTOR`, `TGTCARRIER`)
continues to work and retains its detailed relation dimensions.

If the detected mapping is incomplete or ambiguous, select the HO file and click
**Map Columns...**. Confirm Source and Target, choose optional metadata, and select every failure
counter in the multi-select list.

LTE MRO layouts are recognized using approximate header matching. For example, variants of
`ENODEB + EUTRANCELL` are combined as the Source, variants of
`ENODEB_TARGET + CELL_TARGET` are combined as the Target, and counters containing concepts such
as coverage hole, too early, too late/RLF, ping-pong, failure, timeout, reject, drop, or error are
classified as failure types.

Coordinates are optional for failure/offender analysis. Without them, distance columns remain
empty while failure classifications and rankings still run. A location file can use:

```text
DU, LAT, LON, SITE_NAME
```

where `DU` is the full gNodeB+DU identifier, or the legacy cell-level mapping format documented
in the application.

After running analysis, click **Failure Dashboard** to switch among Failure Types, Source
Offenders, and Target Offenders. Choose the ranking metric and Top N, then export the active view
to Excel or CSV.

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
