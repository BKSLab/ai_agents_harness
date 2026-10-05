"""GitLab configuration, project aliases and safe errors. Runtime uses the standard library only."""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

from bitrix_config import ToolError, positive_id as positive_id, state_home

_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.\-/]{0,198}[A-Za-z0-9_.\-])?")
_NUMERIC_ID = re.compile(r"[1-9][0-9]*")


def load_profile():
    path = Path(os.environ.get("GITLAB_PROFILE", str(state_home() / "profile.json"))).expanduser()
    if not path.exists():
        if os.environ.get("GITLAB_PROFILE"):
            raise ToolError("CONFIG_ERROR", "The explicitly configured profile does not exist.")
        return {}
    try:
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(profile, dict):
            raise ValueError()
        for key in ("host", "token", "gitlab_host", "gitlab_token"):
            if key in profile:
                raise ToolError("CONFIG_ERROR", "Store the GitLab host and token in environment variables, not in the profile.")
        projects = profile.get("gitlab_projects", {})
        if not isinstance(projects, dict):
            raise ValueError()
        for name, value in projects.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError()
            if isinstance(value, bool):
                raise ValueError()
            if isinstance(value, int):
                if value <= 0:
                    raise ValueError()
                continue
            if not isinstance(value, str) or not _NAME.fullmatch(value) or ".." in value or "//" in value:
                raise ValueError()
        return profile
    except (ValueError, OSError):
        raise ToolError("CONFIG_ERROR", "Cannot read the private JSON profile.") from None


@dataclass(repr=False)
class Config:
    host: str = field(repr=False)
    token: str = field(repr=False)
    profile: dict = field(default_factory=dict, repr=False)
    timeout: float = 20.0
    read_retries: int = 2
    ca_bundle: str | None = None

    @classmethod
    def load(cls):
        profile = load_profile()
        host = os.environ.get("GITLAB_HOST", "")
        token = os.environ.get("GITLAB_TOKEN", "")
        missing = [name for name, value in (("GITLAB_HOST", host), ("GITLAB_TOKEN", token)) if not value]
        if missing:
            raise ToolError("CONFIG_MISSING", "Missing configuration: " + ", ".join(missing) + ".")
        insecure_ok = os.environ.get("GITLAB_ALLOW_INSECURE_HTTP", "") == "1"
        scheme = None
        try:
            parsed = urlsplit(host)
            scheme = parsed.scheme
            if ((scheme != "https" and not (insecure_ok and scheme == "http"))
                    or not parsed.hostname or parsed.username is not None or parsed.password is not None
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                    or any(c.isspace() for c in host)):
                raise ValueError()
            _ = parsed.port
            if not re.fullmatch(r"[A-Za-z0-9_\-.]{8,256}", token):
                raise ValueError()
            timeout = float(os.environ.get("GITLAB_TIMEOUT_SECONDS", "20"))
            retries = int(os.environ.get("GITLAB_READ_RETRIES", "2"))
            if not math.isfinite(timeout) or not 1 <= timeout <= 120 or not 0 <= retries <= 3:
                raise ValueError()
        except (TypeError, ValueError):
            hint = " Plain HTTP requires explicit opt-in: set GITLAB_ALLOW_INSECURE_HTTP=1." if scheme == "http" and not insecure_ok else ""
            raise ToolError("CONFIG_ERROR", "Invalid host, credential format or request limits." + hint) from None
        return cls(host.rstrip("/"), token, profile, timeout, retries,
                   os.environ.get("GITLAB_CA_BUNDLE") or None)

    def project(self, value):
        if isinstance(value, str):
            resolved = self.profile.get("gitlab_projects", {}).get(value, value)
        else:
            resolved = value
        if isinstance(resolved, bool):
            raise ToolError("INVALID_INPUT", "Project must be a path, numeric ID or configured alias.")
        if isinstance(resolved, int):
            if resolved <= 0:
                raise ToolError("INVALID_INPUT", "Project ID must be a positive integer.")
            return str(resolved)
        resolved = str(resolved) if resolved is not None else ""
        if _NUMERIC_ID.fullmatch(resolved):
            return resolved
        if not _NAME.fullmatch(resolved) or ".." in resolved or "//" in resolved:
            raise ToolError("INVALID_INPUT", "Project must be a valid group/project path, numeric ID or configured alias.")
        return quote(resolved, safe="")

    def ref(self, value):
        if (not isinstance(value, str) or not _NAME.fullmatch(value) or ".." in value
                or "//" in value or value.startswith("/")):
            raise ToolError("INVALID_INPUT", "Ref must be a branch or tag name.")
        return value

    def redact(self, value):
        parsed = urlsplit(self.host)
        hosts = sorted({self.host, parsed.netloc, parsed.hostname} - {None, ""}, key=len, reverse=True)
        host_pattern = re.compile("|".join(re.escape(host) for host in hosts), re.IGNORECASE)

        def clean(item):
            if isinstance(item, str):
                return host_pattern.sub("[REDACTED]", item).replace(self.token, "[REDACTED]")
            if isinstance(item, dict):
                return {clean(key): clean(child) for key, child in item.items()}
            if isinstance(item, list):
                return [clean(child) for child in item]
            return item

        return clean(value)
