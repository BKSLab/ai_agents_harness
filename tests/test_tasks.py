"""Exercise task evidence against real disposable Git repositories and processes."""

import copy
import json
import os
from pathlib import Path
import subprocess

import pytest

from harness_cli import tasks


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="strict", timeout=20, check=True)
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    # Avoid machine-specific hooks, identities, signing and credential helpers.
    git_config = tmp_path / "empty-gitconfig"
    git_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Harness Fixture")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "fixture@example.invalid")
    root = tmp_path / "project with spaces"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "commit.gpgsign", "false")
    (root / "app.py").write_bytes(b"VALUE = 1\n")
    (root / "unrelated.txt").write_bytes(b"Original owner content.\n")
    (root / ".gitignore").write_bytes(b"__pycache__/\n*.pyc\n")
    git(root, "add", "--all")
    git(root, "commit", "-m", "Synthetic fixture baseline")
    git(root, "remote", "add", "origin", "https://example.invalid/synthetic/project.git")
    return root


def plan(command=None, *, scope=None):
    command = command or "from pathlib import Path; assert Path('app.py').read_text(encoding='utf-8') == 'VALUE = 2\\n'"
    return {
        "schema_version": 1,
        "scope": scope or ["app.py"],
        "acceptance": [{"id": "AC1", "description": "The requested value is present.", "checks": ["C1"]}],
        "risks": [{"id": "R1", "description": "Wrong value would break the caller.", "severity": "medium", "checks": ["C1"]}],
        "checks": [{"id": "C1", "argv": ["{python}", "-c", command], "timeout_seconds": 10}],
    }


def start(root, *, task_id="feature", mode="light", task_plan=None, adopt=()):
    tasks.init(task_id, root, "Implement the requested fixture behavior", mode=mode, adopt_changes=adopt)
    tasks.set_plan(task_id, root, task_plan or plan())
    tasks.approve(task_id, root, "Synthetic user authorization in test fixture")
    return task_id


