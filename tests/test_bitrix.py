import argparse
import http.client
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import ssl
import subprocess
import sys
import threading
import urllib.error

import pytest

from bitrix_config import Config, ToolError
from bitrix_http import Client, NoRedirect
from bitrix_state import Journal
from bitrix_cli import execute, main, parser_for


class Response:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class Transport:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def __call__(self, request, **kwargs):
        self.calls.append((request, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Response(outcome)


def test_tls_context_verifies_host_and_certificates(monkeypatch, config):
    import urllib.request
    handlers = []
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: handlers.extend(args) or argparse.Namespace(open=lambda: None))
    Client(config)
    context = handlers[0]._context
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert isinstance(handlers[1], NoRedirect)


@pytest.mark.parametrize("reply", [{}, {"result": None}, {"result": False}, [], b"<html>error</html>"])
def test_invalid_reply_is_not_success(config, reply):
    with pytest.raises(ToolError) as error:
        Client(config, transport=Transport(reply)).call("im.message.add", {}, write=True)
    assert error.value.code == "INVALID_RESPONSE" and error.value.uncertain


def test_read_retries_are_bounded_and_use_timeout(config):
    config.read_retries = 2
    transport = Transport(TimeoutError(), urllib.error.HTTPError("", 503, "", {}, None), {"result": {"tasks": []}})
    sleeps = []
    result = Client(config, transport=transport, sleep=sleeps.append).call("tasks.task.list", {})
    assert result["result"]["tasks"] == []
    assert len(transport.calls) == 3 and sleeps == [1, 2]
    assert all(call[1]["timeout"] == 20 for call in transport.calls)


def test_mutation_timeout_never_retried(config):
    config.read_retries = 3
    transport = Transport(TimeoutError(), {"result": 42})
    with pytest.raises(ToolError) as error:
        Client(config, transport=transport).call("im.message.add", {}, write=True)
    assert error.value.uncertain and not error.value.retryable
    assert len(transport.calls) == 1


def test_incomplete_http_response_is_unknown_for_writes(config):
    transport = Transport(http.client.IncompleteRead(b"partial"))
    with pytest.raises(ToolError) as error:
        Client(config, transport=transport).call("im.message.add", {}, write=True)
    assert error.value.uncertain and len(transport.calls) == 1


def test_http_error_does_not_echo_url_or_api_description(config):
    transport = Transport({"error": "FAILED", "error_description": config.portal + config.token})
    with pytest.raises(ToolError) as error:
        Client(config, transport=transport).call("tasks.task.get", {})
    assert config.portal not in str(error.value) and config.token not in str(error.value)


def test_read_interface_cannot_call_write_method(config):
    transport = Transport()
    with pytest.raises(ToolError, match="capabilities"):
        Client(config, transport=transport).call("im.message.add", {})
    assert not transport.calls


@pytest.mark.parametrize("command,argv", [
    ("send-message", ["chat1", "hello"]),
    ("close-task", ["7"]),
    ("update-task", ["7", '{"TITLE":"new"}']),
    ("create-task", ["title", "description"]),
    ("comment-task", ["7", "hello"]),
])
def test_empty_api_reply_fails_all_mutations(config, command, argv):
    args = parser_for(command).parse_args([*argv, "--operation-id", "operation-1"])
    with pytest.raises(ToolError):
        execute(command, args, config, Client(config, transport=Transport({})))
    assert Journal(config).recent()[0]["state"] == "unknown"


def test_successful_write_replays_receipt_without_second_request(config):
    transport = Transport({"result": 42})
    args = parser_for("send-message").parse_args(["chat1", "hello", "--operation-id", "operation-1"])
    first = execute("send-message", args, config, Client(config, transport=transport))
    second = execute("send-message", args, config, Client(config, transport=transport))
    assert first[0] == second[0] == {"message_id": 42}
    assert not first[1]["replayed"] and second[1]["replayed"]
    assert len(transport.calls) == 1


def test_uncertain_write_blocks_retries(config):
    transport = Transport(TimeoutError())
    args = parser_for("send-message").parse_args(["chat1", "hello", "--operation-id", "operation-1"])
    with pytest.raises(ToolError):
        execute("send-message", args, config, Client(config, transport=transport))
    with pytest.raises(ToolError) as error:
        execute("send-message", args, config, Client(config, transport=transport))
    assert error.value.code == "RECONCILE_REQUIRED" and len(transport.calls) == 1


def test_operation_id_cannot_change_payload(config):
    journal = Journal(config)
    journal.run("operation-1", "im.message.add", {"text": "one"}, lambda: {"message_id": 42})
    with pytest.raises(ToolError) as error:
        journal.run("operation-1", "im.message.add", {"text": "two"}, lambda: {})
    assert error.value.code == "OPERATION_CONFLICT"


def test_concurrent_duplicate_reserves_only_one_write(config):
    journal = Journal(config)
    entered, release = threading.Event(), threading.Event()
    def action():
        entered.set()
        assert release.wait(5)
        return {"message_id": 42}
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(journal.run, "operation-1", "im.message.add", {}, action)
        assert entered.wait(5)
        try:
            with pytest.raises(ToolError) as error:
                journal.run("operation-1", "im.message.add", {}, lambda: pytest.fail("Duplicate write"))
            assert error.value.code == "RECONCILE_REQUIRED"
        finally:
            release.set()
        assert first.result()[0] == {"message_id": 42}


def test_create_participants_and_multiline_text_reach_api(config, tmp_path):
    config.profile = {"users": {"reviewer": 23}, "responsible_id": 11}
    body = {"TITLE": "Fix quotes", "DESCRIPTION": "line1\nline2 `code` $(not-a-command)", "RESPONSIBLE_ID": "reviewer"}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    args = parser_for("create-task").parse_args(["--input", str(path), "--auditor", "reviewer", "--operation-id", "operation-1"])
    transport = Transport({"result": {"task": {"id": "42"}}})
    execute("create-task", args, config, Client(config, transport=transport))
    fields = json.loads(transport.calls[0][0].data)["fields"]
    assert fields["RESPONSIBLE_ID"] == 23 and fields["AUDITORS"] == [23]
    assert fields["DESCRIPTION"] == body["DESCRIPTION"]


@pytest.mark.parametrize("status,completed", [("4", False), ("5", True)])
def test_close_reports_actual_status(config, status, completed):
    args = parser_for("close-task").parse_args(["7", "--operation-id", "operation-1"])
    data, _ = execute("close-task", args, config, Client(config, transport=Transport({"result": {"task": {"id": "7", "status": status}}})))
    assert data["completed"] is completed


def test_wrong_task_id_is_never_success(config):
    args = parser_for("update-task").parse_args(["7", '{"TITLE":"new"}', "--operation-id", "operation-1"])
    with pytest.raises(ToolError):
        execute("update-task", args, config, Client(config, transport=Transport({"result": {"task": {"id": "8"}}})))


def test_comments_require_explicit_boolean_confirmation(config):
    args = parser_for("comment-task").parse_args(["7", "hello", "--operation-id", "operation-1"])
    with pytest.raises(ToolError):
        execute("comment-task", args, config, Client(config, transport=Transport({"result": {"result": "false"}})))


def test_get_task_preserves_comment_loading(config):
    transport = Transport({"result": {"item": {"id": 7, "chatId": 2, "description": "context"}}},
                          {"result": {"messages": [{"author_id": 1, "text": "comment"}, {"author_id": 0, "text": "system"}]}})
    data, _ = execute("get-task", parser_for("get-task").parse_args(["7"]), config, Client(config, transport=transport))
    assert data["comments_loaded"] and len(data["comments"]) == 1
    assert "/rest/api/" in transport.calls[0][0].full_url


def test_pagination_cannot_repeat_same_cursor(config):
    transport = Transport({"result": {"tasks": [{"id": 1}]}, "next": 0})
    with pytest.raises(ToolError, match="Pagination"):
        execute("list-tasks", parser_for("list-tasks").parse_args([]), config, Client(config, transport=transport))


def test_unknown_chat_does_not_make_network_request(config):
    transport = Transport()
    with pytest.raises(ToolError):
        execute("get-messages", parser_for("get-messages").parse_args(["unknown"]), config, Client(config, transport=transport))
    assert not transport.calls


def test_malformed_message_entry_is_a_structured_error(config):
    transport = Transport({"result": {"messages": ["unexpected"]}})
    with pytest.raises(ToolError) as error:
        execute("get-messages", parser_for("get-messages").parse_args(["chat1"]), config, Client(config, transport=transport))
    assert error.value.code == "INVALID_RESPONSE"


def test_config_requires_https_and_split_credentials(monkeypatch):
    monkeypatch.setenv("BITRIX_PORTAL_URL", "https://portal.example.invalid")
    monkeypatch.setenv("BITRIX_WEBHOOK_USER_ID", "11")
    monkeypatch.setenv("BITRIX_WEBHOOK_TOKEN", "fixture-token")
    assert Config.load().webhook_user_id == 11
    monkeypatch.setenv("BITRIX_PORTAL_URL", "http://portal.example.invalid")
    with pytest.raises(ToolError):
        Config.load()


@pytest.mark.parametrize("profile", [{"users": []}, {"chats": []}, {"auditors": "1"}, {"user_id": False},
                                      {"portal_url": "https://portal.example.invalid"}])
def test_invalid_profile_is_a_sanitized_configuration_error(monkeypatch, tmp_path, profile):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setenv("BITRIX_PROFILE", str(path))
    with pytest.raises(ToolError) as error:
        Config.load()
    assert error.value.code == "CONFIG_ERROR"


def test_explicit_invalid_user_does_not_fall_back_to_default(config):
    with pytest.raises(ToolError):
        config.user(0)


def test_cli_redacts_portal_and_token(monkeypatch, capsys, config):
    monkeypatch.setattr(Config, "load", lambda: config)
    transport = Transport({"result": {"messages": [{"text": config.portal + ' ' + config.token}]}})
    code = main("get-messages", ["chat1"], client_factory=lambda cfg: Client(cfg, transport=transport))
    output = capsys.readouterr().out
    assert code == 0 and json.loads(output)["ok"]
    assert config.portal not in output and config.token not in output


def test_missing_environment_is_json_without_traceback():
    script = Path(__file__).resolve().parents[1] / "skills/bitrix-list-tasks/scripts/list_tasks.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 2 and not result.stderr
    assert json.loads(result.stdout)["error"]["code"] == "CONFIG_MISSING"
