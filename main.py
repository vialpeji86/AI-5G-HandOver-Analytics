from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_ho_analysis.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
