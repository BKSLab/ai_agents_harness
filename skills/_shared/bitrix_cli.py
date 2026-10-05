"""One JSON contract for the eight Bitrix skills."""

import argparse
import json
from pathlib import Path
import sys

from bitrix_config import Config, ToolError, positive_id
from bitrix_http import Client
from bitrix_state import Journal

WRITE_COMMANDS = {"create-task", "update-task", "close-task", "comment-task", "send-message"}
ROLE_FILTER = {"responsible": "RESPONSIBLE_ID", "creator": "CREATED_BY",
               "accomplice": "ACCOMPLICE", "auditor": "AUDITOR"}
TASK_FIELDS = {"TITLE", "DESCRIPTION", "RESPONSIBLE_ID", "PRIORITY", "DEADLINE", "PARENT_ID",
               "GROUP_ID", "ACCOMPLICES", "AUDITORS"}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError("INVALID_INPUT", "Invalid command arguments; use --help for supported options.")


def parser_for(command):
    p = Parser(description=f"Bitrix {command}. JSON output; configuration values are redacted.")
    if command in WRITE_COMMANDS:
        p.add_argument("--operation-id", required=True, help="Keep this ID unchanged when retrying the same action.")
    if command in ("get-task", "close-task", "comment-task", "update-task"):
        p.add_argument("task_id", type=positive_id)
    if command == "create-task":
        p.add_argument("title", nargs="?")
        p.add_argument("description", nargs="?")
        p.add_argument("--responsible")
        p.add_argument("--group-id", type=positive_id)
        p.add_argument("--auditor", action="append")
        p.add_argument("--accomplice", action="append")
        p.add_argument("--priority", choices=("0", "1", "2"))
        p.add_argument("--deadline")
    if command in ("get-messages", "send-message"):
        p.add_argument("dialog_id")
    if command in ("send-message", "comment-task"):
        p.add_argument("text", nargs="?")
    if command == "update-task":
        p.add_argument("fields_json", nargs="?")
    if command in ("create-task", "update-task", "send-message", "comment-task"):
        p.add_argument("--input", help="UTF-8 JSON file; - reads stdin. Do not interpolate text into shell commands.")
    if command == "get-task":
        p.add_argument("--without-comments", action="store_true")
    if command == "get-messages":
        p.add_argument("limit", type=int, nargs="?", default=20)
    if command == "list-tasks":
        p.add_argument("role", choices=tuple(ROLE_FILTER), nargs="?", default="responsible")
        p.add_argument("status", nargs="?", default=None)
        p.add_argument("--user")
        p.add_argument("--limit", type=int, default=200)
    return p


def input_object(args):
    source = getattr(args, "input", None)
    if not source:
        return {}
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8-sig")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (OSError, ValueError):
        raise ToolError("INVALID_INPUT", "Input must be a readable UTF-8 JSON object.") from None


def require_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ToolError("INVALID_INPUT", "A nonempty text value is required.")
    return value


def result_task(body, expected=None, *, v3=False, write=False):
    try:
        task = body["result"]["item" if v3 else "task"]
        task_id = positive_id(task["id"])
        if expected is not None and task_id != expected:
            raise ValueError()
        return task
    except (KeyError, TypeError, ValueError, ToolError):
        raise ToolError("INVALID_RESPONSE", "API did not confirm the expected task ID.", uncertain=write) from None


def result_id(body, *, write=False):
    try:
        return positive_id(body["result"])
    except (KeyError, ToolError):
        raise ToolError("INVALID_RESPONSE", "API did not confirm a positive object ID.", uncertain=write) from None


