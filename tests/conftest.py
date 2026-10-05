from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "_shared"))


@pytest.fixture(autouse=True)
def private_environment(monkeypatch, tmp_path):
    import os
    for key in list(os.environ):
        if key.startswith(("BITRIX_", "GITLAB_")) or key in ("KIMI_CODE_HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("HARNESS_HOME", str(tmp_path / "state"))


@pytest.fixture
def config():
    from bitrix_config import Config
    return Config("https://portal.example.invalid", 11, "fixture-token", read_retries=0)
