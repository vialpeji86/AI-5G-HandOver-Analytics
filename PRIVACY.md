# Data Privacy

AI-5G-HandOver-Analytics is local-first. Input KPI files, DU identifiers, coordinates, and generated
reports are processed on the user's computer and are not transmitted by the application.

## Repository data policy

- Only files explicitly named `data/sample_*.csv` may be committed as examples.
- Every included sample row uses synthetic `900000x` identifiers and `SYNTH-*` site names.
- Production exports, maps, workbooks, databases, and the root `DU_Locations.csv` are ignored.
- Generated output belongs in `outputs/`, which is ignored by Git.
- Before every public release, run `python scripts/privacy_check.py`.

Never commit customer names, internal site identifiers, exact production coordinates,
network topology exports, credentials, or generated reports based on production inputs.
