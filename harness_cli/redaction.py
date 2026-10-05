"""Shared, stdlib-only masking for persisted receipts and hook diagnostics."""

import os
import re
from urllib.parse import urlsplit


def model_environment():
    """Omit service credentials from model helpers that do not use those services."""
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("BITRIX_", "GITLAB_", "GH_", "GITHUB_"))}


def redact_credentials(text):
    for name, value in sorted(os.environ.items(), key=lambda item: len(item[1]), reverse=True):
        if len(value) >= 4 and re.search(
            r"TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE_?KEY|WEBHOOK|PORTAL_URL|CREDENTIAL|DSN|DATABASE_URL",
            name, re.I,
        ):
            text = text.replace(value, "[REDACTED]")
    host = os.environ.get("GITLAB_HOST", "")
    if host:
        try:
            parsed = urlsplit(host)
            variants = {host, parsed.netloc, parsed.hostname} - {None, ""}
        except ValueError:
            variants = {host}
        for value in sorted(variants, key=len, reverse=True):
            if len(value) >= 4:
                text = re.sub(re.escape(value), "[REDACTED]", text, flags=re.I)
    text = re.sub(r"(?<![A-Za-z0-9+.-])([A-Za-z][A-Za-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@",
                  r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)(?<![A-Za-z0-9_])(?:sk-|gh[pousr]_|glpat-)[A-Za-z0-9_.-]{16,}",
                  "[REDACTED]", text)
    text = re.sub(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