def normalize_fields(fields, cfg):
    if not isinstance(fields, dict) or not fields or set(fields) - TASK_FIELDS:
        raise ToolError("INVALID_INPUT", "Task fields must be a nonempty object of supported UPPERCASE fields.")
    fields = dict(fields)
    for key in ("TITLE", "DESCRIPTION"):
        if key in fields:
            if not isinstance(fields[key], str) or (key == "TITLE" and not fields[key].strip()):
                raise ToolError("INVALID_INPUT", "Task title and description must be strings; title cannot be empty.")
    for key in ("RESPONSIBLE_ID", "PARENT_ID", "GROUP_ID"):
        if key in fields:
            fields[key] = cfg.user(fields[key]) if key == "RESPONSIBLE_ID" else positive_id(fields[key])
    for key in ("AUDITORS", "ACCOMPLICES"):
        if key in fields:
            if not isinstance(fields[key], list):
                raise ToolError("INVALID_INPUT", "Participant fields must be arrays of IDs or configured aliases.")
            fields[key] = [cfg.user(value) for value in fields[key]]
    if "PRIORITY" in fields:
        fields["PRIORITY"] = str(fields["PRIORITY"])
        if fields["PRIORITY"] not in ("0", "1", "2"):
            raise ToolError("INVALID_INPUT", "Priority must be 0, 1 or 2.")
    if "DEADLINE" in fields and not isinstance(fields["DEADLINE"], str):
        raise ToolError("INVALID_INPUT", "Deadline must be an ISO date/time string.")
    return fields


def messages(client, dialog, limit):
    if not 1 <= limit <= 50:
        raise ToolError("INVALID_INPUT", "Message limit must be between 1 and 50.")
    result = client.call("im.dialog.messages.get", {"DIALOG_ID": dialog, "LIMIT": limit})["result"]
    if not isinstance(result, dict) or not isinstance(result.get("messages"), list):
        raise ToolError("INVALID_RESPONSE", "API did not return a message list.")
    if any(not isinstance(item, dict) or not isinstance(item.get("text", ""), str) for item in result["messages"]):
        raise ToolError("INVALID_RESPONSE", "API returned an invalid message entry.")
    return result


