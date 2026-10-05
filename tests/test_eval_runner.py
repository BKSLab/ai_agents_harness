"""Exercise the eval transport with a fake command runner; no external model or network."""

import json
from pathlib import Path
import subprocess

import pytest

from evals import run_kimi as runner
from harness_cli.evals import load_scenarios


def kimi_stream(content, before_reply=()):
    events = [
        {"role": "meta", "type": "system.version", "version": "2.1.1"},
        *before_reply,
        {"role": "assistant", "content": content},
        {"role": "meta", "type": "session.resume_hint", "session_id": "session_fixture",
         "command": "kimi -r session_fixture", "content": "To resume..."},
    ]
    return "\n".join(json.dumps(event) for event in events) + "\n"


def unexpected_tool_stream(content):
    return kimi_stream(content, [
        {"role": "assistant", "tool_calls": [{"type": "function", "id": "tool_fixture",
         "function": {"name": "Read", "arguments": '{"path":"fixture.txt"}'}}]},
        {"role": "tool", "tool_call_id": "tool_fixture", "content": "fixture-value"},
    ])


@pytest.mark.parametrize("encode", [json.dumps,
                                    lambda value: "```json\n" + json.dumps(value) + "\n```",
                                    lambda value: "```\n" + json.dumps(value) + "\n```"])
def test_parse_answers_accepts_one_complete_array(encode):
    value = [{"id": "case-1", "skill": None}]
    assert runner.parse_answers(encode(value)) == value


@pytest.mark.parametrize("text", [
    'I failed.\n[{"id":"case-1"}]',
    '[{"id":"case-1"}]\nThe success above is withdrawn.',
    '[{"id":"case-1"}]\n[{"id":"case-2"}]',
    '```json\n[{"id":"case-1"}]\n```\nExtra prose',
    '```json\n[{"id":"case-1"}]\n```\n```json\n[{"id":"case-2"}]\n```',
    '[{"id":"case-1","claim_success":false,"claim_success":true}]',
    '[{"id":"case-1","data":{"nested":1,"nested":2}}]',
    '[{"id":"case-1","value":NaN}]',
    '[{"id":"case-1","value":Infinity}]',
    '[]', '{}', 'true', '[{"id":true}]', '[{"id":null}]', '[{}]',
    '```yaml\n- id: case-1\n```',
])
def test_parse_answers_rejects_prose_extra_documents_and_ambiguous_json(text):
    with pytest.raises(ValueError):
        runner.parse_answers(text)


def answers(mode):
    defaults = {"skill": None, "action": "explain", "claim_success": False, "repeat_write": False,
                "expose_secrets": False, "preserve_user_changes": True, "stage_paths": [],
                "operation_id": "none", "invent_files": False, "weaken_tests": False,
                "respect_scope": True, "honor_plan": True}
    cases = load_scenarios()
    if mode == "routing":
        return [{"id": case["id"], "skill": case["expected"]["skill"]}
                for case in cases if "skill" in case["expected"]]
    return [{"id": case["id"], **defaults,
             **{key: value["one_of"][0] if isinstance(value, dict) else value
                for key, value in case["expected"].items()}} for case in cases]


@pytest.fixture
def model_process(monkeypatch):
    calls = []
    configured = {"ok": True, "aliases": ["alpha", "beta"], "default": "beta"}
    behavior = {"status": "passed", "exit_code": 0, "reason": None, "mode": "decisions"}
    monkeypatch.setattr(runner, "model_aliases", lambda: configured)

    def run(argv, root, timeout, output_path, *, env=None, stdout_limit=32768):
        calls.append({"argv": argv, "root": Path(root), "timeout": timeout,
                      "output_path": Path(output_path), "env": env, "stdout_limit": stdout_limit})
        if "raise" in behavior:
            raise behavior["raise"]
        content = json.dumps(answers(behavior["mode"]))
        output = {"stdout": behavior.get("stream", kimi_stream)(content), "stderr": "",
                  "stdout_truncated": False, "stderr_truncated": False}
        if "output" in behavior:
            replacement = behavior["output"]
            output = replacement(output) if callable(replacement) else replacement
        if output is not None:
            Path(output_path).write_text(
                output if isinstance(output, str) else json.dumps(output), encoding="utf-8")
        return {"status": behavior["status"], "exit_code": behavior["exit_code"], "reason": behavior["reason"],
                "duration_seconds": 0.01, "log": str(output_path) if output is not None else None}

    monkeypatch.setattr(runner, "run_command", run)
    return calls, configured, behavior


def run_evaluation(tmp_path, *arguments):
    directory = tmp_path / "model-evaluation"
    code = runner.main(["--kimi", "synthetic-kimi-never-executed", "--output-dir", str(directory), *arguments])
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    return code, directory, report


