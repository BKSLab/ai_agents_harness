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
    (root / "global").mkdir()
    (root / "global/AGENTS.md").write_text("# Shared rules\nRun appropriate checks.\n", encoding="utf-8")
    (root / "hooks").mkdir()
    for name in ("protect_secrets", "lint_on_edit", "git_gate", "_common"):
        (root / f"hooks/{name}.py").write_text("# Hook fixture.\n", encoding="utf-8")
    (root / "agents").mkdir()
    (root / "agents/reviewer.md").write_text("---\nname: reviewer\ndescription: Review changes.\ntools: [Read]\n---\nReview.\n", encoding="utf-8")
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


def test_managed_instructions_preserve_outside_bytes_and_update_only_owned_block(tmp_path, source):
    from harness_cli.install import instruction_block, plan_instructions
    target = tmp_path / "AGENTS.md"
    prefix, suffix = b"# My rules\r\nKeep my conventions.\r\n\r\n", b"\r\n# Other tool\r\nKeep this too.\r\n"
    target.write_bytes(prefix)
    apply(plan_instructions(target, source))
    target.write_bytes(target.read_bytes() + suffix)
    (source / "global/AGENTS.md").write_text("# New rules\nReview the current snapshot.\n", encoding="utf-8")
    apply(plan_instructions(target, source))
    assert target.read_bytes() == prefix + instruction_block(source) + suffix
    assert plan_instructions(target, source) == []


def test_instruction_local_edit_blocks_all_targets_then_override_is_backed_up(tmp_path, source):
    user_home = tmp_path / "home"
    install(["kimi"], source=source, user_home=user_home, components=["instructions"])
    path = user_home / ".kimi-code/AGENTS.md"
    path.write_bytes(path.read_bytes().replace(b"appropriate", b"my customized"))
    customized = path.read_bytes()
    with pytest.raises(ValueError, match="instructions conflicts"):
        install(["claude", "kimi"], source=source, user_home=user_home, components=["instructions"])
    assert not (user_home / ".claude").exists()
    report = install(["kimi"], source=source, user_home=user_home, components=["instructions"], replace_conflicts=True)
    from pathlib import Path
    backup = Path(report["backup"])
    assert any(item.read_bytes() == customized for item in backup.glob("*.bak"))


def test_removed_instruction_block_requires_explicit_restore(tmp_path, source):
    from harness_cli.install import plan_instructions
    path = tmp_path / "AGENTS.md"
    apply(plan_instructions(path, source))
    path.write_text("My replacement instructions\n", encoding="utf-8")
    with pytest.raises(ValueError, match="removed locally"):
        plan_instructions(path, source)
    apply(plan_instructions(path, source, replace_conflicts=True))
    assert path.read_text().startswith("My replacement instructions\n")


def test_malformed_instruction_markers_are_not_guessed(tmp_path, source):
    from harness_cli.install import INSTRUCTIONS_START, plan_instructions
    path = tmp_path / "AGENTS.md"
    path.write_bytes(INSTRUCTIONS_START + b"\nUser text without closing marker\n")
    with pytest.raises(ValueError, match="ambiguous"):
        plan_instructions(path, source, replace_conflicts=True)


def test_exact_manual_instructions_are_adopted_without_duplicate_content(tmp_path, source):
    from harness_cli.install import instruction_block, plan_instructions
    path = tmp_path / "AGENTS.md"
    path.write_bytes((source / "global/AGENTS.md").read_bytes())
    apply(plan_instructions(path, source))
    assert path.read_bytes() == instruction_block(source)


def test_all_components_merge_once_preserve_unrelated_hooks_and_are_idempotent(tmp_path, source):
    home = tmp_path / "home"
    path = home / ".kimi-code/config.toml"
    path.parent.mkdir(parents=True)
    path.write_text('# User configuration\ndefault_model="existing"\nextra_agent_dirs=["/custom/agents"] # keep agent paths\n'
                    '[[hooks]] # User notification\nevent="Notification"\ncommand="my-notifier"\ntimeout=2\n', encoding="utf-8")
    components = ["skills", "instructions", "hooks", "agents"]
    report = install(["kimi", "claude", "codex"], source=source, user_home=home, components=components)
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    assert doc["default_model"] == "existing"
    assert "/custom/agents" in doc["extra_agent_dirs"]
    assert "# User notification" in path.read_text(encoding="utf-8")
    assert "# keep agent paths" in path.read_text(encoding="utf-8")
    assert len(doc["hooks"]) == 4
    assert doc["hooks"][0]["command"] == "my-notifier"
    assert all(set(item) <= {"event", "matcher", "command", "timeout"} for item in doc["hooks"])
    assert len(report["unsupported"]) == 4
    assert (home / ".codex/AGENTS.md").exists()
    assert (home / ".claude/CLAUDE.md").exists()
    assert sum(action["path"] == str(path) for action in report["actions"]) == 1
    assert install(["kimi", "claude", "codex"], source=source, user_home=home, components=components)["changes"] == 0


