"""GitLab packaging and host/credential boundaries in the common harness."""

import json
import os
import subprocess
import sys

import pytest

from harness_cli import artifacts
from harness_cli.checks import private_values, scan_bytes
from harness_cli.doctor import doctor
from harness_cli.install import ROOT, install
from harness_cli.main import main
from harness_cli.redaction import model_environment, redact_credentials


ENTRYPOINTS = (
    ("gitlab-project-info", "project_info.py", []),
    ("gitlab-ci", "ci.py", ["--action", "pipelines"]),
    ("gitlab-mr", "mr.py", ["--action", "list"]),
    ("gitlab-repo-check", "repo_check.py", []),
)


@pytest.mark.parametrize("skill,script,arguments", ENTRYPOINTS)
def test_installed_gitlab_entrypoints_work_outside_repository(tmp_path, skill, script, arguments):
    user_home = tmp_path / "user"
    install(["claude", "codex"], source=ROOT, user_home=user_home)
    for agent_dir in (".claude", ".agents"):
        entrypoint = user_home / agent_dir / "skills" / skill / "scripts" / script
        assert (entrypoint.parents[2] / "_shared" / "gitlab_http.py").exists()
        result = subprocess.run([sys.executable, str(entrypoint), "--help"], cwd=tmp_path,
                                capture_output=True, encoding="utf-8", timeout=20)
        assert result.returncode == 0 and "--project" in result.stdout
        result = subprocess.run([sys.executable, str(entrypoint), "--project", "group/project", *arguments],
                                cwd=tmp_path, capture_output=True, encoding="utf-8", timeout=20)
        assert result.returncode == 2
        assert json.loads(result.stdout)["error"]["code"] == "CONFIG_MISSING"
        assert not result.stderr
    assert install(["claude", "codex"], source=ROOT, user_home=user_home, dry_run=True)["changes"] == 0


def test_optional_gitlab_config_and_tls_diagnostics_do_not_call_api(tmp_path, monkeypatch, config):
    from bitrix_config import Config
    from gitlab_http import Client

    monkeypatch.setattr(Config, "load", lambda: config)
    monkeypatch.setattr(Client, "request", lambda *a, **kw: pytest.fail("Doctor must not call GitLab"))
    user_home = tmp_path / "user"
    install(["kimi", "claude", "codex"], source=ROOT, user_home=user_home,
            components=["skills", "instructions", "hooks", "agents"])
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert report["ok"]
    assert report["gitlab"] == {"configured": False, "status": "not_configured", "api_probed": False}

    monkeypatch.setenv("GITLAB_HOST", "https://git.example.invalid")
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert not report["ok"] and report["gitlab"]["error_code"] == "CONFIG_MISSING"
    monkeypatch.setenv("GITLAB_TOKEN", "synthetic-gitlab-token")
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert report["ok"] and report["gitlab"]["configured"]
    assert report["gitlab"]["tls_verification"] and report["gitlab"]["transport"] == "https"
    assert report["gitlab"]["api_probed"] is False
    assert "git.example.invalid" not in json.dumps(report)
    assert "synthetic-gitlab-token" not in json.dumps(report)

    monkeypatch.setenv("GITLAB_CA_BUNDLE", str(tmp_path / "missing-ca.pem"))
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert not report["ok"] and report["gitlab"]["error_code"] == "TLS_CONFIG"


