"""Installation and diagnostics for the portable harness."""

from pathlib import Path
import tomllib

with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as _metadata:
    __version__ = tomllib.load(_metadata)["project"]["version"]
