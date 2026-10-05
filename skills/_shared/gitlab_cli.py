"""One JSON contract for the GitLab skills."""

import argparse
import json
from pathlib import Path
import re
import sys

from gitlab_config import Config, ToolError, positive_id
from gitlab_http import Client
from gitlab_state import Journal

LIST_LIMIT = 500
CI_READ = ("pipelines", "pipeline", "job-log")
CI_WRITE = ("retry", "trigger", "cancel")
MR_READ = ("list", "show")
MR_WRITE = ("create", "merge", "approve")

PROJECT_FIELDS = ("id", "path_with_namespace", "name", "description", "visibility", "default_branch",
                  "merge_requests_enabled", "merge_method", "approvals_before_merge",
                  "only_allow_merge_if_pipeline_succeeds", "allow_merge_on_skipped_pipeline",
                  "only_allow_merge_if_all_discussions_are_resolved", "squash_option",
                  "remove_source_branch_after_merge", "created_at", "last_activity_at", "web_url")
PUSH_RULE_FIELDS = ("id", "deny_delete_tag", "member_check", "prevent_secrets", "commit_message_regex",
                    "commit_message_negative_regex", "branch_name_regex", "author_email_regex",
                    "file_name_regex", "max_file_size", "commit_committer_check",
                    "commit_committer_name_check", "reject_unsigned_commits", "reject_non_dco_commits")
PROTECTED_BRANCH_FIELDS = ("id", "name", "allow_force_push", "code_owner_approval_required", "inherited",
                           "push_access_levels", "merge_access_levels", "unprotect_access_levels")
APPROVAL_RULE_FIELDS = ("id", "name", "rule_type", "approvals_required", "protected_branches",
                        "applies_to_all_protected_branches")
APPROVAL_SETTINGS_FIELDS = ("disable_overriding_approvers_per_merge_request",)
PIPELINE_FIELDS = ("id", "iid", "project_id", "status", "ref", "sha", "source",
                   "created_at", "updated_at", "web_url")
JOB_FIELDS = ("id", "name", "stage", "status", "ref", "allow_failure",
              "created_at", "started_at", "finished_at", "duration")
MR_FIELDS = ("id", "iid", "title", "state", "draft", "source_branch", "target_branch", "sha",
             "merge_status", "detailed_merge_status", "has_conflicts", "blocking_discussions_resolved",
             "created_at", "updated_at", "merged_at", "web_url")
MR_CREATE_FIELDS = ("source_branch", "target_branch", "title", "description",
                    "remove_source_branch", "squash")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError("INVALID_INPUT", "Invalid command arguments; use --help for supported options.")


def parser_for(command):
    p = Parser(description=f"GitLab {command}. JSON output; configuration values are redacted.")
    p.add_argument("--project", required=True, help="Project path (group/project), numeric ID or configured alias.")
    if command == "ci":
        p.add_argument("--action", required=True, choices=CI_READ + CI_WRITE)
        p.add_argument("value", nargs="?", help="Pipeline ID, job ID or ref name, depending on the action.")
        p.add_argument("--limit", type=int, default=100, help=f"List size limit, 1-{LIST_LIMIT}.")
        p.add_argument("--operation-id", help="Required for retry, trigger and cancel; keep it unchanged when retrying.")
    if command == "mr":
        p.add_argument("--action", required=True, choices=MR_READ + MR_WRITE)
        p.add_argument("value", nargs="?", help="Merge request IID for show, merge and approve.")
        p.add_argument("--state", default="opened", choices=("opened", "closed", "merged", "locked", "all"))
        p.add_argument("--limit", type=int, default=100, help=f"List size limit, 1-{LIST_LIMIT}.")
        p.add_argument("--input", help="UTF-8 JSON file; - reads stdin. Required for create.")
        p.add_argument("--sha", help="Reviewed HEAD commit SHA; required for merge and approve.")
        p.add_argument("--operation-id", help="Required for create, merge and approve; keep it unchanged when retrying.")
    if command == "repo-check":
        p.add_argument("--allow-public", action="store_true", help="Downgrade public visibility from fail to warn.")
    return p