def test_doctor_reports_http_opt_in_without_claiming_tls(tmp_path, monkeypatch, config):
    from bitrix_config import Config
    from gitlab_http import Client

    monkeypatch.setattr(Config, "load", lambda: config)
    monkeypatch.setattr(Client, "request", lambda *a, **kw: pytest.fail("Doctor must not call GitLab"))
    user_home = tmp_path / "user"
    install(["kimi", "claude", "codex"], source=ROOT, user_home=user_home,
            components=["skills", "instructions", "hooks", "agents"])
    monkeypatch.setenv("GITLAB_ALLOW_INSECURE_HTTP", "1")
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert not report["ok"] and report["gitlab"]["error_code"] == "CONFIG_MISSING"
    monkeypatch.setenv("GITLAB_HOST", "http://git.example.invalid:8080")
    monkeypatch.setenv("GITLAB_TOKEN", "synthetic-gitlab-token")
    monkeypatch.setenv("GITLAB_ALLOW_INSECURE_HTTP", "0")
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert not report["ok"] and report["gitlab"]["error_code"] == "CONFIG_ERROR"
    monkeypatch.setenv("GITLAB_ALLOW_INSECURE_HTTP", "1")
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert report["ok"] and report["gitlab"]["configured"]
    assert report["gitlab"]["transport"] == "http" and not report["gitlab"]["tls_verification"]
    assert report["gitlab"]["api_probed"] is False
    assert "git.example.invalid" not in json.dumps(report)
    assert "synthetic-gitlab-token" not in json.dumps(report)
    monkeypatch.setenv("GITLAB_HOST", "https://git.example.invalid")
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert report["ok"] and report["gitlab"]["tls_verification"]
    assert report["gitlab"]["transport"] == "https"


def test_operations_selects_gitlab_without_changing_bitrix_default(monkeypatch, config, capsys):
    from bitrix_config import Config
    from bitrix_state import Journal
    from gitlab_config import Config as GitLabConfig
    from gitlab_state import Journal as GitLabJournal

    gitlab = GitLabConfig("https://git.example.invalid", "synthetic-gitlab-token")
    monkeypatch.setattr(Config, "load", lambda: config)
    monkeypatch.setattr(GitLabConfig, "load", lambda: gitlab)
    Journal(config).run("bitrix-example", "bitrix.fixture", {}, lambda: {"id": 1})
    GitLabJournal(gitlab).run("gitlab-example", "gitlab.fixture", {}, lambda: {"id": 2})
    assert main(["operations"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [op["operation_id"] for op in report["operations"]] == ["bitrix-example"]
    assert main(["operations", "--service", "gitlab"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [op["operation_id"] for op in report["operations"]] == ["gitlab-example"]
    assert "git.example.invalid" not in json.dumps(report)


def test_gitlab_operations_missing_configuration_is_structured(capsys):
    assert main(["operations", "--service", "gitlab"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False and report["error"]["code"] == "CONFIG_MISSING"


@pytest.mark.parametrize("host", ["https://git.example.invalid", "https://git.example.invalid:8443"])
def test_gitlab_values_are_redacted_in_receipts_and_scanned_before_publication(tmp_path, monkeypatch, host):
    token = "synthetic-gitlab-token"
    monkeypatch.setenv("GITLAB_HOST", host)
    monkeypatch.setenv("GITLAB_TOKEN", token)
    output = tmp_path / "receipt.json"
    result = artifacts.run_command(
        [sys.executable, "-c", "import os; print(os.environ['GITLAB_HOST']); print(os.environ['GITLAB_TOKEN'])"],
        tmp_path, 20, output)
    assert result["status"] == "passed"
    text = output.read_text(encoding="utf-8")
    assert host not in text and token not in text
    assert redact_credentials("GIT.EXAMPLE.INVALID") == "[REDACTED]"
    for value in (host, "git.example.invalid", token):
        findings = scan_bytes(value.encode(), "fixture.txt", private_values())
        assert findings == [{"location": "fixture.txt", "rule": "private_profile_value"}]
        assert value not in json.dumps(findings)
    pat = "glpat" + "-" + "x" * 24
    assert redact_credentials(pat) == "[REDACTED]"
    assert scan_bytes(pat.encode(), "fixture.txt")[0]["rule"] == "provider_key"


def test_model_helpers_receive_no_gitlab_or_other_service_credentials(monkeypatch):
    for name in ("GITLAB_HOST", "GITLAB_TOKEN", "GITLAB_PROFILE", "BITRIX_WEBHOOK_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "synthetic-sensitive-value")
    monkeypatch.setenv("HARNESS_MODEL_FIXTURE", "preserved")
    environment = model_environment()
    assert environment["HARNESS_MODEL_FIXTURE"] == "preserved"
    assert not any(name.startswith(("GITLAB_", "BITRIX_", "GH_", "GITHUB_")) for name in environment)
    assert os.environ["GITLAB_TOKEN"] == "synthetic-sensitive-value"
