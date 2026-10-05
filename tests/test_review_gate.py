"""Review evidence comes from a controller, never an author's success claim or a model exit code."""

import copy
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from harness_cli import review_gate as gate
from harness_cli import tasks


MODEL = "fixture-review-model"
TASK_ID = "review-fixture"


def verdict(required_ids=None):
    return {
        "schema_version": 1,
        **(required_ids or {"snapshot_id": "snapshot-fixture", "fingerprint": "a" * 64,
                           "plan_hash": "b" * 64, "verification_id": "verify-fixture"}),
        "reviewer": MODEL,
        "status": "approved",
        "summary": "The checked change satisfies the recorded acceptance criterion.",
        "findings": [],
        "limitations": [],
    }


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Harness Fixture")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Harness Fixture")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "fixture@example.invalid")

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, timeout=15)

    git("init", "--initial-branch=main")
    git("config", "core.hooksPath", str(tmp_path / "disabled-hooks"))
    git("config", "commit.gpgsign", "false")
    git("config", "core.autocrlf", "false")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    git("add", "--all")
    git("commit", "-m", "fixture baseline")
    tasks.init(TASK_ID, root, "Update the fixture value", mode="standard")
    tasks.set_plan(TASK_ID, root, {
        "schema_version": 1,
        "scope": ["module.py"],
        "acceptance": [{"id": "value", "description": "Exported VALUE is 2", "checks": ["value-check"]}],
        "risks": [{"id": "consumer", "description": "A reader may receive the previous value",
                   "severity": "low", "checks": ["value-check"]}],
        "checks": [{"id": "value-check", "argv": [
            "{python}", "-B", "-c", "import runpy; assert runpy.run_path('module.py')['VALUE'] == 2"
        ], "timeout_seconds": 10}],
    })
    tasks.approve(TASK_ID, root, "Synthetic test owner approved this fixture plan.")
    (root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(gate, "model_aliases", lambda: {
        "ok": True, "aliases": [MODEL, "different-default"], "default": "different-default",
        "credentials_included": False,
    })
    return root


@pytest.fixture
def model_process(monkeypatch):
    """Only the model process is replaced; Git snapshots and planned checks are real local fixtures."""
    calls = []
    behavior = {"status": "passed", "exit_code": 0, "reason": None}

    def run(argv, root, timeout, output_path, *, env=None):
        instruction = json.loads(argv[argv.index("--prompt") + 1])
        call = {"argv": argv, "root": Path(root), "timeout": timeout, "output_path": Path(output_path),
                "instruction": instruction, "env": env}
        calls.append(call)
        answer = verdict(instruction["required_ids"])
        if "mutate_answer" in behavior:
            behavior["mutate_answer"](answer, call)
        output = {"stdout": json.dumps(answer), "stderr": "",
                  "stdout_truncated": False, "stderr_truncated": False}
        if "output" in behavior:
            replacement = behavior["output"]
            output = replacement(output) if callable(replacement) else replacement
        if output is not None:
            Path(output_path).write_text(
                output if isinstance(output, str) else json.dumps(output), encoding="utf-8"
            )
        if "during_process" in behavior:
            behavior["during_process"](call)
        return {"status": behavior["status"], "exit_code": behavior["exit_code"],
                "reason": behavior["reason"], "duration_seconds": 0.01,
                "log": str(output_path) if output is not None else None}

    monkeypatch.setattr(gate, "run_command", run)
    return calls, behavior


def run_review(project):
    return gate.review_gate(TASK_ID, project, MODEL, timeout=30, executable="synthetic-kimi-never-executed")


def assert_no_approval(project):
    state = tasks.Store(project).load(TASK_ID)
    assert not any(review["status"] == "approved" for review in state["reviews"])
    assert not tasks.status(TASK_ID, project)["ready"]


def test_model_aliases_returns_names_without_provider_secrets(tmp_path, monkeypatch):
    config = tmp_path / "kimi.toml"
    secret = "synthetic-provider-secret-for-alias-test"
    endpoint = "https://model-fixture.example.invalid"
    config.write_text(
        f'default_model = "beta"\n[models.beta]\nprovider = "fixture"\nmodel = "second"\n'
        f'[models.alpha]\nprovider = "fixture"\nmodel = "first"\n'
        f'[providers.fixture]\napi_key = "{secret}"\nbase_url = "{endpoint}"\n', encoding="utf-8"
    )
    monkeypatch.setattr(gate, "agent_targets", lambda: {"kimi": config})
    result = gate.model_aliases()
    assert result == {"ok": True, "aliases": ["alpha", "beta"], "default": "beta", "credentials_included": False}
    assert secret not in json.dumps(result) and endpoint not in json.dumps(result)


def test_model_aliases_missing_configuration_does_not_probe_other_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "agent_targets", lambda: {"kimi": tmp_path / "absent.toml"})
    assert gate.model_aliases() == {"ok": False, "aliases": [], "error": "kimi_not_configured"}