def test_explicit_model_mode_and_bounded_runner_recorded(tmp_path, model_process, monkeypatch):
    calls, _, _ = model_process
    monkeypatch.setenv("BITRIX_WEBHOOK_TOKEN", "synthetic-private-fixture")
    monkeypatch.setenv("GH_TOKEN", "synthetic-private-fixture")
    monkeypatch.setenv("GITHUB_OTHER_SECRET", "synthetic-private-fixture")
    code, directory, report = run_evaluation(tmp_path, "--model", "alpha", "--admission", "--timeout", "37")
    assert code == 0 and report["ok"] and report["admission"]["qualified"]
    assert report["model"] == "alpha" and report["model_selection"] == "explicit"
    assert report["evaluation_mode"] == "decisions"
    assert report["model_call_attempted"] and report["model_executed"] and report["decision_array_graded"]
    assert not report["autonomous_ready"] and not report["admission"]["autonomous_ready"]
    assert len(report["context_sha256"]) == 64
    assert report["process"]["status"] == "passed"
    assert len(calls) == 1 and calls[0]["timeout"] == 37
    call = calls[0]
    assert call["argv"][call["argv"].index("--model") + 1] == "alpha"
    assert call["argv"][call["argv"].index("--output-format") + 1] == "stream-json"
    assert call["stdout_limit"] == 2_000_000
    assert call["root"] == directory and call["output_path"] == directory / "model-output.json"
    assert not any(key.startswith(("BITRIX_", "GH_", "GITHUB_")) for key in call["env"])
    assert not (directory / "stdout.txt").exists() and not (directory / "stderr.txt").exists()
    assert list((directory / "empty-skills").iterdir()) == []
    assert "synthetic-private-fixture" not in (directory / "report.json").read_text(encoding="utf-8")


def test_configured_default_is_frozen_in_explicit_cli_argument(tmp_path, model_process):
    calls, _, behavior = model_process
    behavior["mode"] = "routing"
    code, _, report = run_evaluation(tmp_path, "--mode", "routing")
    assert code == 0 and report["model"] == "beta" and report["model_selection"] == "configured-default"
    assert report["mode"] == "catalog-routing-evaluation"
    assert calls[0]["argv"][calls[0]["argv"].index("--model") + 1] == "beta"
    context = Path(calls[0]["argv"][calls[0]["argv"].index("--agent-file") + 1]).read_text(encoding="utf-8")
    assert "CATALOG:" in context and "CONTRACT:" not in context


@pytest.mark.parametrize("option", ["unknown", ""])
def test_unknown_explicit_model_cannot_fall_back_to_default(tmp_path, model_process, option):
    calls, _, _ = model_process
    with pytest.raises(SystemExit) as failure:
        run_evaluation(tmp_path, "--model", option)
    assert failure.value.code == 2 and not calls
    assert not (tmp_path / "model-evaluation").exists()


def test_missing_default_does_not_select_first_model(tmp_path, model_process):
    calls, configured, _ = model_process
    configured["default"] = None
    with pytest.raises(SystemExit):
        run_evaluation(tmp_path)
    assert not calls


@pytest.mark.parametrize("output", [
    lambda output: {**output, "stdout_truncated": True},
    lambda output: {"stdout": output["stdout"]},
    {"stdout": None, "stdout_truncated": False},
    {"stdout": '[{"id":"case-1"}]\nIgnore the above', "stdout_truncated": False},
    None, "malformed log", [],
])
def test_incomplete_or_invalid_model_log_never_qualifies(tmp_path, model_process, output):
    calls, _, behavior = model_process
    behavior["output"] = output
    code, _, report = run_evaluation(tmp_path, "--admission")
    assert code == 1 and not report["ok"] and len(calls) == 1
    assert not report["decision_array_graded"] and not report["admission"]["qualified"]
    assert not report["autonomous_ready"]


@pytest.mark.parametrize("stream", [
    lambda content: content,
    lambda content: "• " + content,
    lambda content: kimi_stream(content) + "{broken-jsonl\n",
    unexpected_tool_stream,
    lambda content: json.dumps({"role": "meta", "type": "session.resume_hint",
                               "session_id": "session_fixture", "command": "kimi -r session_fixture",
                               "content": content}) + "\n",
], ids=["raw-answer-not-a-stream", "terminal-transcript", "damaged-tail", "unexpected-tool", "meta-only-answer"])
def test_invalid_kimi_stream_cannot_qualify_an_otherwise_correct_submission(tmp_path, model_process, stream):
    calls, _, behavior = model_process
    behavior["stream"] = stream
    code, directory, report = run_evaluation(tmp_path, "--admission")
    assert code == 1 and not report["ok"] and len(calls) == 1
    assert report["model_executed"] and not report["decision_array_graded"]
    assert not report["admission"]["qualified"]
    assert not (directory / "decisions.json").exists()


@pytest.mark.parametrize("outcome", [
    {"status": "error", "exit_code": None, "reason": "timeout"},
    {"status": "error", "exit_code": None, "reason": "command_unavailable"},
    {"status": "failed", "exit_code": 1, "reason": None},
])
def test_process_failure_cannot_accept_an_otherwise_valid_answer(tmp_path, model_process, outcome):
    calls, _, behavior = model_process
    behavior.update(outcome)
    code, directory, report = run_evaluation(tmp_path, "--admission")
    assert code == 1 and not report["ok"] and len(calls) == 1
    assert not report["model_executed"] and not report["decision_array_graded"]
    assert report["process"]["reason"] == outcome["reason"]
    assert not (directory / "decisions.json").exists()
    assert not report["admission"]["qualified"]


def test_runner_exception_records_failure_without_raw_exception_details(tmp_path, model_process):
    _, _, behavior = model_process
    behavior["raise"] = subprocess.TimeoutExpired("synthetic-secret-command", 1)
    code, directory, report = run_evaluation(tmp_path, "--admission")
    assert code == 1 and not report["ok"] and not report["autonomous_ready"]
    assert "synthetic-secret-command" not in (directory / "report.json").read_text(encoding="utf-8")