def input_object(args):
    source = getattr(args, "input", None)
    if not source:
        return {}

    def unique_keys(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError()
            data[key] = value
        return data

    def reject_constant(value):
        raise ValueError()

    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8-sig")
        data = json.loads(text, object_pairs_hook=unique_keys, parse_constant=reject_constant)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (OSError, ValueError):
        raise ToolError("INVALID_INPUT", "Input must be a readable UTF-8 JSON object without duplicate keys or non-finite numbers.") from None


def require_text(value, label="text"):
    if not isinstance(value, str) or not value.strip():
        raise ToolError("INVALID_INPUT", f"A nonempty {label} value is required.")
    return value


def pick(source, fields):
    return {key: source.get(key) for key in fields if key in source}


def expect_iid(body, key, expected=None, *, write=False):
    try:
        value = positive_id(body[key])
    except (KeyError, TypeError, ToolError):
        raise ToolError("INVALID_RESPONSE", "API did not confirm the expected object ID.", uncertain=write) from None
    if expected is not None and value != expected:
        raise ToolError("INVALID_RESPONSE", "API returned an unexpected object ID.", uncertain=write)
    return value


def collect(client, path, params, limit):
    if not 1 <= limit <= LIST_LIMIT:
        raise ToolError("INVALID_INPUT", f"List limit must be between 1 and {LIST_LIMIT}.")
    items, page = [], 1
    # One bounded lookahead distinguishes an exact limit from an actually truncated list.
    while len(items) <= limit:
        batch = client.request("GET", path, params={**params, "per_page": 100, "page": page})
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            raise ToolError("INVALID_RESPONSE", "API did not return a list of objects.")
        items.extend(batch)
        if len(batch) < 100:
            return items[:limit], len(items) > limit
        if len(items) > limit:
            break
        page += 1
    return items[:limit], True


def _is_write(command, action):
    return (command == "ci" and action in CI_WRITE) or (command == "mr" and action in MR_WRITE)


def validate_args(command, args, cfg):
    """Validate all local input before the first API request or journal reservation."""
    action = getattr(args, "action", None)
    value = getattr(args, "value", None)
    if command not in ("project-info", "repo-check", "ci", "mr"):
        raise ToolError("INVALID_INPUT", "Unknown tool command.")
    if command == "ci" and action not in CI_READ + CI_WRITE:
        raise ToolError("INVALID_INPUT", "Unknown CI action.")
    if command == "mr" and action not in MR_READ + MR_WRITE:
        raise ToolError("INVALID_INPUT", "Unknown merge request action.")
    if hasattr(args, "limit") and (isinstance(args.limit, bool) or not isinstance(args.limit, int)
                                  or not 1 <= args.limit <= LIST_LIMIT):
        raise ToolError("INVALID_INPUT", f"List limit must be between 1 and {LIST_LIMIT}.")
    if _is_write(command, action):
        if not args.operation_id or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", args.operation_id):
            raise ToolError("OPERATION_ID_REQUIRED", "Writes require a stable --operation-id (8-100 letters, digits, - or _).")
    elif getattr(args, "operation_id", None):
        raise ToolError("INVALID_INPUT", "--operation-id is only supported for writes.")
    if command == "ci":
        if action == "pipelines":
            if value is not None:
                raise ToolError("INVALID_INPUT", "The pipelines action does not accept a positional value.")
        elif action == "trigger":
            cfg.ref(value)
        else:
            positive_id(value)
    if command == "mr":
        if action in ("list", "create"):
            if value is not None:
                raise ToolError("INVALID_INPUT", "This merge request action does not accept a positional value.")
        else:
            positive_id(value)
        if action in ("merge", "approve"):
            if not args.sha or not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", args.sha):
                raise ToolError("INVALID_INPUT", "Merge and approve require --sha with the reviewed HEAD commit SHA.")
            args.sha = args.sha.lower()
        elif args.sha:
            raise ToolError("INVALID_INPUT", "--sha is only supported for merge and approve.")
        if action != "create" and args.input:
            raise ToolError("INVALID_INPUT", "--input is only supported for create.")


def optional_resource(client, path, *, collection=False, nullable=False):
    try:
        if collection:
            data, truncated = collect(client, path, {}, LIST_LIMIT)
        else:
            data, truncated = client.request("GET", path, allow_null=nullable), False
            if data is not None and not isinstance(data, dict):
                raise ToolError("INVALID_RESPONSE", "API did not return a settings object.")
        return data, truncated, True
    except ToolError as exc:
        if exc.code == "NOT_FOUND" or (exc.code == "ACCESS_DENIED" and getattr(exc, "status", None) == 403):
            return None, False, False
        raise


def project_settings(client, base):
    project = client.request("GET", base)
    expect_iid(project, "id")
    resources, meta = {}, {"truncated": False, "unavailable": []}
    for name, path, collection, nullable in (
        ("push_rules", "push_rule", False, True),
        ("protected_branches", "protected_branches", True, False),
        ("approval_rules", "approval_rules", True, False),
        ("approval_settings", "approvals", False, False),
    ):
        data, truncated, available = optional_resource(client, f"{base}/{path}",
                                                       collection=collection, nullable=nullable)
        resources[name] = {"data": data, "truncated": truncated, "available": available}
        meta["truncated"] |= truncated
        if not available:
            meta["unavailable"].append(name)
    meta["partial"] = bool(meta["unavailable"] or meta["truncated"])
    return project, resources, meta


def matches_branch(branch, pattern):
    # GitLab documents '*' wildcards, not shell character classes or '?' patterns.
    return bool(re.fullmatch(re.escape(pattern).replace(r"\*", ".*"), branch))


def audit_project(project, resources, allow_public):
    checks, complete = [], True

    def add(check_id, result, detail, *, unknown=False):
        nonlocal complete
        complete &= not unknown
        checks.append({"id": check_id, "result": result, "detail": detail})

    branches = resources["protected_branches"]
    default = project.get("default_branch")
    rules = branches["data"] or []
    branch_known = (branches["available"] and not branches["truncated"]
                    and all(isinstance(b.get("name"), str) for b in rules))
    matched = [b for b in rules if isinstance(default, str) and isinstance(b.get("name"), str)
               and matches_branch(default, b["name"])]
    if matched:
        add("default_branch_protected", "ok", "The default branch matches protected branch rules.")
    elif not branch_known or "default_branch" not in project:
        add("default_branch_protected", "warn", "Default branch protection is unknown or incomplete.", unknown=True)
    else:
        add("default_branch_protected", "fail", "The project has no protected default branch.")
    if any(b.get("allow_force_push") is True for b in matched):
        add("force_push_blocked", "fail", "At least one matching rule allows force push.")
    elif not branch_known or "default_branch" not in project or any(
            not isinstance(b.get("allow_force_push"), bool) for b in matched):
        add("force_push_blocked", "warn", "Force-push permissions are unknown or incomplete.", unknown=True)
    elif not matched:
        add("force_push_blocked", "fail", "The default branch is not protected against force push.")
    else:
        add("force_push_blocked", "ok", "All matching rules block force push.")

    pipeline = project.get("only_allow_merge_if_pipeline_succeeds")
    skipped = project.get("allow_merge_on_skipped_pipeline")
    if pipeline is False or skipped is True:
        add("merge_requires_pipeline", "fail", "Merge can proceed without a successful pipeline.")
    elif pipeline is True and skipped is False:
        add("merge_requires_pipeline", "ok", "Merge requires a successful pipeline; skipped pipelines are not accepted.")
    else:
        add("merge_requires_pipeline", "warn", "Pipeline requirements are not fully reported.", unknown=True)

    approvals = resources["approval_rules"]
    approval_settings = resources["approval_settings"]
    overrides_disabled = (approval_settings["data"] or {}).get("disable_overriding_approvers_per_merge_request")
    overrides_known = approval_settings["available"] and isinstance(overrides_disabled, bool)
    complete &= overrides_known
    approval_unknown = not approvals["available"] or approvals["truncated"] or not isinstance(default, str)
    required = []
    for rule in approvals["data"] or []:
        count = rule.get("approvals_required")
        protected = rule.get("protected_branches")
        all_protected = rule.get("applies_to_all_protected_branches")
        if (isinstance(count, bool) or not isinstance(count, int) or count < 0
                or not isinstance(protected, list) or not isinstance(all_protected, bool)
                or any(not isinstance(b, dict) or not isinstance(b.get("name"), str) for b in protected)):
            approval_unknown = True
            continue
        if all_protected:
            applies = bool(matched)
            approval_unknown |= not branch_known
        elif protected:
            applies = isinstance(default, str) and any(matches_branch(default, b["name"]) for b in protected)
        else:
            applies = True
        if applies and count > 0:
            if rule.get("rule_type") not in ("regular", "any_approver"):
                approval_unknown = True
            else:
                required.append(count)
    if approval_unknown:
        add("approvals_required", "warn", "Applicable approval requirements are unavailable or incomplete.", unknown=True)
    elif required:
        if not overrides_known:
            add("approvals_required", "warn", "The API did not confirm whether approval rule overrides are disabled.", unknown=True)
        elif not overrides_disabled:
            add("approvals_required", "fail", "Merge request authors can override the default approval rules.")
        else:
            add("approvals_required", "ok", f"An applicable rule requires {max(required)} approval(s) for the default branch; rule overrides are disabled.")
    else:
        add("approvals_required", "fail", "No applicable rule requires approvals for the default branch.")

    visibility = project.get("visibility")
    if visibility == "public":
        add("visibility_restricted", "warn" if allow_public else "fail", "Project visibility is public.")
    elif visibility in ("private", "internal"):
        add("visibility_restricted", "ok", f"Project visibility is {visibility}.")
    else:
        add("visibility_restricted", "warn", "Project visibility is not reported.", unknown=True)

    push = resources["push_rules"]
    push_data = push["data"]
    if not push["available"]:
        add("push_rules_enabled", "warn", "Push rules are unavailable with the current permissions or GitLab tier.", unknown=True)
    elif push_data is None:
        add("push_rules_enabled", "fail", "No push rules are configured.")
    else:
        fields = set(PUSH_RULE_FIELDS) - {"id"}
        enabled = any(push_data.get(key) is True for key in fields if not key.endswith("_regex") and key != "max_file_size")
        enabled |= any(isinstance(push_data.get(key), str) and bool(push_data[key])
                       for key in fields if key.endswith("_regex"))
        size = push_data.get("max_file_size")
        enabled |= isinstance(size, int) and not isinstance(size, bool) and size > 0
        if enabled:
            add("push_rules_enabled", "ok", "At least one push rule restriction is enabled.")
        elif not fields <= push_data.keys():
            add("push_rules_enabled", "warn", "The API did not report all push rule settings.", unknown=True)
        else:
            add("push_rules_enabled", "fail", "All configured push rule restrictions are disabled.")
    complete &= all(r["available"] and not r["truncated"] for r in resources.values())
    summary = {state: sum(c["result"] == state for c in checks) for state in ("ok", "warn", "fail")}
    return {"project": pick(project, PROJECT_FIELDS), "checks": checks, "summary": summary,
            "complete": complete, "passed": complete and summary["fail"] == 0}


def execute(command, args, cfg, client, journal_factory=Journal):
    action = getattr(args, "action", None)
    validate_args(command, args, cfg)
    base = f"/projects/{cfg.project(args.project)}"

    if command == "project-info":
        project, resources, meta = project_settings(client, base)
        push_rule = resources["push_rules"]["data"]
        approval_settings = resources["approval_settings"]["data"]
        return {"project": pick(project, PROJECT_FIELDS),
                "push_rules": pick(push_rule, PUSH_RULE_FIELDS) if isinstance(push_rule, dict) else None,
                "protected_branches": [pick(b, PROTECTED_BRANCH_FIELDS) for b in resources["protected_branches"]["data"] or []],
                "approval_rules": [pick(r, APPROVAL_RULE_FIELDS) for r in resources["approval_rules"]["data"] or []],
                "approval_settings": pick(approval_settings, APPROVAL_SETTINGS_FIELDS)
                if isinstance(approval_settings, dict) else None}, meta

    if command == "ci":
        if action == "pipelines":
            items, truncated = collect(client, f"{base}/pipelines", {"order_by": "id", "sort": "desc"}, args.limit)
            return {"pipelines": [pick(p, PIPELINE_FIELDS) for p in items], "count": len(items)}, {"truncated": truncated}
        if action == "pipeline":
            pid = positive_id(args.value)
            pipeline = client.request("GET", f"{base}/pipelines/{pid}")
            expect_iid(pipeline, "id", pid)
            jobs, truncated = collect(client, f"{base}/pipelines/{pid}/jobs", {}, LIST_LIMIT)
            return {"pipeline": pick(pipeline, PIPELINE_FIELDS),
                    "jobs": [pick(j, JOB_FIELDS) for j in jobs]}, {"truncated": truncated}
        if action == "job-log":
            jid = positive_id(args.value)
            log = client.request("GET", f"{base}/jobs/{jid}/trace", raw=True)
            return {"job_id": jid, "log": log["text"]}, {"truncated": log["truncated"], "log_segment": log["segment"]}
        if action in ("retry", "cancel"):
            pid = positive_id(args.value)
            path, payload = f"{base}/pipelines/{pid}/{action}", None
        else:  # trigger
            ref = cfg.ref(args.value)
            path, payload = f"{base}/pipeline", {"ref": ref}

        def mutate():
            body = client.request("POST", path, payload=payload, write=True)
            expected = pid if action in ("retry", "cancel") else None
            receipt = {"action": action, "pipeline_id": expect_iid(body, "id", expected, write=True)}
            if action == "trigger" and body.get("ref") != ref:
                raise ToolError("POSTCONDITION_FAILED", "API did not confirm the requested pipeline ref.", uncertain=True)
            if isinstance(body.get("status"), str):
                receipt["status"] = body["status"]
            if isinstance(body.get("ref"), str):
                receipt["ref"] = body["ref"]
            return receipt

        receipt, replayed = journal_factory(cfg).run(args.operation_id, f"gitlab.ci.{action}",
                                                     {"project": base, "arg": args.value, "payload": payload}, mutate)
        return receipt, {"operation_id": args.operation_id, "replayed": replayed}

    if command == "mr":
        if action == "list":
            items, truncated = collect(client, f"{base}/merge_requests",
                                       {"state": args.state, "order_by": "updated_at", "sort": "desc"}, args.limit)
            return {"merge_requests": [pick(m, MR_FIELDS) for m in items], "count": len(items)}, {"truncated": truncated}
        if action == "show":
            iid = positive_id(args.value)
            mr = client.request("GET", f"{base}/merge_requests/{iid}")
            expect_iid(mr, "iid", iid)
            return {"merge_request": pick(mr, MR_FIELDS)}, {}
        if action == "create":
            data = input_object(args)
            if not data or set(data) - set(MR_CREATE_FIELDS):
                raise ToolError("INVALID_INPUT", "Create input must be a JSON object with fields: " + ", ".join(MR_CREATE_FIELDS) + ".")
            payload = {key: cfg.ref(data.get(key)) for key in ("source_branch", "target_branch")}
            payload["title"] = require_text(data.get("title"), "title")
            if "description" in data:
                if not isinstance(data["description"], str):
                    raise ToolError("INVALID_INPUT", "Merge request description must be a string.")
                payload["description"] = data["description"]
            for key in ("remove_source_branch", "squash"):
                if key in data:
                    if not isinstance(data[key], bool):
                        raise ToolError("INVALID_INPUT", f"Merge request field {key} must be a boolean.")
                    payload[key] = data[key]
        else:  # merge, approve
            iid = positive_id(args.value)
            payload = {"sha": args.sha}
        # Approval belongs to an authenticated user. Token rotation for that same user must preserve replay.
        actor_id = None
        if action == "approve":
            actor_id = expect_iid(client.request("GET", "/user"), "id")

        def mutate():
            if action == "create":
                body = client.request("POST", f"{base}/merge_requests", payload=payload, write=True)
                iid_out = expect_iid(body, "iid", write=True)
                if (body.get("state") != "opened" or body.get("source_branch") != payload["source_branch"]
                        or body.get("target_branch") != payload["target_branch"]):
                    raise ToolError("POSTCONDITION_FAILED", "API did not confirm the requested merge request branches and state.", uncertain=True)
                return {"iid": iid_out, "state": body.get("state"),
                        "source_branch": body.get("source_branch"), "target_branch": body.get("target_branch")}
            if action == "merge":
                body = client.request("PUT", f"{base}/merge_requests/{iid}/merge", payload=payload, write=True)
                expect_iid(body, "iid", iid, write=True)
                if body.get("state") != "merged":
                    raise ToolError("POSTCONDITION_FAILED", "API did not confirm the merged state.", uncertain=True)
                receipt = {"iid": iid, "state": "merged", "sha": args.sha}
                if isinstance(body.get("merge_commit_sha"), str):
                    receipt["merge_commit_sha"] = body["merge_commit_sha"]
                return receipt
            body = client.request("POST", f"{base}/merge_requests/{iid}/approve", payload=payload, write=True)
            expect_iid(body, "iid", iid, write=True)
            approved_by = body.get("approved_by")
            if not isinstance(approved_by, list) or not any(
                    isinstance(item, dict) and isinstance(item.get("user"), dict)
                    and type(item["user"].get("id")) is int
                    and item["user"]["id"] == actor_id for item in approved_by):
                raise ToolError("POSTCONDITION_FAILED", "API did not confirm the current user's approval.", uncertain=True)
            return {"iid": iid, "approved": True, "sha": args.sha, "actor_id": actor_id}

        identity = {"actor_id": actor_id} if actor_id is not None else {}
        receipt, replayed = journal_factory(cfg).run(args.operation_id, f"gitlab.mr.{action}",
                                                     {"project": base, "arg": args.value, "payload": payload, **identity}, mutate)
        return receipt, {"operation_id": args.operation_id, "replayed": replayed}

    if command == "repo-check":
        project, resources, meta = project_settings(client, base)
        result = audit_project(project, resources, args.allow_public)
        meta["partial"] |= not result["complete"]
        return result, meta

    raise ToolError("INVALID_INPUT", "Unknown tool command.")


def main(command, argv=None, *, client_factory=Client, journal_factory=Journal):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cfg, args = None, None
    try:
        args = parser_for(command).parse_args(argv)
        cfg = Config.load()
        data, meta = execute(command, args, cfg, client_factory(cfg), journal_factory)
        output = {"ok": True, "data": data, "meta": meta}
        code = 0
    except ToolError as exc:
        output = {"ok": False, "error": exc.as_dict()}
        code = 2 if exc.code in ("INVALID_INPUT", "CONFIG_MISSING", "CONFIG_ERROR", "OPERATION_ID_REQUIRED", "TLS_CONFIG") else 1
    except Exception:
        # This is the CLI boundary: never leak request URLs through an unexpected traceback.
        output = {"ok": False, "error": {"code": "LOCAL_ERROR", "message": "Tool failed locally; inspect configuration and the operation journal.",
                                         "outcome_unknown": _is_write(command, getattr(args, "action", None)), "retryable": False}}
        code = 1
    print(json.dumps(cfg.redact(output) if cfg else output, ensure_ascii=False))
    return code
