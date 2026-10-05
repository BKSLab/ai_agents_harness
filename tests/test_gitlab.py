import argparse
import http.client
import io
import json
import ssl
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from bitrix_state import Journal as BitrixJournal
from gitlab_config import Config, ToolError
from gitlab_http import Client, MAX_LOG_BYTES, MAX_RESPONSE_BYTES, NoRedirect
from gitlab_state import Journal
from gitlab_cli import PUSH_RULE_FIELDS, collect, execute, main, parser_for


SHA = "a" * 40


class Response:
    def __init__(self, body):
        self.body = io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.body.close()

    def read(self, limit):
        return self.body.read(limit)


class Transport:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def __call__(self, request, **kwargs):
        self.calls.append((request, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return Response(outcome)


@pytest.fixture
def glconfig():
    return Config("https://git.example.invalid", "fixture-token", read_retries=0)


def args(command, *values):
    return parser_for(command).parse_args(["--project", "group/project", *values])


def run(command, glconfig, transport, *values):
    return execute(command, args(command, *values), glconfig, Client(glconfig, transport=transport))


def project_reply(**overrides):
    return {"id": 1, "default_branch": "main", "visibility": "private",
            "only_allow_merge_if_pipeline_succeeds": True, "allow_merge_on_skipped_pipeline": False,
            "approvals_before_merge": 0, **overrides}


def approval_rule(**overrides):
    return {"id": 1, "rule_type": "regular", "approvals_required": 2,
            "protected_branches": [], "applies_to_all_protected_branches": False, **overrides}


def approval_settings_reply(**overrides):
    return {"disable_overriding_approvers_per_merge_request": True, **overrides}


def audit_transport(project=None, push=None, branches=None, approvals=None, approval_settings=None):
    return Transport(project if project is not None else project_reply(),
                     push if push is not None else {"id": 1, "prevent_secrets": True},
                     branches if branches is not None else [{"name": "main", "allow_force_push": False}],
                     approvals if approvals is not None else [approval_rule()],
                     approval_settings if approval_settings is not None else approval_settings_reply())


def checks(data):
    return {check["id"]: check["result"] for check in data["checks"]}


def test_tls_verified_and_redirects_disabled(monkeypatch, glconfig):
    handlers = []
    monkeypatch.setattr("urllib.request.build_opener",
                        lambda *items: handlers.extend(items) or argparse.Namespace(open=lambda: None))
    Client(glconfig)
    assert handlers[0]._context.check_hostname
    assert handlers[0]._context.verify_mode == ssl.CERT_REQUIRED
    assert isinstance(handlers[1], NoRedirect)
    assert handlers[1].redirect_request(None, None, 302, "", {}, "https://other.invalid") is None


def config_error_output(monkeypatch, capsys, host, opt_in):
    monkeypatch.setenv("GITLAB_HOST", host)
    monkeypatch.setenv("GITLAB_TOKEN", "fixture-token")
    if opt_in is None:
        monkeypatch.delenv("GITLAB_ALLOW_INSECURE_HTTP", raising=False)
    else:
        monkeypatch.setenv("GITLAB_ALLOW_INSECURE_HTTP", opt_in)
    clients = []

    def client_factory(config):
        clients.append(config)
        raise AssertionError("Invalid configuration must fail before constructing a network client")

    code = main("ci", ["--project", "group/project", "--action", "pipelines"], client_factory=client_factory)
    output = capsys.readouterr()
    body = json.loads(output.out)
    assert code == 2 and not body["ok"]
    assert body["error"]["code"] == "CONFIG_ERROR"
    assert not body["error"]["outcome_unknown"]
    assert not clients and not output.err
    assert host not in output.out and "fixture-token" not in output.out
    assert "fixture-user" not in output.out and "fixture-password" not in output.out
    assert "git.example.invalid" not in output.out
    return body


@pytest.mark.parametrize("opt_in", [None, "", "0", "true", "True", "yes", "on", " 1", "1 ", "01"])
def test_http_requires_exact_explicit_opt_in(monkeypatch, capsys, opt_in):
    body = config_error_output(monkeypatch, capsys, "http://git.example.invalid", opt_in)
    assert "GITLAB_ALLOW_INSECURE_HTTP=1" in body["error"]["message"]


def test_http_is_allowed_with_exact_opt_in_and_preserves_redaction(monkeypatch, capsys):
    monkeypatch.setenv("GITLAB_HOST", "http://git.example.invalid:8080/")
    monkeypatch.setenv("GITLAB_TOKEN", "fixture-token")
    monkeypatch.setenv("GITLAB_ALLOW_INSECURE_HTTP", "1")
    config = Config.load()
    assert config.host == "http://git.example.invalid:8080"
    transport = Transport(b"HTTP://GIT.EXAMPLE.INVALID:8080 fixture-token")
    code = main("ci", ["--project", "group/project", "--action", "job-log", "7"],
                client_factory=lambda cfg: Client(cfg, transport=transport))
    output = capsys.readouterr()
    assert code == 0 and not output.err
    assert json.loads(output.out)["data"]["log"] == "[REDACTED] [REDACTED]"
    assert transport.calls[0][0].full_url == "http://git.example.invalid:8080/api/v4/projects/group%2Fproject/jobs/7/trace"


@pytest.mark.parametrize("opt_in", [None, "0", "1", "true"])
def test_https_remains_verified_regardless_of_http_opt_in(monkeypatch, opt_in):
    monkeypatch.setenv("GITLAB_HOST", "https://git.example.invalid")
    monkeypatch.setenv("GITLAB_TOKEN", "fixture-token")
    if opt_in is not None:
        monkeypatch.setenv("GITLAB_ALLOW_INSECURE_HTTP", opt_in)
    handlers = []
    monkeypatch.setattr("urllib.request.build_opener",
                        lambda *items: handlers.extend(items) or argparse.Namespace(open=lambda: None))
    Client(Config.load())
    assert handlers[0]._context.check_hostname
    assert handlers[0]._context.verify_mode == ssl.CERT_REQUIRED
    assert isinstance(handlers[1], NoRedirect)


@pytest.mark.parametrize("host", [
    "ftp://git.example.invalid",
    "//git.example.invalid",
    "http://fixture-user:fixture-password@git.example.invalid",
    "https://fixture-user:fixture-password@git.example.invalid",
    "http://@git.example.invalid",
    "http://git.example.invalid/api",
    "https://git.example.invalid/api",
    "http://git.example.invalid?query=fixture-token",
    "http://git.example.invalid#fixture-token",
    "http://git.example.invalid:bad",
    "https://git.example.invalid:65536",
    "http://[::1",
    "https://[::1",
    "http://[not-an-ipv6-address]",
    "http://git.example.invalid\n",
])
def test_http_opt_in_does_not_allow_invalid_urls_or_leak_configuration(monkeypatch, capsys, host):
    config_error_output(monkeypatch, capsys, host, "1")


@pytest.mark.parametrize("method,options", [
    ("POST", {}), ("PUT", {}), ("GET", {"write": True}), ("DELETE", {"write": True}),
    ("GET", {"payload": {}}), ("POST", {"write": True, "raw": True}),
])
def test_http_capabilities_cannot_retry_mutations_as_reads(glconfig, method, options):
    transport = Transport()
    with pytest.raises(ToolError, match="capabilities"):
        Client(glconfig, transport=transport).request(method, "/projects/1", **options)
    assert not transport.calls


def test_read_retry_bounded_and_no_credentials_in_errors(glconfig):
    glconfig.read_retries = 2
    transport = Transport(TimeoutError(glconfig.token),
                          urllib.error.HTTPError(glconfig.host, 503, glconfig.token, {}, None), [])
    sleeps = []
    assert Client(glconfig, transport=transport, sleep=sleeps.append).request("GET", "/projects/1/pipelines") == []
    assert len(transport.calls) == 3 and sleeps == [1, 2]
    assert all(call[1]["timeout"] == glconfig.timeout for call in transport.calls)


@pytest.mark.parametrize("failure", [TimeoutError(), http.client.IncompleteRead(b"partial"),
                                      urllib.error.HTTPError("https://fixture.invalid", 503, "", {}, None)])
def test_write_unknown_blocks_second_attempt(glconfig, failure):
    glconfig.read_retries = 3
    transport = Transport(failure)
    with pytest.raises(ToolError) as first:
        run("ci", glconfig, transport, "--action", "trigger", "main", "--operation-id", "operation-1")
    assert first.value.uncertain and not first.value.retryable
    with pytest.raises(ToolError) as second:
        run("ci", glconfig, transport, "--action", "trigger", "main", "--operation-id", "operation-1")
    assert second.value.code == "RECONCILE_REQUIRED" and second.value.uncertain
    assert Journal(glconfig).recent()[0]["state"] == "unknown"
    assert len(transport.calls) == 1


def test_empty_push_rule_is_valid_only_for_nullable_read(glconfig):
    assert Client(glconfig, transport=Transport(b"null")).request("GET", "/projects/1/push_rule", allow_null=True) is None
    with pytest.raises(ToolError) as error:
        Client(glconfig, transport=Transport(b"null")).request("GET", "/projects/1")
    assert error.value.code == "INVALID_RESPONSE"
    result, _ = run("project-info", glconfig, Transport(project_reply(), b"null", [], [], approval_settings_reply()))
    assert result["push_rules"] is None


@pytest.mark.parametrize("body", [b"<html>error</html>", b"null", b"false", b"x" * (MAX_RESPONSE_BYTES + 1)],
                         ids=["invalid-json", "null", "boolean", "oversized"])
def test_invalid_write_response_is_unknown(glconfig, body):
    with pytest.raises(ToolError) as error:
        Client(glconfig, transport=Transport(body)).request("POST", "/projects/1/pipeline", write=True)
    assert error.value.code == "INVALID_RESPONSE" and error.value.uncertain


def test_trace_returns_bounded_prefix_and_labels_it(glconfig):
    text = b"START\n" + b"x" * MAX_LOG_BYTES + b"\nEND"
    data, meta = run("ci", glconfig, Transport(text), "--action", "job-log", "7")
    assert data["log"] == text[:MAX_LOG_BYTES].decode()
    assert meta == {"truncated": True, "log_segment": "prefix"}
    _, meta = run("ci", glconfig, Transport(b"whole log"), "--action", "job-log", "7")
    assert meta == {"truncated": False, "log_segment": "complete"}


@pytest.mark.parametrize("limit,total", [(1, 0), (1, 1), (1, 2), (100, 100), (100, 101), (500, 500), (500, 501)])
def test_pagination_reports_actual_truncation(glconfig, limit, total):
    pages = [[{"id": value} for value in range(start, min(start + 100, total))]
             for start in range(0, total, 100)]
    if total % 100 == 0:
        pages.append([])
    transport = Transport(*pages)
    data, truncated = collect(Client(glconfig, transport=transport), "/projects/1/pipelines", {}, limit)
    assert len(data) == min(limit, total) and truncated is (total > limit)
    assert [parse_qs(urlsplit(call[0].full_url).query)["page"] for call in transport.calls] == [
        [str(index + 1)] for index in range(len(transport.calls))]
    assert len(transport.calls) <= 6


@pytest.mark.parametrize("command,values", [
    ("mr", ["--action", "merge", "7", "--operation-id", "operation-1"]),
    ("mr", ["--action", "approve", "7", "--sha", "bad", "--operation-id", "operation-1"]),
    ("mr", ["--action", "approve", "7", "--sha", SHA, "--operation-id", "bad"]),
    ("mr", ["--action", "show", "0"]),
    ("mr", ["--action", "show", "7", "--input", "missing-file"]),
    ("mr", ["--action", "list", "7"]),
    ("mr", ["--action", "create", "--operation-id", "operation-1"]),
    ("mr", ["--action", "list", "--limit", "501"]),
    ("ci", ["--action", "trigger", "bad ref", "--operation-id", "operation-1"]),
    ("ci", ["--action", "pipelines", "unexpected"]),
    ("ci", ["--action", "cancel", "7"]),
    ("ci", ["--action", "pipeline", "-1"]),
])
def test_invalid_arguments_fail_before_network(glconfig, command, values):
    transport = Transport()
    with pytest.raises(ToolError) as error:
        run(command, glconfig, transport, *values)
    assert error.value.code in ("INVALID_INPUT", "OPERATION_ID_REQUIRED")
    assert not transport.calls


def test_merge_binds_sha_and_replay_conflicts_on_new_head(glconfig):
    transport = Transport({"iid": 7, "state": "merged", "merge_commit_sha": "b" * 40})
    values = ["--action", "merge", "7", "--sha", SHA, "--operation-id", "operation-1"]
    first, meta = run("mr", glconfig, transport, *values)
    assert first["sha"] == SHA and not meta["replayed"]
    assert json.loads(transport.calls[0][0].data) == {"sha": SHA}
    assert run("mr", glconfig, transport, *values)[1]["replayed"]
    values[4] = "c" * 40
    with pytest.raises(ToolError) as error:
        run("mr", glconfig, transport, *values)
    assert error.value.code == "OPERATION_CONFLICT"
    assert len(transport.calls) == 1


def test_stale_sha_is_clean_rejection_without_retry(glconfig):
    transport = Transport(urllib.error.HTTPError(glconfig.host, 409, glconfig.token, {}, None))
    with pytest.raises(ToolError) as error:
        run("mr", glconfig, transport, "--action", "merge", "7", "--sha", SHA, "--operation-id", "operation-1")
    assert error.value.code == "API_REJECTED" and not error.value.uncertain
    assert glconfig.host not in str(error.value) and glconfig.token not in str(error.value)
    assert Journal(glconfig).recent()[0]["state"] == "failed"
    assert len(transport.calls) == 1


def test_approval_binds_actor_and_survives_token_rotation(glconfig):
    transport = Transport({"id": 11}, {"iid": 7, "approved_by": [{"user": {"id": 11}}]},
                          {"id": 11}, {"id": 12})
    values = ["--action", "approve", "7", "--sha", SHA, "--operation-id", "operation-1"]
    first, _ = run("mr", glconfig, transport, *values)
    assert first == {"iid": 7, "approved": True, "sha": SHA, "actor_id": 11}
    assert json.loads(transport.calls[1][0].data) == {"sha": SHA}
    glconfig.token = "rotated-fixture-token"
    second, meta = run("mr", glconfig, transport, *values)
    assert first == second and meta["replayed"]
    with pytest.raises(ToolError) as error:
        run("mr", glconfig, transport, *values)
    assert error.value.code == "OPERATION_CONFLICT"
    assert sum(call[0].method == "POST" for call in transport.calls) == 1


@pytest.mark.parametrize("body", [{"iid": 7}, {"iid": 8}, {"iid": 7, "approved_by": []},
                                   {"iid": 7, "approved_by": [{"user": {"id": 12}}]}])
def test_approval_does_not_claim_success_without_current_actor(glconfig, body):
    with pytest.raises(ToolError) as error:
        run("mr", glconfig, Transport({"id": 11}, body), "--action", "approve", "7",
            "--sha", SHA, "--operation-id", "operation-1")
    assert error.value.uncertain
    assert Journal(glconfig).recent()[0]["state"] == "unknown"


def test_approval_boolean_user_id_does_not_confirm_actor_one(glconfig):
    with pytest.raises(ToolError) as error:
        run("mr", glconfig, Transport({"id": 1}, {"iid": 7, "approved_by": [{"user": {"id": True}}]}),
            "--action", "approve", "7", "--sha", SHA, "--operation-id", "operation-1")
    assert error.value.code == "POSTCONDITION_FAILED" and error.value.uncertain


@pytest.mark.parametrize("action,body", [("retry", {"id": 8}), ("cancel", {"id": 8}),
                                        ("trigger", {"id": 8, "ref": "unexpected"})])
def test_pipeline_receipt_confirms_requested_object(glconfig, action, body):
    value = "main" if action == "trigger" else "7"
    with pytest.raises(ToolError) as error:
        run("ci", glconfig, Transport(body), "--action", action, value, "--operation-id", "operation-1")
    assert error.value.uncertain and Journal(glconfig).recent()[0]["state"] == "unknown"


def test_create_confirms_branches_and_preserves_description(glconfig, tmp_path):
    payload = {"source_branch": "feature/work", "target_branch": "main", "title": "Fix checks",
               "description": "line 1\n`quoted` $(not-a-command)"}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    transport = Transport({"iid": 7, "state": "opened", "source_branch": "feature/work", "target_branch": "wrong"})
    with pytest.raises(ToolError) as error:
        run("mr", glconfig, transport, "--action", "create", "--input", str(path), "--operation-id", "operation-1")
    assert error.value.code == "POSTCONDITION_FAILED" and error.value.uncertain
    assert json.loads(transport.calls[0][0].data)["description"] == payload["description"]


@pytest.mark.parametrize("extra", ['"title":"different"', '"description":NaN',
                                    '"description":Infinity', '"unexpected":true'])
def test_create_rejects_ambiguous_or_unsupported_json_before_network(glconfig, tmp_path, extra):
    path = tmp_path / "input.json"
    path.write_text('{"source_branch":"feature","target_branch":"main","title":"reviewed",' + extra + '}',
                    encoding="utf-8")
    transport = Transport()
    with pytest.raises(ToolError) as error:
        run("mr", glconfig, transport, "--action", "create", "--input", str(path), "--operation-id", "operation-1")
    assert error.value.code == "INVALID_INPUT" and not transport.calls


def test_receipts_are_redacted_before_storage_and_on_replay(glconfig, config):
    text = f"{glconfig.host.upper()} {glconfig.token}"
    transport = Transport({"id": 7, "status": text, "ref": text})
    data, _ = run("ci", glconfig, transport, "--action", "retry", "7", "--operation-id", "operation-1")
    assert data["status"] == "[REDACTED] [REDACTED]"
    journal = Journal(glconfig)
    stored = journal.path.read_bytes()
    assert glconfig.token.encode() not in stored and glconfig.host.upper().encode() not in stored
    replay, meta = run("ci", glconfig, transport, "--action", "retry", "7", "--operation-id", "operation-1")
    assert replay == data and meta["replayed"] and len(transport.calls) == 1
    # Both services can use the common table without sharing operation identities.
    assert BitrixJournal(config).run("operation-1", "fixture", {}, lambda: {"id": 9})[0] == {"id": 9}


def test_audit_combines_all_matching_and_inherited_rules(glconfig):
    branches = [{"name": "main", "allow_force_push": False},
                {"name": "*", "allow_force_push": True, "inherited": True}]
    data, meta = run("repo-check", glconfig, audit_transport(branches=branches))
    assert checks(data)["force_push_blocked"] == "fail" and not data["passed"]
    assert data["complete"] and not meta["partial"]


def test_audit_requires_successful_not_skipped_pipeline(glconfig):
    data, _ = run("repo-check", glconfig, audit_transport(project=project_reply(allow_merge_on_skipped_pipeline=True)))
    assert checks(data)["merge_requires_pipeline"] == "fail"


def test_audit_uses_actual_approval_rule_scope_not_deprecated_count(glconfig):
    data, _ = run("repo-check", glconfig, audit_transport())
    assert data["passed"] and checks(data)["approvals_required"] == "ok"
    data, _ = run("repo-check", glconfig, audit_transport(project=project_reply(approvals_before_merge=99),
                  approvals=[approval_rule(protected_branches=[{"name": "release/*"}])]))
    assert checks(data)["approvals_required"] == "fail"


def test_audit_all_protected_rule_applies_to_default(glconfig):
    data, _ = run("repo-check", glconfig, audit_transport(approvals=[approval_rule(applies_to_all_protected_branches=True)]))
    assert checks(data)["approvals_required"] == "ok"


@pytest.mark.parametrize("rule_type", ["regular", "any_approver"])
@pytest.mark.parametrize("disabled,expected", [(True, "ok"), (False, "fail")])
def test_audit_requires_approval_rule_overrides_to_be_disabled(glconfig, rule_type, disabled, expected):
    transport = audit_transport(approvals=[approval_rule(rule_type=rule_type)],
                                approval_settings=approval_settings_reply(disable_overriding_approvers_per_merge_request=disabled))
    data, meta = run("repo-check", glconfig, transport)
    assert checks(data)["approvals_required"] == expected
    assert data["passed"] is disabled and data["complete"] and not meta["partial"]
    assert transport.calls[-1][0].method == "GET"
    assert urlsplit(transport.calls[-1][0].full_url).path == "/api/v4/projects/group%2Fproject/approvals"


@pytest.mark.parametrize("settings", [{}, {"disable_overriding_approvers_per_merge_request": None},
                                       {"disable_overriding_approvers_per_merge_request": "true"},
                                       {"disable_overriding_approvers_per_merge_request": 1}])
def test_unknown_approval_override_setting_is_partial(glconfig, settings):
    data, meta = run("repo-check", glconfig, audit_transport(approval_settings=settings))
    assert checks(data)["approvals_required"] == "warn"
    assert not data["complete"] and not data["passed"] and meta["partial"]
    assert not meta["unavailable"]


@pytest.mark.parametrize("status", [403, 404])
def test_unavailable_approval_settings_are_partial(glconfig, status):
    unavailable = urllib.error.HTTPError(glconfig.host, status, glconfig.token, {}, None)
    data, meta = run("repo-check", glconfig, audit_transport(approval_settings=unavailable))
    assert checks(data)["approvals_required"] == "warn"
    assert not data["complete"] and not data["passed"] and meta["partial"]
    assert meta["unavailable"] == ["approval_settings"]


def test_no_required_approval_rule_still_fails_with_unknown_override_setting(glconfig):
    data, meta = run("repo-check", glconfig, audit_transport(approvals=[], approval_settings={}))
    assert checks(data)["approvals_required"] == "fail"
    assert not data["passed"] and not data["complete"] and meta["partial"]


def test_project_info_whitelists_approval_settings(glconfig):
    settings = approval_settings_reply(unrelated={"fixture": "value"}, approvals_before_merge=99)
    data, meta = run("project-info", glconfig, audit_transport(approval_settings=settings))
    assert data["approval_settings"] == approval_settings_reply()
    assert not meta["partial"]


@pytest.mark.parametrize("status", [403, 404])
def test_project_info_marks_approval_settings_unavailable(glconfig, status):
    unavailable = urllib.error.HTTPError(glconfig.host, status, glconfig.token, {}, None)
    data, meta = run("project-info", glconfig, audit_transport(approval_settings=unavailable))
    assert data["approval_settings"] is None
    assert meta["partial"] and meta["unavailable"] == ["approval_settings"]


@pytest.mark.parametrize("status", [403, 404])
def test_unavailable_approvals_are_partial_not_absent(glconfig, status):
    unavailable = urllib.error.HTTPError(glconfig.host, status, glconfig.token, {}, None)
    data, meta = run("repo-check", glconfig, audit_transport(approvals=unavailable))
    assert checks(data)["approvals_required"] == "warn"
    assert not data["complete"] and not data["passed"]
    assert meta["partial"] and meta["unavailable"] == ["approval_rules"]


def test_unauthorized_optional_resource_is_authentication_error(glconfig):
    with pytest.raises(ToolError) as error:
        run("repo-check", glconfig, audit_transport(approvals=urllib.error.HTTPError("", 401, "", {}, None)))
    assert error.value.code == "ACCESS_DENIED"


def test_truncated_protection_cannot_prove_force_push_blocked(glconfig):
    branches = [{"name": "*", "allow_force_push": False} for _ in range(501)]
    transport = Transport(project_reply(), {"id": 1, "prevent_secrets": True},
                          *[branches[start:start + 100] for start in range(0, 501, 100)], [approval_rule()], approval_settings_reply())
    data, meta = run("repo-check", glconfig, transport)
    assert checks(data)["force_push_blocked"] == "warn"
    assert not data["passed"] and not data["complete"] and meta["truncated"] and meta["partial"]


def test_disabled_push_rule_record_does_not_pass(glconfig):
    disabled = {key: False for key in PUSH_RULE_FIELDS}
    disabled.update(id=1, max_file_size=0)
    disabled.update({key: "" for key in PUSH_RULE_FIELDS if key.endswith("_regex")})
    data, _ = run("repo-check", glconfig, audit_transport(push=disabled))
    assert checks(data)["push_rules_enabled"] == "fail"


def test_incomplete_settings_are_not_a_successful_audit(glconfig):
    project = project_reply()
    del project["allow_merge_on_skipped_pipeline"]
    data, meta = run("repo-check", glconfig, audit_transport(project=project))
    assert checks(data)["merge_requires_pipeline"] == "warn"
    assert not data["complete"] and not data["passed"] and meta["partial"]


def test_explicit_public_exception_is_known_warning(glconfig):
    data, meta = run("repo-check", glconfig, audit_transport(project=project_reply(visibility="public")), "--allow-public")
    assert checks(data)["visibility_restricted"] == "warn"
    assert data["passed"] and data["complete"] and not meta["partial"]


def test_cli_masks_nested_case_variant_host_and_token(monkeypatch, capsys, glconfig):
    monkeypatch.setattr(Config, "load", lambda: glconfig)
    text = f'Юникод\\" {glconfig.host.upper()} {glconfig.token}\n' + "x" * 10000
    code = main("ci", ["--project", "group/project", "--action", "job-log", "7"],
                client_factory=lambda cfg: Client(cfg, transport=Transport(text.encode())))
    output = capsys.readouterr()
    assert code == 0 and json.loads(output.out)["ok"] and not output.err
    assert glconfig.token not in output.out and "git.example.invalid" not in output.out.lower()


def test_unexpected_read_failure_is_structured_and_not_an_uncertain_write(monkeypatch, capsys, glconfig):
    monkeypatch.setattr(Config, "load", lambda: glconfig)
    code = main("ci", ["--project", "group/project", "--action", "pipelines"],
                client_factory=lambda cfg: Client(cfg, transport=Transport(RuntimeError(glconfig.token))))
    output = capsys.readouterr()
    error = json.loads(output.out)["error"]
    assert code == 1 and error["code"] == "LOCAL_ERROR" and not error["outcome_unknown"]
    assert not output.err and glconfig.token not in output.out


def test_invalid_cli_argument_is_sanitized_json(capsys):
    assert main("ci", ["--not-an-option", "fixture-token"]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["error"]["code"] == "INVALID_INPUT"
    assert not output.err and "fixture-token" not in output.out