def test_hook_relocation_replaces_only_previous_owned_commands(tmp_path, source):
    import shutil
    from harness_cli.install import hook_definitions
    path = tmp_path / "config.toml"
    path.write_text('[[hooks]]\nevent="PreToolUse"\nmatcher="Bash"\ncommand="user-security-check"\n', encoding="utf-8")
    apply(plan_kimi(path, source, hooks=True, agents=True))
    renamed = tmp_path / "relocated 'repository with spaces"
    shutil.copytree(source, renamed)
    apply(plan_kimi(path, renamed, hooks=True, agents=True))
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    commands = {item["command"] for item in doc["hooks"]}
    assert commands == {"user-security-check", *(item["command"] for item in hook_definitions(renamed).values())}
    assert list(doc["extra_agent_dirs"]) == [(renamed / "agents").as_posix()]
    assert plan_kimi(path, renamed, hooks=True, agents=True) == []


def test_edited_hook_settings_require_override_and_are_backed_up(tmp_path, source):
    path = tmp_path / "config.toml"
    apply(plan_kimi(path, source, hooks=True))
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    doc["hooks"][0]["timeout"] = 90
    customized = tomlkit.dumps(doc).encode("utf-8")
    path.write_bytes(customized)
    with pytest.raises(ValueError, match="hook conflicts"):
        plan_kimi(path, source, hooks=True)
    backup = apply(plan_kimi(path, source, hooks=True, replace_conflicts=True))
    assert any(item.read_bytes() == customized for item in backup.glob("*.bak"))
    hooks = tomlkit.parse(path.read_text(encoding="utf-8"))["hooks"]
    assert next(item for item in hooks if "protect_secrets.py" in item["command"])["timeout"] == 5
    assert plan_kimi(path, source, hooks=True) == []


def test_skills_only_update_keeps_other_component_receipts(tmp_path, source):
    path = tmp_path / "config.toml"
    apply(plan_kimi(path, source, hooks=True, agents=True))
    receipt = read_receipt(path)
    apply(plan_kimi(path, source))
    assert read_receipt(path) == receipt
    assert plan_kimi(path, source, hooks=True, agents=True) == []


def test_unknown_hook_with_our_command_is_not_overwritten(tmp_path, source):
    from harness_cli.install import hook_definitions
    path = tmp_path / "config.toml"
    definition = next(iter(hook_definitions(source).values()))
    doc = tomlkit.document()
    entries = tomlkit.aot()
    table = tomlkit.table()
    table.update({**definition, "timeout": 90})
    entries.append(table)
    doc["hooks"] = entries
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="unmanaged hook"):
        plan_kimi(path, source, hooks=True, replace_conflicts=True)


def test_hook_command_uses_explicit_interpreter_and_roundtrips_shell_quoting(source):
    import shlex
    from harness_cli.install import hook_definitions, hook_interpreter
    for name, definition in hook_definitions(source).items():
        argv = shlex.split(definition["command"])
        assert argv == [hook_interpreter(source).as_posix(), "-E", "-s", "-X", "utf8", (source / f"hooks/{name}.py").as_posix()]


def test_hook_interpreter_preserves_venv_path(source):
    import os
    from harness_cli.install import hook_interpreter
    path = source / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture")
    assert hook_interpreter(source) == path


def test_unsupported_components_do_not_create_fake_installation(tmp_path, source):
    home = tmp_path / "home"
    report = install(["codex", "claude"], components=["hooks", "agents"], source=source, user_home=home)
    assert report["changes"] == 0
    assert len(report["unsupported"]) == 4
    assert not home.exists()


def test_component_selection_does_not_implicitly_install_other_components(tmp_path, source):
    home = tmp_path / "home"
    install(["kimi"], components=["hooks"], source=source, user_home=home)
    doc = tomlkit.parse((home / ".kimi-code/config.toml").read_text(encoding="utf-8"))
    assert "extra_skill_dirs" not in doc and "extra_agent_dirs" not in doc
    assert not (home / ".kimi-code/AGENTS.md").exists()


def test_failed_write_rolls_back_config_and_keeps_user_content(tmp_path, source, monkeypatch):
    import harness_cli.install as module
    user_home = tmp_path / "home"
    config = user_home / ".kimi-code/config.toml"
    config.parent.mkdir(parents=True)
    original = b'default_model="keep-my-setting"\n'
    config.write_bytes(original)
    write = module.atomic_write

    def fail_on_instructions(path, data):
        if path == user_home / ".kimi-code/AGENTS.md":
            raise OSError("Synthetic write failure")
        return write(path, data)

    monkeypatch.setattr(module, "atomic_write", fail_on_instructions)
    with pytest.raises(OSError, match="Synthetic"):
        install(["kimi"], source=source, user_home=user_home, components=["skills", "instructions", "hooks", "agents"])
    assert config.read_bytes() == original
    assert read_receipt(config) == {}
    assert not (user_home / ".kimi-code/AGENTS.md").exists()
