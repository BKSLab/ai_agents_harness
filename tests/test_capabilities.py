import json
from pathlib import Path
import subprocess

import pytest
import tomlkit

from harness_cli.capabilities import capabilities, probe_hooks
from harness_cli.install import install, receipt_path


@pytest.fixture
def feature_source(tmp_path):
    source = tmp_path / "source with spaces"
    files = {
        "skills/example/SKILL.md": "---\nname: example\ndescription: Example.\n---\nBody.\n",
        "global/AGENTS.md": "# Shared rules\nKeep evidence current.\n",
        "agents/reviewer.md": "---\nname: reviewer\ndescription: Review.\ntools: [Read]\n---\nReview.\n",
        "pyproject.toml": '[project]\nname="example-harness"\nversion="0.4.0"\n',
    }
    for name in ("protect_secrets", "lint_on_edit", "git_gate", "_common"):
        files[f"hooks/{name}.py"] = "# Hook fixture.\n"
    for relative, text in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return source


def test_missing_features_are_visible_and_unsupported_are_not_claimed_installed(tmp_path, feature_source):
    user_home = tmp_path / "home"
    install(["kimi", "claude", "codex"], source=feature_source, user_home=user_home)
    report = capabilities(feature_source, user_home=user_home, probes=False)
    assert not report["ok"]
    for name, features in report["agents"].items():
        assert features["skills"]["configured"]
        assert features["instructions"]["status"] == "missing"
        if name != "kimi":
            for component in ("agents", "hooks"):
                assert features[component]["status"] == "unsupported"
                assert not features[component]["installed"]


def test_all_configured_components_and_versions_without_live_requests(tmp_path, feature_source):
    user_home = tmp_path / "home"
    install(["kimi", "claude", "codex"], source=feature_source, user_home=user_home,
            components=["skills", "instructions", "hooks", "agents"])
    report = capabilities(feature_source, user_home=user_home, probes=False)
    assert report["ok"]
    assert report["source_version"] == "0.4.0"
    assert report["agents"]["kimi"]["hooks"]["probe"] == {"status": "skipped", "reason": "disabled"}
    assert report["agents"]["claude"]["skills"]["installed_version"] == "0.4.0"
    assert report["agents"]["codex"]["instructions"]["installed_version"] == "0.4.0"


def test_drift_separates_source_updates_local_blocks_and_skills(tmp_path, feature_source):
    user_home = tmp_path / "home"
    install(["kimi", "claude"], source=feature_source, user_home=user_home,
            components=["skills", "instructions", "hooks", "agents"])
    path = user_home / ".claude/CLAUDE.md"
    path.write_text(path.read_text().replace("Keep evidence", "Custom rules for evidence"), encoding="utf-8")
    (feature_source / "hooks/_common.py").write_text("# Changed helper.\n", encoding="utf-8")
    (feature_source / "agents/reviewer.md").write_text("Updated profile.\n", encoding="utf-8")
    (user_home / ".claude/skills/example/SKILL.md").write_text("Custom copy.\n", encoding="utf-8")
    report = capabilities(feature_source, user_home=user_home, probes=False)
    assert not report["ok"]
    assert report["agents"]["claude"]["instructions"]["locally_modified"]
    assert report["agents"]["claude"]["skills"]["different"] == ["example/SKILL.md"]
    assert report["agents"]["kimi"]["hooks"]["drift"] == ["source_changed_since_install"]
    assert report["agents"]["kimi"]["agents"]["drift"] == ["source_changed_since_install"]


def test_config_and_receipt_errors_do_not_echo_secrets(tmp_path, feature_source):
    user_home = tmp_path / "home"
    target = user_home / ".kimi-code/config.toml"
    target.parent.mkdir(parents=True)
    target.write_text('token="private-fixture-value"\nhooks="wrong-type"\n', encoding="utf-8")
    report = capabilities(feature_source, user_home=user_home, probes=False)
    assert report["agents"]["kimi"]["hooks"]["status"] == "error"
    assert "private-fixture-value" not in json.dumps(report)
    path = receipt_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('malformed private-fixture-value', encoding="utf-8")
    report = capabilities(feature_source, user_home=user_home, probes=False)
    assert report["agents"]["kimi"]["skills"]["status"] == "error"
    assert "private-fixture-value" not in json.dumps(report)


def test_probes_invoke_trusted_scripts_without_running_payload_commands(monkeypatch, feature_source):
    calls = []

    def fake_run(argv, **kwargs):
        assert not kwargs.get("shell")
        assert Path(argv[-1]).parent == feature_source / "hooks"
        assert kwargs["cwd"] != str(feature_source)
        assert "BITRIX_WEBHOOK_TOKEN" not in kwargs["env"]
        payload = json.loads(kwargs["input"])
        calls.append(payload["tool_input"])
        code, output = 0, {"status": "allowed"}
        if argv[-1].endswith("lint_on_edit.py"):
            output = {"status": "skipped", "reason": "non_python_file"}
        if payload["tool_input"].get("command") == "cat .env":
            code, output = 2, {"status": "blocked"}
        return subprocess.CompletedProcess(argv, code, stdout=json.dumps(output), stderr="private-fixture-value")

    monkeypatch.setenv("BITRIX_WEBHOOK_TOKEN", "private-fixture-value")
    monkeypatch.setattr(subprocess, "run", fake_run)
    report = probe_hooks(feature_source)
    assert report["status"] == "passed"
    assert {"command": "cat .env"} in calls
    assert {"command": "git commit -m synthetic-probe"} in calls
    assert "private-fixture-value" not in json.dumps(report)
    assert "managed task authorization" in report["limitation"]


def test_probe_missing_lint_report_is_failed_not_silently_green(monkeypatch, feature_source):
    def fake_run(argv, **kwargs):
        command = json.loads(kwargs["input"])["tool_input"].get("command")
        return subprocess.CompletedProcess(argv, 2 if command == "cat .env" else 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    report = probe_hooks(feature_source)
    assert report["status"] == "failed"
    assert report["hooks"]["lint_on_edit"]["checks"][0]["status"] == "error"


def test_arbitrary_configured_hook_is_never_probed(tmp_path, monkeypatch, feature_source):
    user_home = tmp_path / "home"
    install(["kimi"], components=["hooks"], source=feature_source, user_home=user_home)
    path = user_home / ".kimi-code/config.toml"
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    doc["hooks"][0]["command"] = "untrusted-executable --sensitive-option"
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("No hooks should be executed when configuration differs."))
    report = capabilities(feature_source, user_home=user_home, probes=True)
    hook = report["agents"]["kimi"]["hooks"]
    assert hook["status"] == "drift"
    assert hook["probe"] == {"status": "skipped", "reason": "not_configured"}
    assert "untrusted-executable" not in json.dumps(report)