@pytest.mark.parametrize("encode", [json.dumps, yaml.safe_dump,
                                    lambda value: "```json\n" + json.dumps(value) + "\n```"])
def test_parse_verdict_accepts_one_complete_schema_document(encode):
    expected = verdict()
    assert gate.parse_verdict(encode(expected)) == expected


@pytest.mark.parametrize("text", [
    "status: approved", "[]", "true", "I cannot approve this patch.\n" + json.dumps(verdict()),
    "The checks failed.\n```json\n" + json.dumps(verdict()) + "\n```",
    json.dumps(verdict()) + "\nThe approval above is withdrawn.",
    yaml.safe_dump(verdict()) + "\n---\n" + yaml.safe_dump(verdict()),
    yaml.safe_dump(verdict()) + "\nstatus: blocked\n",
    json.dumps(verdict())[:-1] + ', "status": "blocked"}',
    json.dumps({**verdict(), "authorized_to_push": True}),
    json.dumps({**verdict(), "status": "almost_approved"}),
    json.dumps({**verdict(), "fingerprint": "not-a-snapshot-fingerprint"}),
])
def test_parse_verdict_rejects_duplicate_keys_prose_and_schema_shortcuts(text):
    with pytest.raises(ValueError):
        gate.parse_verdict(text)


@pytest.mark.parametrize("model", [None, "", "unknown-model"])
def test_explicit_configured_model_required_without_fallback(project, model_process, model):
    calls, _ = model_process
    with pytest.raises(ValueError, match="model|alias"):
        gate.review_gate(TASK_ID, project, model, executable="synthetic-kimi-never-executed")
    assert calls == []
    assert not tasks.Store(project).load(TASK_ID)["verifications"]
    assert_no_approval(project)


