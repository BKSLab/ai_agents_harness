"""Guard delivered representations, process budgets and persisted diagnostics."""

import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from harness_cli import artifacts, tasks
from harness_cli.redaction import redact_credentials


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", timeout=20, check=True)
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Artifact Fixture")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "fixture@example.invalid")
    root = tmp_path / "project with spaces"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "commit.gpgsign", "false")
    (root / "app.py").write_bytes(b"VALUE = 1\n")
    git(root, "add", "app.py")
    git(root, "commit", "-m", "Synthetic artifact baseline")
    return root


def start_task(root):
    tasks.init("artifacts", root, "Verify the delivered fixture representation", mode="light")
    tasks.set_plan("artifacts", root, {
        "schema_version": 1,
        "scope": ["."],
        "acceptance": [{"id": "AC1", "description": "The fixture contains the approved value.", "checks": ["C1"]}],
        "risks": [],
        "checks": [{"id": "C1", "argv": ["{python}", "-c",
                    "from pathlib import Path; assert Path('app.py').read_text(encoding='utf-8') == 'VALUE = 2\\n'"]}],
    })
    tasks.approve("artifacts", root, "Synthetic test owner approved the plan")
    (root / "app.py").write_bytes(b"VALUE = 2\n")


@pytest.mark.parametrize("attribute", ["filter=fixture", "filter=unset", "filter=unspecified", "working-tree-encoding=UTF-16", "ident"])
def test_content_rewriting_attributes_block_gate_and_snapshot_without_running_filter(repository, tmp_path, attribute):
    start_task(repository)
    git(repository, "add", "app.py")
    marker = tmp_path / "filter-executed"
    script = tmp_path / "synthetic clean filter.py"
    script.write_text(
        "from pathlib import Path\nimport sys\n"
        "data = sys.stdin.buffer.read()\n"
        "Path(sys.argv[1]).write_text('executed', encoding='utf-8')\n"
        "sys.stdout.buffer.write(data.replace(b'VALUE = 2', b'VALUE = 999'))\n",
        encoding="utf-8",
    )
    # Verify the fixture transformation explicitly, then detect any implicit Git invocation.
    direct = subprocess.run([sys.executable, str(script), str(marker)], input=b"VALUE = 2\n",
                            capture_output=True, timeout=10, check=True)
    assert direct.stdout == b"VALUE = 999\n"
    marker.unlink()
    command = shlex.join([Path(sys.executable).as_posix(), script.as_posix(), marker.as_posix()])
    (repository / ".gitattributes").write_text(f"app.py {attribute}\n", encoding="utf-8")
    git(repository, "add", ".gitattributes")
    # Git add may refresh other entries: enable the filter only after fixture staging.
    git(repository, "config", "filter.fixture.clean", command)
    git(repository, "config", "filter.unset.clean", command)
    git(repository, "config", "filter.unspecified.clean", command)
    assert not marker.exists()
    manifest = artifacts.inventory(repository)
    with pytest.raises(ValueError, match="does not support"):
        artifacts.supported_git_attributes(repository, manifest)
    with pytest.raises(ValueError, match="does not support"):
        artifacts.git_inventory(repository, manifest)
    assert tasks.verify("artifacts", repository)["ok"]
    tasks.authorize("artifacts", repository, "commit", "main", "Synthetic exact commit permission")
    gate = tasks.git_gate(repository, "commit")
    assert not gate["allowed"] and gate["reason"] == "task_evidence_unavailable"
    with pytest.raises(ValueError, match="does not support"):
        tasks.snapshot("artifacts", repository)
    assert not marker.exists(), "A guard must reject transformations before Git can execute a clean filter."


def test_eol_attributes_and_explicitly_disabled_transformations_remain_supported(repository):
    (repository / ".gitattributes").write_bytes(b"*.py text eol=lf -filter -ident -working-tree-encoding\n")
    (repository / "app.py").write_bytes(b"VALUE = 2\r\n")
    git(repository, "add", "--all")
    manifest = artifacts.inventory(repository)
    artifacts.supported_git_attributes(repository, manifest)
    assert artifacts.git_inventory(repository, manifest) == artifacts.index_tree(repository)


def test_snapshot_checks_its_own_attributes_before_staging(repository, tmp_path):
    start_task(repository)
    (repository / ".gitattributes").write_bytes(b"app.py filter=fixture\n")
    (repository / ".git" / "info" / "attributes").write_bytes(b"app.py -filter\n")
    git(repository, "add", "--all")
    marker = tmp_path / "snapshot-filter-executed"
    script = tmp_path / "filter.py"
    script.write_text("from pathlib import Path\nimport sys\n"
                      "Path(sys.argv[1]).write_text('executed')\n"
                      "sys.stdout.buffer.write(sys.stdin.buffer.read())\n", encoding="utf-8")
    command = shlex.join([Path(sys.executable).as_posix(), script.as_posix(), marker.as_posix()])
    # --global is confined by the fixture's private GIT_CONFIG_GLOBAL.
    git(repository, "config", "--global", "filter.fixture.clean", command)
    artifacts.supported_git_attributes(repository, artifacts.inventory(repository))
    with pytest.raises(ValueError, match="does not support"):
        tasks.snapshot("artifacts", repository)
    assert not marker.exists()
    assert tasks.Store(repository).load("artifacts")["snapshots"] == {}


