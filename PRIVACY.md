# Data Privacy

AI-5G-HandOver-Analytics is local-first. Input KPI files, DU identifiers, coordinates, and generated
reports are processed on the user's computer. By default, AI requests go only to Ollama at
`127.0.0.1`; the application sends the user's prompt and bounded tool-result rows to that local
service, never the original input files. If `AI_HO_OLLAMA_HOST` is changed to a remote address,
those prompts and tool results will be transmitted to the configured host. Keep the default local
host for production network data.

## Repository data policy

- Only files explicitly named `data/sample_*.csv` may be committed as examples.
- Every included sample row uses synthetic `900000x` identifiers and `SYNTH-*` site names.
- Production exports, maps, workbooks, databases, and the root `DU_Locations.csv` are ignored.
- Generated output belongs in `outputs/`, which is ignored by Git.
- Before every public release, run `python scripts/privacy_check.py`.

Never commit customer names, internal site identifiers, exact production coordinates,
network topology exports, credentials, or generated reports based on production inputs.
