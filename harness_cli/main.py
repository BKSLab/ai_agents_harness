"""Manage a checked-out harness repository."""

import argparse
import json
import sys

from .install import ROOT


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Install, inspect and validate the agent harness.")
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install")
    install.add_argument("--agents", nargs="+", choices=("kimi", "claude", "codex"))
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--replace-conflicts", action="store_true")
    install.add_argument("--migrate-legacy-codex", action="store_true")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--skip-versions", action="store_true")
    check = commands.add_parser("check")
    check.add_argument("--history", action="store_true")
    check.add_argument("--ref", action="append")
    commands.add_parser("operations")
    evaluate = commands.add_parser("eval")
    evaluate.add_argument("--submission", help="Grade structured decisions produced for the published scenarios.")
    publication = commands.add_parser("export-public")
    publication.add_argument("--output", required=True, help="New directory outside this source repository.")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            from .install import install
            result = install(args.agents, dry_run=args.dry_run, replace_conflicts=args.replace_conflicts,
                             migrate_legacy=args.migrate_legacy_codex)
            result["ok"] = True
        elif args.command == "doctor":
            from .doctor import doctor
            result = doctor(versions=not args.skip_versions)
        elif args.command == "check":
            from .checks import check
            result = check(history=args.history, refs=args.ref)
        elif args.command == "eval":
            from .evals import evaluate
            result = evaluate(args.submission)
        elif args.command == "export-public":
            from .publication import export_public
            result = export_public(args.output)
        else:
            sys.path.insert(0, str(ROOT / "skills" / "_shared"))
            from bitrix_config import Config
            from bitrix_state import Journal
            result = {"ok": True, "operations": Journal(Config.load()).recent()}
    except Exception as exc:
        message = str(exc) if type(exc) is ValueError else "Command failed; check local configuration and dependencies."
        result = {"ok": False, "error": type(exc).__name__, "message": message}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1