def ready(root, *, mode="light", task_plan=None):
    task_id = start(root, mode=mode, task_plan=task_plan)
    (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    receipt = tasks.verify(task_id, root)
    assert receipt["status"] == "passed"
    return task_id, receipt


def review_packet(root, *, task_plan=None):
    task_id, source_receipt = ready(root, mode="standard", task_plan=task_plan)
    packet = tasks.snapshot(task_id, root)
    receipt = tasks.verify(task_id, root, packet["snapshot_id"])
    assert receipt["status"] == "passed"
    verdict = {
        "schema_version": 1,
        "snapshot_id": packet["snapshot_id"],
        "fingerprint": packet["fingerprint"],
        "plan_hash": packet["plan_hash"],
        "verification_id": receipt["id"],
        "reviewer": "Independent fixture reviewer",
        "status": "approved",
        "summary": "Checked the requested behavior and the controller's evidence.",
        "findings": [],
        "limitations": [],
    }
    return task_id, packet, source_receipt, receipt, verdict


def grants(task_id, root):
    tasks.authorize(task_id, root, "commit", "main", "Synthetic commit authorization")
    tasks.authorize(task_id, root, "push", "origin/main", "Synthetic push authorization")


def test_checks_cannot_run_before_actual_plan_authorization(repository):
    task_id = "approval"
    initial = tasks.init(task_id, repository, "Do the requested change", mode="light")
    assert initial["stage"] == "planning" and not initial["ready"]
    tasks.set_plan(task_id, repository, plan())
    assert tasks.status(task_id, repository)["stage"] == "awaiting_plan_approval"
    with pytest.raises(ValueError, match="approved plan"):
        tasks.verify(task_id, repository)
    assert tasks.Store(repository).load(task_id)["verifications"] == []
    with pytest.raises(ValueError, match="authorization"):
        tasks.approve(task_id, repository, " ")
    tasks.approve(task_id, repository, "User approved this concrete fixture plan")
    assert tasks.status(task_id, repository)["plan_approved"]


def test_real_failure_pass_and_stale_code_are_distinct(repository):
    task_id = start(repository)
    failed = tasks.verify(task_id, repository)
    assert not failed["ok"] and failed["checks"][0]["exit_code"] != 0
    assert "current_checks_not_passed" in tasks.status(task_id, repository)["blockers"]
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    passed = tasks.verify(task_id, repository)
    assert passed["ok"] and tasks.status(task_id, repository)["ready"]
    (repository / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
    stale = tasks.status(task_id, repository)
    assert not stale["ready"] and stale["verification"] is None


def test_latest_failed_run_supersedes_pass_for_identical_files(repository, monkeypatch):
    task_plan = plan("import os; assert os.environ.get('HARNESS_TEST_FLAG') == 'pass'")
    task_id = start(repository, task_plan=task_plan)
    monkeypatch.setenv("HARNESS_TEST_FLAG", "pass")
    first = tasks.verify(task_id, repository)
    monkeypatch.setenv("HARNESS_TEST_FLAG", "fail")
    second = tasks.verify(task_id, repository)
    assert first["fingerprint"] == second["fingerprint"]
    assert first["status"] == "passed" and second["status"] == "failed"
    report = tasks.status(task_id, repository)
    assert not report["ready"] and report["verification"]["id"] == second["id"]


def test_out_of_scope_edit_blocks_verification_without_changing_owner_files(repository):
    task_id = start(repository)
    (repository / "unrelated.txt").write_text("Unexpected outside change.\n", encoding="utf-8")
    before = (repository / "unrelated.txt").read_bytes()
    assert "changes_outside_approved_scope" in tasks.status(task_id, repository)["blockers"]
    with pytest.raises(ValueError, match="Scope"):
        tasks.verify(task_id, repository)
    assert (repository / "unrelated.txt").read_bytes() == before
    assert tasks.Store(repository).load(task_id)["verifications"] == []


def test_preexisting_owner_edits_are_preserved_and_cannot_be_modified(repository):
    path = repository / "unrelated.txt"
    path.write_text("Owner work in progress.\n", encoding="utf-8")
    owner = path.read_bytes()
    task_id, _ = ready(repository)
    assert path.read_bytes() == owner
    assert tasks.status(task_id, repository)["ready"]
    path.write_text("Task overwrote unrelated owner work.\n", encoding="utf-8")
    assert "preexisting_changes_modified" in tasks.status(task_id, repository)["blockers"]
    with pytest.raises(ValueError, match="Scope"):
        tasks.verify(task_id, repository)


def test_explicitly_adopted_change_is_in_review_packet_even_without_further_edit(repository):
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    task_id = start(repository, mode="standard", adopt=["app.py"])
    assert tasks.verify(task_id, repository)["ok"]
    packet = tasks.snapshot(task_id, repository)
    assert "app.py" in packet["changed_paths"]
    assert "VALUE = 2" in Path(packet["packet"]).with_name("changes.patch").read_text(encoding="utf-8")


def test_adoption_is_explicit_and_limited_to_existing_changes(repository):
    with pytest.raises(ValueError, match="Adopt"):
        tasks.init("wrong-adoption", repository, "Fixture", adopt_changes=["app.py"])


def test_high_risk_requires_rollback_and_compatibility(repository):
    tasks.init("migration", repository, "Fixture migration", mode="high-risk")
    with pytest.raises(ValueError, match="rollback and compatibility"):
        tasks.set_plan("migration", repository, plan())
    candidate = plan()
    candidate.update(rollback="Restore the old fixture implementation.", compatibility="Keep the fixture field name.")
    result = tasks.set_plan("migration", repository, candidate)
    assert result["stage"] == "awaiting_plan_approval"


def test_every_risk_and_acceptance_reference_must_resolve(repository):
    tasks.init("contracts", repository, "Fixture contracts")
    candidate = plan()
    candidate["risks"][0]["checks"] = ["MISSING"]
    with pytest.raises(ValueError, match="defined checks"):
        tasks.set_plan("contracts", repository, candidate)
    candidate = plan()
    candidate["checks"].append({"id": "C1", "argv": ["{python}", "-c", "pass"]})
    with pytest.raises(ValueError, match="unique"):
        tasks.set_plan("contracts", repository, candidate)


def test_standard_work_requires_snapshot_verification_and_independent_review(repository):
    task_id, packet, source, snapshot_receipt, verdict = review_packet(repository)
    assert "independent_review_required" in tasks.status(task_id, repository)["blockers"]
    forged = {**verdict, "verification_id": "verify-does-not-exist"}
    with pytest.raises(ValueError, match="controller-generated"):
        tasks.review(task_id, repository, forged)
    with pytest.raises(ValueError, match="controller-generated"):
        tasks.review(task_id, repository, {**verdict, "verification_id": source["id"]})
    result = tasks.review(task_id, repository, verdict)
    assert result["ready"] and result["review"]["verification_id"] == snapshot_receipt["id"]
    assert Path(packet["path"]).resolve() != repository.resolve()


def test_failed_latest_snapshot_run_invalidates_older_successful_receipt(repository, monkeypatch):
    monkeypatch.setenv("HARNESS_TEST_FLAG", "pass")
    task_plan = plan("import os; assert os.environ.get('HARNESS_TEST_FLAG') == 'pass'")
    task_id, packet, _, first, verdict = review_packet(repository, task_plan=task_plan)
    monkeypatch.setenv("HARNESS_TEST_FLAG", "fail")
    second = tasks.verify(task_id, repository, packet["snapshot_id"])
    assert first["fingerprint"] == second["fingerprint"] and not second["ok"]
    with pytest.raises(ValueError):
        tasks.review(task_id, repository, verdict)
    assert not tasks.status(task_id, repository)["ready"]


def test_changed_snapshot_cannot_be_approved(repository):
    task_id, packet, _, _, verdict = review_packet(repository)
    (Path(packet["path"]) / "app.py").write_text("VALUE = 100\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        tasks.review(task_id, repository, verdict)
    assert not tasks.status(task_id, repository)["ready"]


def test_major_findings_prevent_approval_and_repeated_disagreement_stops_loop(repository):
    task_id, _, _, _, verdict = review_packet(repository)
    finding = {"id": "F1", "severity": "major", "location": "app.py:1",
               "problem": "Fixture contract requires discussion.", "evidence": "The fixture uses a literal value.",
               "suggestion": "Resolve the fixture contract with the owner."}
    verdict["findings"] = [finding]
    with pytest.raises(ValueError, match="major"):
        tasks.review(task_id, repository, verdict)
    verdict["status"] = "changes_requested"
    tasks.review(task_id, repository, verdict)
    report = tasks.review(task_id, repository, verdict)
    assert "review_no_progress" in report["blockers"] and not report["ready"]
    third = tasks.review(task_id, repository, verdict)
    assert "review_iteration_limit" in third["blockers"]
    with pytest.raises(ValueError, match="iteration limit"):
        tasks.review(task_id, repository, verdict)


def test_plan_change_invalidates_approval_and_action_grants(repository):
    task_id, _ = ready(repository)
    grants(task_id, repository)
    before = tasks.Store(repository).load(task_id)
    tasks.set_plan(task_id, repository, copy.deepcopy(before["plan"]))
    unchanged = tasks.Store(repository).load(task_id)
    assert unchanged["approval"] == before["approval"] and unchanged["grants"] == before["grants"]
    candidate = copy.deepcopy(before["plan"])
    candidate["acceptance"][0]["description"] += " Verify the new requirement too."
    tasks.set_plan(task_id, repository, candidate)
    state = tasks.Store(repository).load(task_id)
    assert state["approval"] is None and state["grants"] == []
    tasks.approve(task_id, repository, "User approved the amended fixture plan")
    assert tasks.verify(task_id, repository)["ok"]
    assert not tasks.check_authorization(task_id, repository, "commit", "main")["authorized"]


def test_repository_destination_change_does_not_expand_existing_authorization(repository):
    task_id, _ = ready(repository)
    grants(task_id, repository)
    git(repository, "remote", "set-url", "origin", "https://example.invalid/another/project.git")
    report = tasks.status(task_id, repository)
    assert "repository_target_changed" in report["blockers"]
    assert not tasks.check_authorization(task_id, repository, "push", "origin/main")["ok"]
    with pytest.raises(ValueError, match="identity changed"):
        tasks.authorize(task_id, repository, "push", "origin/main", "Old permission")


def test_sqlite_revision_prevents_lost_updates(repository):
    task_id = start(repository)
    store = tasks.Store(repository)
    first, stale = store.load(task_id), store.load(task_id)
    first["title"] = "First writer"
    store.save(first, "fixture_first_writer")
    stale["title"] = "Stale writer"
    with pytest.raises(ValueError, match="concurrently"):
        store.save(stale, "fixture_stale_writer")
    assert store.load(task_id)["title"] == "First writer"


def test_recovery_clears_interrupted_run_without_inventing_passing_evidence(repository):
    task_id = start(repository)
    store = tasks.Store(repository)
    state = store.load(task_id)
    state["active_run"] = {"id": "verify-interrupted", "started_at": tasks.now(), "snapshot_id": None}
    store.save(state, "fixture_interrupted_controller")
    assert tasks.status(task_id, repository)["stage"] == "verifying"
    with pytest.raises(ValueError, match="verification is active"):
        tasks.verify(task_id, repository)
    result = tasks.recover(task_id, repository, "Synthetic controller was terminated")
    assert not result["ready"] and "current_checks_not_passed" in result["blockers"]
    state = store.load(task_id)
    assert state["active_run"] is None and state["verifications"] == []


def test_timeout_is_reported_and_does_not_leave_active_verification(repository):
    candidate = plan("import time; time.sleep(30)")
    candidate["checks"][0]["timeout_seconds"] = 1
    task_id = start(repository, task_plan=candidate)
    result = tasks.verify(task_id, repository)
    assert not result["ok"] and result["checks"][0]["status"] == "error"
    assert result["checks"][0]["reason"] == "timeout"
    assert tasks.Store(repository).load(task_id)["active_run"] is None


def test_check_mutation_invalidates_its_own_evidence(repository):
    candidate = plan("from pathlib import Path; Path('app.py').write_text('VALUE = 3\\n', encoding='utf-8')")
    task_id = start(repository, task_plan=candidate)
    result = tasks.verify(task_id, repository)
    assert result["checks"][0]["exit_code"] == 0
    assert not result["ok"] and result["reason"] == "files_changed_during_verification"


def test_process_receipts_redact_secret_environment_values(repository, monkeypatch):
    monkeypatch.setenv("HARNESS_TEST_SECRET", "private-synthetic-secret-value")
    candidate = plan("import os; print(os.environ['HARNESS_TEST_SECRET'])")
    task_id = start(repository, task_plan=candidate)
    result = tasks.verify(task_id, repository)
    assert result["ok"]
    output = Path(result["checks"][0]["log"]).read_text(encoding="utf-8")
    assert "private-synthetic-secret-value" not in output and "[REDACTED]" in output


def test_snapshot_contains_owned_untracked_files_and_diff_survives_a_local_commit(repository):
    task_id, _ = ready(repository, task_plan=plan(scope=["app.py", "new_module.py"]))
    (repository / "new_module.py").write_text("NEW_VALUE = 2\n", encoding="utf-8")
    git(repository, "add", "app.py")
    git(repository, "commit", "-m", "Synthetic local checkpoint")
    packet = tasks.snapshot(task_id, repository)
    assert "app.py" in packet["changed_paths"] and "new_module.py" in packet["changed_paths"]
    assert (Path(packet["path"]) / "new_module.py").read_text(encoding="utf-8") == "NEW_VALUE = 2\n"
    diff = Path(packet["packet"]).with_name("changes.patch").read_text(encoding="utf-8")
    assert "+VALUE = 2" in diff


def test_git_commit_requires_staged_bytes_to_match_verified_working_tree(repository):
    task_id, _ = ready(repository)
    grants(task_id, repository)
    path = repository / "app.py"
    path.write_text("VALUE = 999\n", encoding="utf-8")
    git(repository, "add", "app.py")
    path.write_text("VALUE = 2\n", encoding="utf-8")
    assert tasks.status(task_id, repository)["ready"]
    assert not tasks.git_gate(repository, "commit")["allowed"]
    git(repository, "add", "app.py")
    assert tasks.git_gate(repository, "commit")["allowed"]


def test_git_push_requires_actual_head_to_match_verified_working_tree(repository):
    task_id, _ = ready(repository)
    grants(task_id, repository)
    target = {"remote": "origin", "refspec": "HEAD:main"}
    assert not tasks.git_gate(repository, "push", target)["allowed"]
    git(repository, "add", "app.py")
    assert tasks.git_gate(repository, "commit")["allowed"]
    git(repository, "commit", "-m", "Synthetic reviewed implementation")
    assert tasks.git_gate(repository, "push", target)["allowed"]


def test_untracked_verified_input_cannot_be_omitted_from_commit(repository):
    task_id, _ = ready(repository, task_plan=plan(scope=["app.py", "new_module.py"]))
    (repository / "new_module.py").write_text("NEW_VALUE = 2\n", encoding="utf-8")
    assert tasks.verify(task_id, repository)["ok"]
    grants(task_id, repository)
    git(repository, "add", "app.py")
    assert not tasks.git_gate(repository, "commit")["allowed"]
    git(repository, "add", "new_module.py")
    assert tasks.git_gate(repository, "commit")["allowed"]


def test_preexisting_staged_owner_change_cannot_be_included_in_task_commit(repository):
    path = repository / "unrelated.txt"
    path.write_text("Owner staged work.\n", encoding="utf-8")
    git(repository, "add", "unrelated.txt")
    owner_index = git(repository, "show", ":unrelated.txt")
    task_id, _ = ready(repository)
    grants(task_id, repository)
    git(repository, "add", "app.py")
    assert not tasks.git_gate(repository, "commit")["allowed"]
    assert git(repository, "show", ":unrelated.txt") == owner_index


def test_git_gate_accepts_git_normalized_crlf_content(repository):
    git(repository, "config", "core.autocrlf", "true")
    task_id = start(repository)
    (repository / "app.py").write_bytes(b"VALUE = 2\r\n")
    assert tasks.verify(task_id, repository)["ok"]
    grants(task_id, repository)
    git(repository, "add", "app.py")
    assert tasks.git_gate(repository, "commit")["allowed"]


def test_git_push_requires_explicit_target_even_with_upstream(repository):
    task_id, _ = ready(repository)
    grants(task_id, repository)
    git(repository, "add", "app.py")
    git(repository, "commit", "-m", "Synthetic reviewed implementation")
    git(repository, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repository, "branch", "--set-upstream-to=origin/main", "main")
    assert not tasks.git_gate(repository, "push")["allowed"]


@pytest.mark.parametrize("setting,value", [("push.followTags", "true"), ("remote.origin.mirror", "true")])
def test_push_rejects_configuration_that_expands_its_scope(repository, setting, value):
    task_id, _ = ready(repository)
    grants(task_id, repository)
    git(repository, "add", "app.py")
    git(repository, "commit", "-m", "Synthetic reviewed implementation")
    git(repository, "config", setting, value)
    assert not tasks.git_gate(repository, "push", {"remote": "origin", "refspec": "HEAD:main"})["allowed"]


def test_git_push_refuses_multiple_push_destinations(repository):
    task_id, _ = ready(repository)
    grants(task_id, repository)
    git(repository, "add", "app.py")
    git(repository, "commit", "-m", "Synthetic reviewed implementation")
    git(repository, "config", "--add", "remote.origin.pushurl", "https://example.invalid/synthetic/project.git")
    git(repository, "config", "--add", "remote.origin.pushurl", "https://example.invalid/extra/project.git")
    assert not tasks.git_gate(repository, "push", {"remote": "origin", "refspec": "HEAD:main"})["allowed"]


@pytest.mark.parametrize("identifier", ["NUL", "con.txt", "COM1", "Lpt9", "task."])
def test_nonportable_identifiers_are_rejected(identifier):
    with pytest.raises(ValueError):
        tasks.identifier(identifier)


def test_case_distinct_task_ids_use_distinct_artifact_paths(repository):
    tasks.init("TASK", repository, "Uppercase fixture")
    tasks.init("task", repository, "Lowercase fixture")
    store = tasks.Store(repository)
    first, second = store.directory("TASK"), store.directory("task")
    assert os.path.normcase(str(first)) != os.path.normcase(str(second))
    assert json.loads((first / "checkpoint.json").read_text(encoding="utf-8"))["id"] == "TASK"
    assert json.loads((second / "checkpoint.json").read_text(encoding="utf-8"))["id"] == "task"


def test_case_distinct_check_ids_have_separate_receipts(repository):
    candidate = plan()
    candidate["checks"].append({"id": "c1", "argv": ["{python}", "-c", "print('Second check')"]})
    task_id = start(repository, task_plan=candidate)
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    result = tasks.verify(task_id, repository)
    assert result["ok"]
    logs = [os.path.normcase(item["log"]) for item in result["checks"]]
    assert len(set(logs)) == 2


@pytest.mark.skipif(os.name == "nt", reason="Windows uses Git index mode instead of executable filesystem bits.")
def test_executable_mode_change_invalidates_evidence_and_survives_snapshot(repository):
    task_id, first = ready(repository)
    path = repository / "app.py"
    path.chmod(path.stat().st_mode | 0o111)
    report = tasks.status(task_id, repository)
    assert report["fingerprint"] != first["fingerprint"]
    assert "current_checks_not_passed" in report["blockers"]
    assert tasks.verify(task_id, repository)["ok"]
    packet = tasks.snapshot(task_id, repository)
    copied = Path(packet["path"]) / "app.py"
    assert copied.stat().st_mode & 0o111 == path.stat().st_mode & 0o111
    assert tasks.verify(task_id, repository, packet["snapshot_id"])["ok"]