@pytest.mark.parametrize("file_count", [1, 801])
def test_canonical_hashing_uses_one_git_process_independent_of_file_count(repository, monkeypatch, file_count):
    for number in range(file_count - 1):
        (repository / f"fixture-{number:04d}.txt").write_bytes(f"fixture {number}\n".encode())
    git(repository, "add", "--all")
    manifest = artifacts.inventory(repository)
    assert len(manifest) == file_count
    original_run = subprocess.run
    hash_calls = []

    def capture_hash_commands(argv, **kwargs):
        if argv[:2] == ["git", "hash-object"]:
            hash_calls.append((argv, kwargs))
        return original_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", capture_hash_commands)
    canonical = artifacts.git_inventory(repository, manifest)
    assert canonical == artifacts.index_tree(repository)
    assert len(hash_calls) == 1
    assert hash_calls[0][0] == ["git", "hash-object", "--stdin-paths"]
    assert 0 < hash_calls[0][1]["timeout"] <= 5


def test_batched_git_gate_still_rejects_an_unreviewed_index(repository, monkeypatch):
    start_task(repository)
    (repository / "app.py").write_bytes(b"VALUE = 999\n")
    git(repository, "add", "app.py")
    (repository / "app.py").write_bytes(b"VALUE = 2\n")
    assert tasks.verify("artifacts", repository)["ok"]
    tasks.authorize("artifacts", repository, "commit", "main", "Synthetic exact commit permission")
    original_run = subprocess.run
    hash_calls = []

    def capture_hash_commands(argv, **kwargs):
        if argv[:2] == ["git", "hash-object"]:
            hash_calls.append(argv)
        return original_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", capture_hash_commands)
    result = tasks.git_gate(repository, "commit")
    assert not result["allowed"]
    assert result["reason"] == "git_inputs_differ_from_verified_files"
    assert len(hash_calls) == 1


def test_expired_internal_git_gate_budget_denies_and_restores_context(repository, monkeypatch):
    start_task(repository)
    assert tasks.verify("artifacts", repository)["ok"]
    tasks.authorize("artifacts", repository, "commit", "main", "Synthetic exact commit permission")
    git(repository, "add", "app.py")
    original_context = artifacts.GIT_DEADLINE.get()
    clock_calls = 0

    def advance_past_budget():
        nonlocal clock_calls
        clock_calls += 1
        return 100.0 if clock_calls == 1 else 107.0

    monkeypatch.setattr(tasks.time, "monotonic", advance_past_budget)
    result = tasks.git_gate(repository, "commit")
    assert not result["allowed"] and result["reason"] == "task_evidence_unavailable"
    assert artifacts.GIT_DEADLINE.get() == original_context


def test_process_receipt_masks_database_url_from_environment(tmp_path, monkeypatch):
    value = "postgresql://fixture_user:fixture_password@database.example.invalid:5432/app"
    monkeypatch.setenv("DATABASE_URL", value)
    path = tmp_path / "database-receipt.json"
    result = artifacts.run_command([sys.executable, "-c", "import os; print(os.environ['DATABASE_URL'])"],
                                   tmp_path, 5, path)
    assert result["status"] == "passed"
    output = path.read_text(encoding="utf-8")
    assert value not in output and "fixture_password" not in output and "fixture_user" not in output
    assert json.loads(output)["stdout"].strip() == "[REDACTED]"


def test_process_receipt_masks_generic_postgres_credentials_without_matching_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    value = "postgres://other_fixture_user:encoded%40password@db.example.invalid/app"
    path = tmp_path / "generic-receipt.json"
    result = artifacts.run_command([sys.executable, "-c", f"print({value!r})"], tmp_path, 5, path)
    assert result["status"] == "passed"
    output = path.read_text(encoding="utf-8")
    assert "other_fixture_user" not in output and "encoded%40password" not in output
    assert json.loads(output)["stdout"].strip() == "postgres://[REDACTED]@db.example.invalid/app"


def test_hook_diagnostics_share_database_credential_masking(monkeypatch, capsys):
    from hooks import _common
    value = "postgresql://fixture_user:fixture_password@database.example.invalid/app"
    monkeypatch.setenv("DATABASE_URL", value)
    assert _common.redact is redact_credentials
    _common.emit("fixture", "error", "synthetic_diagnostic", details={"database": value,
                 "logs": ["postgres://other_user:other_password@db.example.invalid/app"]})
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["details"]["database"] == "[REDACTED]"
    assert report["details"]["logs"] == ["postgres://[REDACTED]@db.example.invalid/app"]
    assert "fixture_password" not in captured.out and "other_password" not in captured.out
