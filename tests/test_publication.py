from pathlib import Path
import subprocess

import pytest

from harness_cli.publication import export_public


def test_export_has_no_original_history_or_ignored_local_files(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", str(source)], capture_output=True, check=True)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Fixture")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Fixture")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "fixture@example.invalid")
    (source / "skills/example").mkdir(parents=True)
    (source / "skills/example/SKILL.md").write_text('---\nname: example\ndescription: Example\n---\nBody\n', encoding="utf-8")
    (source / ".gitignore").write_text(".env\n", encoding="utf-8")
    (source / "README.md").write_text("initial content", encoding="utf-8")
    subprocess.run(["git", "add", "--all"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "original"], cwd=source, check=True, capture_output=True)
    original = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    (source / "README.md").write_text("public content", encoding="utf-8")
    (source / ".env").write_text("local-only", encoding="utf-8")
    target = tmp_path / "export"
    result = export_public(target, source)
    assert result["ok"] and not result["published"]
    assert not (target / ".env").exists()
    assert (target / "README.md").read_text() == "public content"
    assert subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=target).strip() == b"1"
    assert subprocess.run(["git", "cat-file", "-e", original], cwd=target, capture_output=True).returncode != 0
    assert subprocess.check_output(["git", "log", "-1", "--format=%ae"], cwd=target).strip() == b"noreply@users.noreply.github.com"


def test_export_refuses_existing_destination(tmp_path):
    with pytest.raises(ValueError, match="new directory"):
        export_public(tmp_path, Path(__file__).resolve().parents[1])
