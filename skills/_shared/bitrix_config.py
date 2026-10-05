"""Private configuration and safe errors. Runtime uses the standard library only."""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


class ToolError(Exception):
    def __init__(self, code, message, *, uncertain=False, retryable=False):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain
        self.retryable = retryable

    def as_dict(self):
        return {"code": self.code, "message": str(self), "outcome_unknown": self.uncertain,
                "retryable": self.retryable}


def state_home():
    return Path(os.environ.get("HARNESS_HOME", str(Path.home() / ".agent-harness"))).expanduser()


def positive_id(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ToolError("INVALID_INPUT", "Expected a positive integer ID.")
    return int(value)


def load_profile():
    path = Path(os.environ.get("BITRIX_PROFILE", str(state_home() / "profile.json"))).expanduser()
    if not path.exists():
        if os.environ.get("BITRIX_PROFILE"):
            raise ToolError("CONFIG_ERROR", "The explicitly configured profile does not exist.")
        return {}
    try:
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(profile, dict):
            raise ValueError()
        for key in ("user_id", "responsible_id"):
            if key in profile:
                positive_id(profile[key])
        if "portal_url" in profile:
            raise ToolError("CONFIG_ERROR", "Store the portal address in BITRIX_PORTAL_URL, not in the profile.")
        if not isinstance(profile.get("auditors", []), list):
            raise ValueError()
        for value in profile.get("auditors", []):
            positive_id(value)
        for key in ("users", "chats"):
            if not isinstance(profile.get(key, {}), dict):
                raise ValueError()
        for name, value in profile.get("users", {}).items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError()
            positive_id(value)
        for name, value in profile.get("chats", {}).items():
            if not isinstance(name, str) or not re.fullmatch(r"(?:chat|sg)?[1-9][0-9]*", str(value)):
                raise ValueError()
        return profile
    except (ValueError, OSError, ToolError):
        raise ToolError("CONFIG_ERROR", "Cannot read the private JSON profile.") from None


@dataclass(repr=False)
class Config:
    portal: str = field(repr=False)
    webhook_user_id: int
    token: str = field(repr=False)
    profile: dict = field(default_factory=dict, repr=False)
    timeout: float = 20.0
    read_retries: int = 2
    ca_bundle: str | None = None

    @classmethod
    def load(cls):
        profile = load_profile()
        portal = os.environ.get("BITRIX_PORTAL_URL", "")
        actor = os.environ.get("BITRIX_WEBHOOK_USER_ID", "")
        token = os.environ.get("BITRIX_WEBHOOK_TOKEN", "")
        legacy = os.environ.get("BITRIX_WEBHOOK", "")
        if legacy and not (actor and token):
            try:
                old = urlsplit(legacy)
                match = re.fullmatch(r"/rest/(\d+)/([A-Za-z0-9_-]+)/?", old.path)
                if not match or old.scheme != "https" or old.query or old.fragment or old.username:
                    raise ValueError()
                old_portal = f"https://{old.netloc}"
                if portal and portal.rstrip("/") != old_portal:
                    raise ValueError()
                portal, actor, token = portal or old_portal, actor or match[1], token or match[2]
            except ValueError:
                raise ToolError("CONFIG_ERROR", "Invalid or mismatched legacy webhook configuration.") from None
        if not all((portal, actor, token)):
            raise ToolError("CONFIG_MISSING", "Set BITRIX_PORTAL_URL, BITRIX_WEBHOOK_USER_ID and BITRIX_WEBHOOK_TOKEN.")
        try:
            parsed = urlsplit(portal)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                    or any(c.isspace() for c in portal)):
                raise ValueError()
            _ = parsed.port
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", token):
                raise ValueError()
            timeout = float(os.environ.get("BITRIX_TIMEOUT_SECONDS", "20"))
            retries = int(os.environ.get("BITRIX_READ_RETRIES", "2"))
            if not math.isfinite(timeout) or not 1 <= timeout <= 120 or not 0 <= retries <= 3:
                raise ValueError()
        except (TypeError, ValueError):
            raise ToolError("CONFIG_ERROR", "Invalid portal, credential format or request limits.") from None
        return cls(portal.rstrip("/"), positive_id(actor), token, profile, timeout, retries,
                   os.environ.get("BITRIX_CA_BUNDLE") or None)

    def user(self, value=None):
        if value is None:
            value = self.profile.get("user_id") or self.webhook_user_id
        return positive_id(self.profile.get("users", {}).get(str(value), value))

    def dialog(self, value):
        value = str(self.profile.get("chats", {}).get(value, value))
        if not re.fullmatch(r"(?:chat|sg)?[1-9][0-9]*", value):
            raise ToolError("UNKNOWN_CHAT", "Use a configured chat alias or an explicit dialog ID.")
        return value

    def redact(self, value):
        text = json.dumps(value, ensure_ascii=False)
        for secret in sorted({self.portal, urlsplit(self.portal).netloc, self.token}, key=len, reverse=True):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return json.loads(text)

    def task_path(self, task_id):
        return f"/company/personal/user/{self.user()}/tasks/task/view/{positive_id(task_id)}/"
