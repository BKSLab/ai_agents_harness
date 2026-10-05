"""Offline validation; findings contain locations and categories, never matched values."""

import json
import os
import re
import subprocess

import yaml

from .install import ROOT, home

PATTERNS = {
    "portal_address": re.compile(rb"https?://(?!apidocs\.|helpdesk\.|www\.)[A-Za-z0-9_-]+\.bitrix24\.[a-z.]+"),
    "literal_webhook": re.compile(rb"https?://[^\s\"'<>]+/rest/(?:api/)?[0-9]+/[A-Za-z0-9_-]{10,}"),
    "provider_key": re.compile(rb"(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_-]{20,}"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def private_values():
    values = []
    path = home() / "publication-denylist.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or any(not isinstance(v, str) or len(v) < 4 for v in data):
            raise ValueError("Publication denylist must contain strings of at least four characters.")
        values.extend(data)
    for name in ("BITRIX_PORTAL_URL", "BITRIX_WEBHOOK_TOKEN", "BITRIX_WEBHOOK"):
        value = os.environ.get(name)
        if value and len(value) >= 8:
            values.append(value)
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
    findings, names = [], set()
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
