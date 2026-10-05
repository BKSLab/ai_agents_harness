"""Small stdlib-only runtime shared by the Kimi hooks; never echo input payloads."""

import json
from pathlib import Path
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness_cli.redaction import redact_credentials as redact


MAX_INPUT = 256 * 1024
MAX_OUTPUT = 8 * 1024


class InvalidPayload(ValueError):
    pass


def read_payload(stream=None):
    stream = stream or sys.stdin.buffer
    raw = stream.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise InvalidPayload("payload_too_large")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise InvalidPayload("invalid_json") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        raise InvalidPayload("invalid_tool_input")
    return payload


def emit(hook, status, reason, **details):
    hook, status, reason = str(hook)[:64], str(status)[:32], str(reason)[:160]
    report = {"schema_version": 1, "hook": hook, "status": status, "reason": reason, **details}
    def safe(value):
        if isinstance(value, str):
            return redact(value)
        if isinstance(value, list):
            return [safe(item) for item in value]
        if isinstance(value, dict):
            return {key: safe(item) for key, item in value.items()}
        return value

    encoded = json.dumps(safe(report), ensure_ascii=True)
    if len(encoded) > MAX_OUTPUT:
        report = {"schema_version": 1, "hook": hook, "status": status,
                  "reason": reason, "diagnostics_truncated": True}
        encoded = json.dumps(report, ensure_ascii=True)
    print(encoded)


def run_bounded(command, cwd, timeout=20, max_stream=32 * 1024):
    """Drain both pipes without unbounded capture; kill only the child we started."""
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]

    def drain(pipe, index):
        try:
            while chunk := pipe.read(4096):
                available = max_stream - len(buffers[index])
                buffers[index].extend(chunk[:available])
                if len(chunk) > available:
                    truncated[index] = True
        finally:
            pipe.close()

    threads = [threading.Thread(target=drain, args=(pipe, index), daemon=True)
               for index, pipe in enumerate((process.stdout, process.stderr))]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=2)
    finally:
        for thread in threads:
            thread.join(timeout=2)
    return {
        "returncode": process.returncode,
        "stdout": buffers[0].decode("utf-8", errors="replace"),
        "stderr": buffers[1].decode("utf-8", errors="replace"),
        "truncated": any(truncated),
        "timed_out": timed_out,
    }
