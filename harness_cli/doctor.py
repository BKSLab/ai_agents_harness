"""Read-only diagnosis without configuration values or live API requests."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

from . import __version__
from .capabilities import capabilities
from .install import ROOT, agent_targets


def binary_version(name):
    executable = shutil.which(name)
    if not executable and name == "kimi":
        candidate = Path.home() / ".kimi-code" / "bin" / "kimi.exe"
        executable = str(candidate) if candidate.exists() else None
    if not executable:
        return {"available": False}
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10)
        version = re.search(r"\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.]+)?", result.stdout)
        return {"available": True, "version": version.group(0) if version else "unknown", "exit_code": result.returncode}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "version": "unavailable"}


def doctor(root=ROOT, *, versions=True, user_home=None, probes=True):
    sys.path.insert(0, str(root / "skills" / "_shared"))
    from bitrix_config import Config, ToolError
    targets = agent_targets(user_home)
    report = {"harness_version": __version__, "python": sys.version.split()[0], "agents": {}, "warnings": []}
    try:
        revision = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=10)
        report["git_revision"] = revision.stdout.strip() if revision.returncode == 0 else None
        report["working_tree_dirty"] = bool(status.stdout) if status.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        report["git_revision"], report["working_tree_dirty"] = None, None
        report["warnings"].append("git_inspection_unavailable")
    feature_report = capabilities(root, user_home=user_home, probes=probes)
    report["source_version"] = feature_report["source_version"]
    report["warnings"].extend(feature_report["warnings"])
    if feature_report["source_version"] is not None and feature_report["source_version"] != __version__:
        report["warnings"].append("harness_version_mismatch")
    for name, target in targets.items():
        state = {"target": str(target), "exists": target.exists()}
        if versions:
            state["cli"] = binary_version(name)
        state["features"] = feature_report["agents"][name]
        skills = state["features"]["skills"]
        # Retain the original summary keys for existing doctor consumers.
        if name == "kimi":
            state["registered"] = skills["configured"]
            state["configured_directory_count"] = skills.get("configured_directory_count", 0)
        else:
            for key in ("missing", "different", "obsolete_managed"):
                state[key] = skills.get(key, [])
            state["managed"] = skills["managed"]
        report["agents"][name] = state
    legacy = Path(os.environ.get("CODEX_HOME", str(Path(user_home or Path.home()) / ".codex"))) / "skills"
    report["legacy_codex_duplicates"] = [p.parent.name for p in (root / "skills").glob("*/SKILL.md")
                                         if (legacy / p.parent.name / "SKILL.md").exists()]
    if report["legacy_codex_duplicates"]:
        report["warnings"].append("legacy_codex_duplicates")
    report["environment_present"] = {key: bool(os.environ.get(key)) for key in
        ("BITRIX_PORTAL_URL", "BITRIX_WEBHOOK_USER_ID", "BITRIX_WEBHOOK_TOKEN", "BITRIX_CA_BUNDLE", "BITRIX_WEBHOOK",
         "GITLAB_HOST", "GITLAB_TOKEN", "GITLAB_CA_BUNDLE")}
    try:
        config = Config.load()
        report["bitrix"] = {"configured": True, "timeout_seconds": config.timeout,
                            "read_retries": config.read_retries, "tls_verification": True,
                            "profile_users": len(config.profile.get("users", {})), "profile_chats": len(config.profile.get("chats", {}))}
    except ToolError as exc:
        report["bitrix"] = {"configured": False, "error_code": exc.code}
        report["warnings"].append("bitrix_not_configured_in_this_process")
    from gitlab_config import Config as GitLabConfig
    from gitlab_http import Client as GitLabClient
    configured = any(os.environ.get(key) for key in
                     ("GITLAB_HOST", "GITLAB_TOKEN", "GITLAB_PROFILE", "GITLAB_CA_BUNDLE"))
    configured |= os.environ.get("GITLAB_ALLOW_INSECURE_HTTP") == "1"
    report["gitlab"] = {"configured": False, "status": "not_configured", "api_probed": False}
    if configured:
        try:
            config = GitLabConfig.load()
            GitLabClient(config)  # Construct TLS context only; no API calls.
            transport = urlsplit(config.host).scheme
            report["gitlab"].update(configured=True, status="configured", timeout_seconds=config.timeout,
                                    read_retries=config.read_retries, transport=transport,
                                    tls_verification=transport == "https",
                                    profile_projects=len(config.profile.get("gitlab_projects", {})))
        except ToolError as exc:
            report["gitlab"].update(status="error", error_code=exc.code)
            report["warnings"].append("gitlab_configuration_invalid")
    report["ok"] = not report["warnings"]
    return report
