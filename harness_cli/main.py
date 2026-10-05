"""Manage a checked-out harness repository."""

import argparse
import json
from pathlib import Path
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
    install.add_argument("--components", nargs="+", choices=("skills", "instructions", "hooks", "agents"))
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--skip-versions", action="store_true")
    doctor.add_argument("--no-probes", action="store_true")
    commands.add_parser("capabilities")
    check = commands.add_parser("check")
    check.add_argument("--history", action="store_true")
    check.add_argument("--ref", action="append")
    operations = commands.add_parser("operations")
    operations.add_argument("--service", choices=("bitrix", "gitlab"), default="bitrix")
    evaluate = commands.add_parser("eval")
    evaluate.add_argument("--submission", help="Grade structured decisions produced for the published scenarios.")
    evaluate.add_argument("--mode", choices=("decisions", "routing"), default="decisions")
    evaluate.add_argument("--admission", action="store_true")
    evaluate.add_argument("--threshold", type=float, default=0.9)
    task = commands.add_parser("task", help="Persist task scope, checks, review and exact delivery permissions.")
    actions = task.add_subparsers(dest="task_command", required=True)
    for action in ("init", "plan", "approve", "status", "verify", "snapshot", "review", "recover", "release", "use",
                   "authorize", "check-authorization"):
        command = actions.add_parser(action)
        command.add_argument("id")
        command.add_argument("--project", type=Path, default=Path.cwd())
        if action == "init":
            command.add_argument("--title", required=True)
            command.add_argument("--mode", choices=("light", "standard", "high-risk"), default="standard")
            command.add_argument("--adopt-changes", nargs="*", default=[])
            command.add_argument("--journal", help="Existing project journal location; no files are created there.")
        if action in ("plan", "review"):
            command.add_argument("--input", required=True, type=Path)
        if action in ("approve", "recover", "release", "authorize"):
            command.add_argument("--reference", required=True, help="Reference to actual authorization or recovery evidence.")
        if action == "verify":
            command.add_argument("--snapshot")
        if action in ("authorize", "check-authorization"):
            command.add_argument("--action", required=True, choices=("commit", "push", "comment"))
            command.add_argument("--target", required=True)
    review_gate = commands.add_parser("review-gate", help="Run verified snapshot checks and a restricted Kimi reviewer.")
    review_gate.add_argument("id")
    review_gate.add_argument("--project", type=Path, default=Path.cwd())
    review_gate.add_argument("--model", required=True, help="Configured Kimi model alias; no automatic substitution.")
    review_gate.add_argument("--timeout", type=int, default=180)
    commands.add_parser("models", help="Show model aliases only, without provider credentials.")
    publication = commands.add_parser("export-public")
    publication.add_argument("--output", required=True, help="New directory outside this source repository.")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            from .install import install
            result = install(args.agents, dry_run=args.dry_run, replace_conflicts=args.replace_conflicts,
                             migrate_legacy=args.migrate_legacy_codex, components=args.components)
            result["ok"] = True
        elif args.command == "doctor":
            from .doctor import doctor
            result = doctor(versions=not args.skip_versions, probes=not args.no_probes)
        elif args.command == "capabilities":
            from .capabilities import capabilities
            result = capabilities()
        elif args.command == "check":
            from .checks import check
            result = check(history=args.history, refs=args.ref)
        elif args.command == "eval":
            from .evals import evaluate
            result = evaluate(args.submission, mode=args.mode, admission=args.admission, threshold=args.threshold)
        elif args.command == "task":
            result = task_command(args)
        elif args.command in ("review-gate", "models"):
            from .review_gate import model_aliases, review_gate
            result = model_aliases() if args.command == "models" else review_gate(
                args.id, args.project, args.model, timeout=args.timeout)
        elif args.command == "export-public":
            from .publication import export_public
            result = export_public(args.output)
        else:
            result = operation_history(args.service)
    except Exception as exc:
        message = str(exc) if type(exc) is ValueError else "Command failed; check local configuration and dependencies."
        result = {"ok": False, "error": type(exc).__name__, "message": message}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def operation_history(service):
    """Read the selected service's local journal; never call its API."""
    sys.path.insert(0, str(ROOT / "skills" / "_shared"))
    from bitrix_config import ToolError
    if service == "gitlab":
        from gitlab_config import Config
        from gitlab_state import Journal
    else:
        from bitrix_config import Config
        from bitrix_state import Journal
    try:
        config = Config.load()
        return {"ok": True, "operations": config.redact(Journal(config).recent())}
    except ToolError as exc:
        return {"ok": False, "error": exc.as_dict()}


def task_command(args):
    from . import tasks
    from .task_schemas import read_input
    action = args.task_command
    if action == "init":
        return tasks.init(args.id, args.project, args.title, args.mode, args.adopt_changes, args.journal)
    if action == "plan":
        return tasks.set_plan(args.id, args.project, read_input(args.input))
    if action == "approve":
        return tasks.approve(args.id, args.project, args.reference)
    if action == "verify":
        return tasks.verify(args.id, args.project, args.snapshot)
    if action == "snapshot":
        return tasks.snapshot(args.id, args.project)
    if action == "review":
        return tasks.review(args.id, args.project, read_input(args.input))
    if action == "recover":
        return tasks.recover(args.id, args.project, args.reference)
    if action == "release":
        return tasks.release(args.id, args.project, args.reference)
    if action == "authorize":
        return tasks.authorize(args.id, args.project, args.action, args.target, args.reference)
    if action == "check-authorization":
        return tasks.check_authorization(args.id, args.project, args.action, args.target)
    if action == "use":
        tasks.Store(args.project).activate(args.id)
    return tasks.status(args.id, args.project)
