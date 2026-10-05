"""Offline validation; findings contain locations and categories, never matched values."""

import json
import os
import re
import shlex
import subprocess
import tomllib
from urllib.parse import urlsplit

import yaml

from .install import ROOT, home

PATTERNS = {
    "portal_address": re.compile(rb"https?://(?!apidocs\.|helpdesk\.|www\.)[A-Za-z0-9_-]+\.bitrix24\.[a-z.]+"),
    "literal_webhook": re.compile(rb"https?://[^\s\"'<>]+/rest/(?:api/)?[0-9]+/[A-Za-z0-9_-]{10,}"),
    "provider_key": re.compile(rb"(?:ghp_|github_pat_|sk-proj-|glpat-)[A-Za-z0-9_.-]{20,}"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
ROLE_TOOLS = {"reviewer": {"Read", "Grep", "Glob"},
              "implementer": {"Read", "Grep", "Glob", "Write", "Edit"}}


def check_agent_profiles(root=ROOT):
    """Validate maintained role capabilities; this is not a filesystem sandbox."""
    findings = []
    for path in sorted((root / "agents").glob("*.md")):
        location = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
            prefix, header, body = content.split("---", 2)
            if prefix.strip() or not body.strip():
                raise ValueError()
            node = yaml.compose(header)
            if not isinstance(node, yaml.MappingNode):
                raise ValueError()
            keys = [key.value for key, _ in node.value]
            if len(keys) != len(set(keys)):
                raise ValueError()
            metadata = yaml.safe_load(header)
            expected = ROLE_TOOLS[path.stem]
            if (not isinstance(metadata, dict) or set(metadata) != {"name", "description", "tools", "subagents"}
                    or metadata["name"] != path.stem
                    or not isinstance(metadata["description"], str) or not metadata["description"].strip()
                    or not isinstance(metadata["tools"], list)
                    or any(not isinstance(tool, str) for tool in metadata["tools"])
                    or len(metadata["tools"]) != len(expected) or set(metadata["tools"]) != expected
                    or metadata["subagents"] != []):
                raise ValueError()
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, yaml.YAMLError):
            findings.append({"location": location, "rule": "invalid_agent_profile"})
    return findings


def check_hook_references(root=ROOT):
    """Check template command references without executing shell code."""
    path = root / "config" / "kimi" / "hooks.toml"
    if not path.exists():
        return []
    location = path.relative_to(root).as_posix()
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        hooks = config["hooks"]
        if not isinstance(hooks, list) or not hooks:
            raise ValueError()
        for hook in hooks:
            if (not isinstance(hook, dict) or not isinstance(hook.get("command"), str)
                    or not isinstance(hook.get("event"), str) or not hook["event"]
                    or not isinstance(hook.get("matcher"), str) or not hook["matcher"]):
                raise ValueError()
            tokens = shlex.split(hook["command"])
            scripts = [token[len("<REPO>/"):] for token in tokens if token.startswith("<REPO>/")]
            if not scripts:
                raise ValueError()
            for script in scripts:
                target = (root / script).resolve()
                if not target.is_relative_to(root.resolve()) or target.suffix != ".py" or not target.is_file():
                    raise ValueError()
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return [{"location": location, "rule": "invalid_hook_reference"}]
    return []


def private_values():
    values = []
    path = home() / "publication-denylist.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or any(not isinstance(v, str) or len(v) < 4 for v in data):
            raise ValueError("Publication denylist must contain strings of at least four characters.")
        values.extend(data)
    for name in ("BITRIX_PORTAL_URL", "BITRIX_WEBHOOK_TOKEN", "BITRIX_WEBHOOK", "GITLAB_HOST", "GITLAB_TOKEN"):
        value = os.environ.get(name)
        if value and len(value) >= 8:
            values.append(value)
    try:
        parsed = urlsplit(os.environ.get("GITLAB_HOST", ""))
        for host in {parsed.netloc, parsed.hostname} - {None, ""}:
            if len(host) >= 4:
                values.append(host)
    except ValueError:
        pass
    return [v.encode("utf-8") for v in values]


def scan_bytes(data, location, denied=()):
    findings = [{"location": location, "rule": rule} for rule, pattern in PATTERNS.items() if pattern.search(data)]
    if any(value in data for value in denied):
        findings.append({"location": location, "rule": "private_profile_value"})
    return findings


def candidate_files(root=ROOT):
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=root, capture_output=True, check=True)
    return [root / p.decode("utf-8") for p in result.stdout.split(b"\0") if p]


def scan_history(root=ROOT, refs=None):
    denied = private_values()
    output = subprocess.check_output(["git", "rev-list", "--objects", *(refs or ["--all"])], cwd=root, text=True)
    findings, checked = [], 0
    for entry in output.splitlines():
        oid, _, name = entry.partition(" ")
        kind = subprocess.check_output(["git", "cat-file", "-t", oid], cwd=root, text=True).strip()
        if kind not in ("blob", "commit", "tag"):
            continue
        data = subprocess.check_output(["git", "cat-file", "-p", oid], cwd=root)
        checked += 1
        findings += scan_bytes(data, f"{oid[:12]}:{name or kind}", denied)
    return {"objects_checked": checked, "findings": findings}


def check(root=ROOT, *, history=False, refs=None):
    findings, names = check_agent_profiles(root) + check_hook_references(root), set()
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    for path in skills:
        location = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            if not text.startswith("---\n"):
                raise ValueError()
            _, header, body = text.split("---", 2)
            metadata = yaml.safe_load(header)
            name = metadata["name"]
            if (not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
                    or len(name) > 64 or name != path.parent.name or name in names
                    or not isinstance(metadata["description"], str) or not metadata["description"].strip()):
                raise ValueError()
            names.add(name)
            for ref in re.findall(r"(?:\]\(|`)((?:references|scripts|\.\./_shared)/[^)`\s]+)", body):
                if not (path.parent / ref.split("#")[0]).exists():
                    findings.append({"location": location, "rule": "missing_reference"})
        except (ValueError, KeyError, TypeError, yaml.YAMLError):
            findings.append({"location": location, "rule": "invalid_frontmatter"})
    denied, compiled = private_values(), 0
    for path in candidate_files(root):
        if not path.is_file():
            continue
        data = path.read_bytes()
        location = path.relative_to(root).as_posix()
        findings += scan_bytes(data, location, denied)
        if path.suffix == ".py":
            try:
                compile(data, str(path), "exec")
                compiled += 1
            except SyntaxError:
                findings.append({"location": location, "rule": "python_syntax"})
    result = {"ok": not findings, "skills": len(skills), "compiled_scripts": compiled, "findings": findings}
    if history:
        result["history"] = scan_history(root, refs)
        result["ok"] = result["ok"] and not result["history"]["findings"]
    return result
