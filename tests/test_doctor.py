import json

from harness_cli.doctor import doctor
from harness_cli.install import ROOT, install


def test_doctor_describes_installed_components_and_skips_network(monkeypatch, tmp_path, config):
    from bitrix_config import Config
    import urllib.request
    monkeypatch.setattr(Config, "load", lambda: config)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No API probes")))
    user_home = tmp_path / "home"
    install(["kimi", "claude", "codex"], source=ROOT, user_home=user_home,
            components=["skills", "instructions", "hooks", "agents"])
    report = doctor(ROOT, versions=False, probes=False, user_home=user_home)
    assert report["ok"]
    assert report["harness_version"] == report["source_version"]
    assert report["bitrix"]["configured"]
    assert report["agents"]["kimi"]["registered"]
    assert report["agents"]["kimi"]["configured_directory_count"] == 1
    assert report["agents"]["claude"]["missing"] == []
    assert report["agents"]["codex"]["features"]["hooks"]["status"] == "unsupported"
    output = json.dumps(report)
    assert "https://portal.example.invalid" not in output and "fixture-token" not in output


def test_doctor_missing_setup_has_reasons_and_does_not_claim_ready(tmp_path):
    report = doctor(ROOT, versions=False, probes=False, user_home=tmp_path / "missing")
    assert not report["ok"]
    assert "no_agent_directories_found" in report["warnings"]
    assert "bitrix_not_configured_in_this_process" in report["warnings"]
    assert report["agents"]["kimi"]["features"]["hooks"]["probe"]["status"] == "skipped"