def execute(command, args, cfg, client, journal_factory=Journal):
    data = input_object(args)
    if command == "get-messages":
        return messages(client, cfg.dialog(args.dialog_id), args.limit), {}
    if command == "get-task":
        task = result_task(client.call("tasks.task.get", {"id": args.task_id, "select": ["*", "responsible.name", "creator.name"]}, v3=True),
                           args.task_id, v3=True)
        result = {"task": task, "comments": [], "comments_loaded": False, "path": cfg.task_path(args.task_id)}
        if task.get("chatId") and not args.without_comments:
            result["comments"] = [m for m in messages(client, cfg.dialog(f"chat{task['chatId']}"), 50)["messages"]
                                  if str(m.get("author_id", 0)) != "0" and m.get("text", "").strip()]
            result["comments_loaded"] = True
        return result, {}
    if command == "list-tasks":
        if not 1 <= args.limit <= 1000 or args.status not in (None, "active", "1", "2", "3", "4", "5", "6", "7"):
            raise ToolError("INVALID_INPUT", "Use a valid status and a limit between 1 and 1000.")
        filters = {ROLE_FILTER[args.role]: cfg.user(args.user)}
        if args.status:
            filters["!STATUS" if args.status == "active" else "STATUS"] = "5" if args.status == "active" else args.status
        tasks, cursor, more = [], 0, False
        for _ in range(100):
            body = client.call("tasks.task.list", {"filter": filters, "select": ["ID", "TITLE", "STATUS", "PRIORITY", "DEADLINE"],
                                                   "order": {"ID": "DESC"}, "start": cursor})
            result = body["result"]
            if not isinstance(result, dict) or not isinstance(result.get("tasks"), list):
                raise ToolError("INVALID_RESPONSE", "API did not return a task list.")
            batch = result["tasks"]
            if any(not isinstance(t, dict) or not (t.get("id") or t.get("ID")) for t in batch):
                raise ToolError("INVALID_RESPONSE", "Task list contains an invalid entry.")
            tasks.extend(batch)
            nxt = body.get("next")
            if len(tasks) >= args.limit or nxt is None:
                more = nxt is not None or len(tasks) > args.limit
                break
            if not batch or isinstance(nxt, bool) or not isinstance(nxt, int) or nxt <= cursor:
                raise ToolError("INVALID_RESPONSE", "Pagination did not advance.")
            cursor = nxt
        else:
            raise ToolError("PAGE_LIMIT", "Pagination exceeded the request budget.")
        return {"tasks": tasks[:args.limit], "count": min(len(tasks), args.limit), "truncated": more}, {}

    v3 = False
    if command == "create-task":
        if data and (args.title is not None or args.description is not None):
            raise ToolError("INVALID_INPUT", "Use either JSON input or positional task text.")
        fields = dict(data) if data else {"TITLE": args.title, "DESCRIPTION": args.description or ""}
        fields.setdefault("RESPONSIBLE_ID", cfg.profile.get("responsible_id") or cfg.user())
        fields.setdefault("AUDITORS", cfg.profile.get("auditors", []))
        options = {"RESPONSIBLE_ID": args.responsible, "GROUP_ID": args.group_id, "AUDITORS": args.auditor,
                   "ACCOMPLICES": args.accomplice, "PRIORITY": args.priority, "DEADLINE": args.deadline}
        fields.update({k: v for k, v in options.items() if v is not None})
        fields = normalize_fields(fields, cfg)
        require_text(fields.get("TITLE"))
        method, payload = "tasks.task.add", {"fields": fields}
    elif command == "update-task":
        if args.fields_json and data:
            raise ToolError("INVALID_INPUT", "Use either JSON input or the fields argument.")
        try:
            fields = normalize_fields(data or json.loads(args.fields_json or "{}"), cfg)
        except ValueError:
            raise ToolError("INVALID_INPUT", "Task fields must be valid JSON.") from None
        method, payload = "tasks.task.update", {"taskId": args.task_id, "fields": fields}
    elif command == "close-task":
        method, payload = "tasks.task.complete", {"taskId": args.task_id}
    elif command in ("send-message", "comment-task"):
        if args.text is not None and data:
            raise ToolError("INVALID_INPUT", "Use either JSON input or positional message text.")
        text = require_text(data.get("text", args.text))
        if command == "send-message":
            method, payload = "im.message.add", {"DIALOG_ID": cfg.dialog(args.dialog_id), "MESSAGE": text, "SYSTEM": "N", "URL_PREVIEW": "N"}
        else:
            method, payload, v3 = "tasks.task.chat.message.send", {"fields": {"taskId": args.task_id, "text": text}}, True
    else:
        raise ToolError("INVALID_INPUT", "Unknown tool command.")

    def mutate():
        body = client.call(method, payload, write=True, v3=v3)
        if command == "send-message":
            return {"message_id": result_id(body, write=True)}
        if command == "comment-task":
            if not isinstance(body["result"], dict) or body["result"].get("result") is not True:
                raise ToolError("INVALID_RESPONSE", "API did not confirm the task comment.", uncertain=True)
            return {"task_id": args.task_id, "comment_confirmed": True, "path": cfg.task_path(args.task_id)}
        task = result_task(body, None if command == "create-task" else args.task_id, write=True)
        task_id = positive_id(task["id"])
        if command == "create-task" and fields.get("GROUP_ID") is not None and str(task.get("groupId")) != str(fields["GROUP_ID"]):
            raise ToolError("POSTCONDITION_FAILED", f"Task {task_id} exists, but the requested group was not confirmed. Do not create it again.", uncertain=True)
        receipt = {"task_id": task_id, "path": cfg.task_path(task_id)}
        if command == "close-task":
            status = str(task.get("status"))
            if status not in ("4", "5"):
                raise ToolError("POSTCONDITION_FAILED", "API did not confirm a completed or awaiting-control state.", uncertain=True)
            receipt.update(status=status, completed=status == "5")
        return receipt

    receipt, replayed = journal_factory(cfg).run(args.operation_id, method, payload, mutate)
    return receipt, {"operation_id": args.operation_id, "replayed": replayed}


def main(command, argv=None, *, client_factory=Client, journal_factory=Journal):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cfg = None
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
                                         "outcome_unknown": command in WRITE_COMMANDS, "retryable": False}}
        code = 1
    print(json.dumps(cfg.redact(output) if cfg else output, ensure_ascii=False))
    return code
