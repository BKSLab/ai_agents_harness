"""CLI entry point; shared runtime is installed with the skill bundle."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from bitrix_cli import main

if __name__ == "__main__":
    raise SystemExit(main("get-messages"))
