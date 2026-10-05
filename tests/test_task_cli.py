"""Exercise CLI contracts and the real hook boundary without executing delivery."""

import json
import os
from pathlib import Path
import subprocess
import sys

from harness_cli import tasks
from harness_cli.install import ROOT
from harness_cli.artifacts import run_command


def run(root, *args, input=None):
    return subprocess.run(args, cwd=root, input=input, capture_output=True, text=True,
                          encoding="utf-8", errors="strict", timeout=30)


def test_managed_cli_blocks_unverified_commit_and_can_resume_released_context(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_bytes(b"VALUE = 1\n")
    for args in (("init", "--initial-branch=main"), ("add", "app.py"),
                 ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-m", "Synthetic baseline")):
        assert run(root, "git", *args).returncode == 0

    def cli(*args, success=True):
        process = run(ROOT, sys.executable, str(ROOT / "manage.py"), "task", *args, "--project", str(root))
        assert process.returncode == (0 if success else 1), process.stdout
        return json.loads(process.stdout)

    assert cli("init", "cli", "--title", "Synthetic change", "--mode", "light")["stage"] == "planning"
    plan = {"schema_version": 1, "scope": ["app.py"], "acceptance": [
        {"id": "AC1", "description": "Use value two", "checks": ["C1"]}], "risks": [], "checks": [
        {"id": "C1", "argv": ["{python}", "-c", "from pathlib import Path; assert '2' in Path('app.py').read_text()"]}]}
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    cli("plan", "cli", "--input", str(plan_file))
    cli("verify", "cli", success=False)
    cli("approve", "cli", "--reference", "Fixture owner approved")
    cli("verify", "cli", success=False)

    payload = json.dumps({"tool_name": "Bash", "cwd": str(root),
                          "tool_input": {"command": 'git commit -m "Synthetic change"'}})
    hook = ROOT / "hooks" / "git_gate.py"
    assert run(root, sys.executable, str(hook), input=payload).returncode == 2
    (root / "app.py").write_bytes(b"VALUE = 2\n")
    assert cli("verify", "cli")["status"] == "passed"
    cli("authorize", "cli", "--action", "commit", "--target", "main", "--reference", "Fixture owner approved commit")
    assert run(root, sys.executable, str(hook), input=payload).returncode == 2  # Different index.
    assert run(root, "git", "add", "app.py").returncode == 0
    assert run(root, sys.executable, str(hook), input=payload).returncode == 0
    assert run(root, "git", "log", "-1", "--format=%s").stdout.strip() == "Synthetic baseline"

    report = cli("release", "cli", "--reference", "Fixture context no longer active")
    assert report["active_task"] is None and not report["delivery_claimed"]
    assert cli("use", "cli")["ready"]
    assert tasks.Store(root).active() == "cli"
    checkpoint = Path(cli("status", "cli")["state_directory"]) / "checkpoint.json"
    assert checkpoint.is_file() and not checkpoint.is_relative_to(root)
    assert os.environ["HARNESS_HOME"] in str(checkpoint)


def test_model_attempt_exhaustion_visible_in_status_without_forging_review(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "project"
    root.mkdir()
    for args in (("init", "--initial-branch=main"),
                 ("-c", "core.hooksPath=" + str(tmp_path / "no-hooks"), "-c", "commit.gpgsign=false",
                  "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "--allow-empty", "-m", "Synthetic baseline")):
        assert run(root, "git", *args).returncode == 0
    tasks.init("attempts", root, "Fixture")
    plan = {"schema_version": 1, "scope": ["."], "risks": [],
            "acceptance": [{"id": "A", "description": "Smoke", "checks": ["C"]}],
            "checks": [{"id": "C", "argv": ["{python}", "-c", "print('smoke')"]}]}
    tasks.set_plan("attempts", root, plan)
    tasks.approve("attempts", root, "Fixture owner approved")
    assert tasks.verify("attempts", root)["ok"]
    store = tasks.Store(root)
    state = store.load("attempts")
    state["review_gate_attempts"] = {state["plan_hash"]: 3}
    store.save(state, "fixture_budget_exhausted")
    report = tasks.status("attempts", root)
    assert report["stage"] == "blocked" and report["model_review_attempts"] == 3
    assert "model_review_attempt_limit" in report["blockers"]


def test_excessive_process_output_is_an_error_with_only_a_bounded_receipt(tmp_path):
    log = tmp_path / "output.json"
    report = run_command([sys.executable, "-c", "print('x' * 2100000)"], tmp_path, 10, log)
    assert report["status"] == "error" and report["reason"] == "output_limit"
    captured = json.loads(log.read_text(encoding="utf-8"))
    assert captured["stdout_truncated"] is True and len(captured["stdout"]) <= 32768
