"""Decode Kimi's JSONL transcript without treating tool output as a final answer."""

import json


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Non-JSON numeric constant.")


def strict_json(text):
    try:
        return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError("Invalid or ambiguous JSON document.") from exc


def assistant_reply(stream, *, allowed_tools=()):
    """Require one final reply after complete, explicitly permitted tool cycles.

    Kimi 2.1 emits system.version/session.resume_hint metadata around chat messages.
    Unknown events, extra answers and missing tool results fail closed. This validates
    the recorded protocol, not the tools' filesystem permissions or their success.
    """
    if not isinstance(stream, str) or not stream.strip():
        raise ValueError("Kimi returned no JSONL messages.")
    final, version_seen, ended = None, False, False
    pending, used = set(), set()
    # JSONL frames use LF. Unicode separators remain valid inside JSON strings.
    for line in stream.split("\n"):
        if not line.strip():
            continue
        message = strict_json(line)
        if not isinstance(message, dict):
            raise ValueError("Kimi JSONL messages must be objects.")
        role = message.get("role")
        if role == "meta":
            kind = message.get("type")
            if kind == "system.version":
                if (version_seen or used or final is not None or ended
                        or set(message) != {"role", "type", "version"}
                        or not isinstance(message["version"], str) or not message["version"]):
                    raise ValueError("Invalid Kimi version metadata.")
                version_seen = True
            elif kind == "session.resume_hint":
                if (final is None or pending or ended
                        or set(message) != {"role", "type", "session_id", "command", "content"}
                        or any(not isinstance(message[key], str) or not message[key]
                               for key in ("session_id", "command", "content"))):
                    raise ValueError("Invalid Kimi completion metadata.")
                ended = True
            else:
                raise ValueError("Unsupported Kimi metadata; inspect the CLI protocol.")
            continue
        if ended or final is not None:
            raise ValueError("Kimi emitted messages after its final answer.")
        if role == "assistant":
            if pending or set(message) - {"role", "content", "tool_calls"}:
                raise ValueError("Incomplete or unsupported Kimi assistant message.")
            content, calls = message.get("content"), message.get("tool_calls", [])
            if (content is not None and not isinstance(content, str)) or not isinstance(calls, list):
                raise ValueError("Invalid Kimi assistant content or calls.")
            if not calls:
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Kimi final answer is empty.")
                final = content
                continue
            for call in calls:
                if not isinstance(call, dict) or set(call) != {"type", "id", "function"}:
                    raise ValueError("Invalid Kimi tool call.")
                function, call_id = call["function"], call["id"]
                if (call["type"] != "function" or not isinstance(call_id, str) or not call_id
                        or call_id in used or not isinstance(function, dict)
                        or set(function) != {"name", "arguments"}
                        or function["name"] not in allowed_tools
                        or not isinstance(function["arguments"], str)
                        or not isinstance(strict_json(function["arguments"]), dict)):
                    raise ValueError("Kimi used an invalid or disallowed tool call.")
                used.add(call_id)
                pending.add(call_id)
        elif role == "tool":
            if (set(message) != {"role", "tool_call_id", "content"}
                    or not isinstance(message["tool_call_id"], str)
                    or message["tool_call_id"] not in pending or not isinstance(message["content"], str)):
                raise ValueError("Kimi returned an unmatched or invalid tool result.")
            pending.remove(message["tool_call_id"])
        else:
            raise ValueError("Unsupported Kimi message role.")
    if final is None or pending:
        raise ValueError("Kimi transcript has no completed final answer.")
    return final