def test_approved_review_is_bound_to_controller_receipt_snapshot_and_selected_model(project, model_process, monkeypatch):
    calls, _ = model_process
    monkeypatch.setenv("BITRIX_WEBHOOK_TOKEN", "synthetic-private-fixture")
    monkeypatch.setenv("GH_TOKEN", "synthetic-github-fixture")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-github-fixture")
    report = run_review(project)
    assert report["ok"] and report["status"] == "approved"
    assert len(calls) == 1
    call = calls[0]
    argv = call["argv"]
    assert argv[argv.index("--model") + 1] == MODEL
    assert Path(argv[argv.index("--agent-file") + 1]).name == "reviewer.md"
    assert list(Path(argv[argv.index("--skills-dir") + 1]).iterdir()) == []
    assert call["root"] != project and call["timeout"] == 30
    assert not any(key.startswith("BITRIX_") or key in {"GH_TOKEN", "GITHUB_TOKEN"} for key in call["env"])
    required = call["instruction"]["required_ids"]
    receipt_path = Path(call["instruction"]["verification_receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    state = tasks.Store(project).load(TASK_ID)
    assert state["reviews"][-1]["verification_id"] == required["verification_id"] == receipt["id"]
    assert receipt["snapshot_id"] == required["snapshot_id"] and receipt["status"] == "passed"
    assert receipt["plan_hash"] == state["plan_hash"] == required["plan_hash"]
    assert receipt["fingerprint"] == required["fingerprint"]
    assert receipt_path.is_relative_to(tasks.Store(project).directory(TASK_ID))
    assert not receipt_path.is_relative_to(project)
    assert tasks.status(TASK_ID, project)["ready"]


@pytest.mark.parametrize("status,exit_code,reason", [
    ("failed", 1, None), ("error", None, "timeout"), ("error", None, "command_unavailable"),
])
def test_non_successful_process_cannot_approve_even_with_approved_stdout(project, model_process, status, exit_code, reason):
    calls, behavior = model_process
    behavior.update(status=status, exit_code=exit_code, reason=reason)
    report = run_review(project)
    assert len(calls) == 1 and not report["ok"] and report["status"] == "blocked"
    assert report["reason"] == "reviewer_process_failed"
    assert_no_approval(project)


@pytest.mark.parametrize("output", [
    None, "{broken-json", [], {}, lambda output: {"stdout": output["stdout"]},
    {"stdout": {}, "stdout_truncated": False}, {"stdout": "", "stdout_truncated": False},
    lambda output: {**output, "stdout_truncated": True},
    {"stdout": '{"status":"approved"}', "stdout_truncated": False},
], ids=["missing-log", "invalid-json", "list-envelope", "empty-envelope", "missing-truncation-flag",
        "wrong-stdout-type", "empty-stdout", "truncated-valid-approval", "incomplete-verdict"])
def test_missing_truncated_or_malformed_model_output_blocks_without_approval(project, model_process, output):
    calls, behavior = model_process
    behavior["output"] = output
    report = run_review(project)
    assert len(calls) == 1 and not report["ok"] and report["status"] == "blocked"
    assert_no_approval(project)


@pytest.mark.parametrize("field,value", [
    ("snapshot_id", "snapshot-not-created-by-controller"),
    ("verification_id", "verify-not-created-by-controller"),
    ("fingerprint", "d" * 64), ("plan_hash", "e" * 64), ("reviewer", "different-default"),
])
def test_model_cannot_substitute_receipt_plan_snapshot_or_reviewer(project, model_process, field, value):
    _, behavior = model_process
    behavior["mutate_answer"] = lambda answer, _: answer.update({field: value})
    report = run_review(project)
    assert not report["ok"] and report["status"] == "blocked"
    assert_no_approval(project)


def test_source_verification_receipt_cannot_replace_snapshot_verification(project, model_process):
    _, behavior = model_process

    def use_source_receipt(answer, _):
        state = tasks.Store(project).load(TASK_ID)
        answer["verification_id"] = next(record["id"] for record in state["verifications"]
                                         if record["snapshot_id"] is None)

    behavior["mutate_answer"] = use_source_receipt
    report = run_review(project)
    assert not report["ok"] and report["status"] == "blocked"
    assert_no_approval(project)


@pytest.mark.parametrize("where", ["source", "snapshot"])
def test_code_changed_during_reviewer_process_invalidates_approval(project, model_process, where):
    _, behavior = model_process

    def change_file(call):
        root = project if where == "source" else call["root"]
        (root / "module.py").write_text("VALUE = 3\n", encoding="utf-8")

    behavior["during_process"] = change_file
    report = run_review(project)
    assert not report["ok"] and report["status"] == "blocked"
    assert_no_approval(project)


def test_failed_source_checks_do_not_invoke_model(project, model_process):
    calls, _ = model_process
    (project / "module.py").write_text("VALUE = 9\n", encoding="utf-8")
    report = run_review(project)
    assert not report["ok"] and report["reason"] == "source_checks_failed"
    assert not calls and not tasks.Store(project).load(TASK_ID).get("review_gate_attempts")
    assert_no_approval(project)


def test_failed_snapshot_checks_do_not_invoke_model(project, model_process, monkeypatch):
    calls, _ = model_process
    original = tasks.run_command

    def fail_snapshot(argv, root, timeout, output_path, **kwargs):
        if Path(root) != project:
            return {"status": "failed", "exit_code": 1, "reason": None, "duration_seconds": 0.01, "log": None}
        return original(argv, root, timeout, output_path, **kwargs)

    monkeypatch.setattr(tasks, "run_command", fail_snapshot)
    report = run_review(project)
    assert not report["ok"] and report["reason"] == "snapshot_checks_failed"
    assert not calls and not tasks.Store(project).load(TASK_ID).get("review_gate_attempts")
    assert_no_approval(project)


def test_attempt_limit_is_reloaded_after_snapshot_verification(project, model_process, monkeypatch):
    calls, _ = model_process
    original = tasks.verify

    def another_controller_used_budget(task_id, root, snapshot_id=None):
        receipt = original(task_id, root, snapshot_id)
        if snapshot_id:
            store = tasks.Store(root)
            state = store.load(task_id)
            state.setdefault("review_gate_attempts", {})[state["plan_hash"]] = 3
            store.save(state, "fixture_concurrent_review_attempts")
        return receipt

    monkeypatch.setattr(tasks, "verify", another_controller_used_budget)
    with pytest.raises(ValueError, match="attempt|review|Three"):
        run_review(project)
    state = tasks.Store(project).load(TASK_ID)
    assert state["review_gate_attempts"][state["plan_hash"]] == 3
    assert not calls
    assert_no_approval(project)


@pytest.mark.parametrize("change", ["plan", "source"])
def test_changed_plan_or_code_after_checks_prevents_quota_consumption(project, model_process, monkeypatch, change):
    calls, _ = model_process
    original = tasks.verify

    def alter_after_verification(task_id, root, snapshot_id=None):
        receipt = original(task_id, root, snapshot_id)
        if snapshot_id:
            if change == "source":
                (project / "module.py").write_text("VALUE = 3\n", encoding="utf-8")
            else:
                plan = copy.deepcopy(tasks.Store(root).load(task_id)["plan"])
                plan["acceptance"][0]["description"] += " in a newly approved plan"
                tasks.set_plan(task_id, root, plan)
                tasks.approve(task_id, root, "Synthetic owner approved the revised fixture plan.")
        return receipt

    monkeypatch.setattr(tasks, "verify", alter_after_verification)
    with pytest.raises(ValueError):
        run_review(project)
    assert not calls and not tasks.Store(project).load(TASK_ID).get("review_gate_attempts")
    assert_no_approval(project)
