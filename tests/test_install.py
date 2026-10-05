import json

import pytest
import tomlkit

from harness_cli.install import apply, install, plan_copies, plan_kimi, read_receipt


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "repo with spaces"
    path = root / "skills" / "example" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text('---\nname: example\ndescription: Example skill.\n---\nBody\n', encoding="utf-8")
    shared = root / "skills" / "_shared" / "runtime.py"
    shared.parent.mkdir()
    shared.write_text('print("fixture")\n', encoding="utf-8")
    return root


@pytest.mark.parametrize("text", [
    '',
    '# extra_skill_dirs may be configured\n[thinking]\nenabled=true\n',
    'default_model="fixture"\n  [thinking]\nenabled=true\n',
    'extra_skill_dirs = ["/other/skills"] # keep this\n[thinking]\nenabled=true\n',
    'extra_skill_dirs = [\n  "/other/skills",\n]\n[thinking]\nenabled=true\n',
])
def test_kimi_toml_merge_preserves_settings_and_is_idempotent(tmp_path, source, text):
    path = tmp_path / "kimi" / "config.toml"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    before = tomlkit.parse(text)
    apply(plan_kimi(path, source))
    after_text = path.read_text(encoding="utf-8")
    after = tomlkit.parse(after_text)
    assert (source / "skills").as_posix() in after["extra_skill_dirs"]
    for key, value in before.items():
        if key != "extra_skill_dirs":
            assert after[key] == value
    if "/other/skills" in text:
        assert "/other/skills" in after["extra_skill_dirs"]
    if "# keep this" in text:
        assert "# keep this" in after_text
    assert plan_kimi(path, source) == []


def test_move_repository_updates_only_previous_managed_kimi_path(tmp_path, source):
    path = tmp_path / "kimi.toml"
    path.write_text('extra_skill_dirs=["/other/skills"]\n', encoding="utf-8")
    apply(plan_kimi(path, source))
    new_source = tmp_path / 'renamed "repository"'
    apply(plan_kimi(path, new_source))
    directories = tomlkit.parse(path.read_text())["extra_skill_dirs"]
    assert "/other/skills" in directories
    assert (new_source / "skills").as_posix() in directories
    assert (source / "skills").as_posix() not in directories


def test_unmanaged_conflict_stops_before_writes(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "SKILL.md").write_bytes(b"user content")
    with pytest.raises(ValueError, match="conflicts"):
        plan_copies(target, {"SKILL.md": b"new content", "new.txt": b"new"})
    assert (target / "SKILL.md").read_bytes() == b"user content"
    assert not (target / "new.txt").exists()


def test_conflict_replacement_is_backed_up(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "SKILL.md").write_bytes(b"user content")
    backup = apply(plan_copies(target, {"SKILL.md": b"new content"}, replace_conflicts=True))
    assert (backup / "0000.bak").read_bytes() == b"user content"
    assert (target / "SKILL.md").read_bytes() == b"new content"
    assert read_receipt(target)["files"]["SKILL.md"]


def test_updates_remove_only_managed_obsolete_files(tmp_path):
    target = tmp_path / "target"
    apply(plan_copies(target, {"skill/a.py": b"first", "skill/old.py": b"old"}))
    (target / "skill" / "user.txt").write_bytes(b"keep")
    apply(plan_copies(target, {"skill/a.py": b"second"}))
    assert not (target / "skill" / "old.py").exists()
    assert (target / "skill" / "user.txt").read_bytes() == b"keep"
    assert plan_copies(target, {"skill/a.py": b"second"}) == []


def test_local_edits_to_managed_files_are_preserved(tmp_path):
    target = tmp_path / "target"
    apply(plan_copies(target, {"a.py": b"first"}))
    (target / "a.py").write_bytes(b"user edit")
    with pytest.raises(ValueError, match="conflicts"):
        plan_copies(target, {"a.py": b"second"})
    with pytest.raises(ValueError, match="conflicts"):
        plan_copies(target, {})


def test_paths_cannot_escape_target(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        plan_copies(tmp_path / "target", {"../outside": b"bad"})
    assert not (tmp_path / "outside").exists()


def test_invalid_config_aborts_before_any_agent_is_changed(tmp_path, source):
    user_home = tmp_path / "user"
    path = user_home / ".kimi-code" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text('extra_skill_dirs="wrong type"', encoding="utf-8")
    with pytest.raises(ValueError):
        install(["claude", "kimi"], source=source, user_home=user_home)
    assert not (user_home / ".claude").exists()


def test_fresh_install_dry_run_then_repeat(tmp_path, source):
    user_home = tmp_path / "new user"
    report = install(["kimi", "claude", "codex"], source=source, user_home=user_home, dry_run=True)
    assert report["changes"] > 0 and not user_home.exists()
    install(["kimi", "claude", "codex"], source=source, user_home=user_home)
    assert (user_home / ".agents/skills/example/SKILL.md").exists()
    assert (user_home / ".claude/skills/_shared/runtime.py").exists()
    assert install(["kimi", "claude", "codex"], source=source, user_home=user_home)["changes"] == 0


def test_no_detected_agents_reports_missing_setup(tmp_path, source):
    with pytest.raises(ValueError, match="No agent directories"):
        install(None, source=source, user_home=tmp_path / "absent")


def test_changes_after_planning_are_not_overwritten(tmp_path):
    target = tmp_path / "target"
    plan = plan_copies(target, {"a.py": b"harness"})
    target.mkdir()
    (target / "a.py").write_bytes(b"user edit")
    with pytest.raises(ValueError, match="changed after"):
        apply(plan)
    assert (target / "a.py").read_bytes() == b"user edit"


def test_backup_contains_restore_metadata(tmp_path):
    target = tmp_path / "target"
    backup = apply(plan_copies(target, {"a.py": b"harness"}))
    record = json.loads((backup / "restore.json").read_text())
    assert record[0]["destination"] == str(target / "a.py")
    assert record[0]["installed_hash"] and record[0]["backup"] is None


def test_legacy_migration_allows_git_line_endings_only(tmp_path, monkeypatch, source):
    from harness_cli.install import plan_legacy_codex
    import subprocess
    user_home = tmp_path / "user"
    legacy = user_home / ".codex/skills/example/SKILL.md"
    legacy.parent.mkdir(parents=True)
    baseline = b"line1\nline2\n"
    legacy.write_bytes(b"line1\r\nline2\r\n")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: type("Output", (), {"stdout": "skills/example/SKILL.md\n"})())
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: baseline)
    plan = plan_legacy_codex(source, user_home)
    assert len(plan) == 1 and plan[0].after is None
    legacy.write_bytes(b"a different skill")
    with pytest.raises(ValueError, match="differs"):
        plan_legacy_codex(source, user_home)
