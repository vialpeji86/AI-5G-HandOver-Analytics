# Contributing

1. Create a virtual environment and install `pip install -e ".[dev]"`.
2. Keep analysis logic independent from the Tkinter interface.
3. Add or update tests for every behavioral change.
4. Use only synthetic fixtures with `SYNTH-*` names and `900000x` gNodeB IDs.
5. Run `pytest` and `python scripts/privacy_check.py` before opening a pull request.

Please keep pull requests focused and document any new input columns or thresholds.
