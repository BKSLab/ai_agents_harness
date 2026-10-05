"""Run synthetic decision evaluations with a tool-free Kimi profile and private artifacts."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Direct script execution needs the checkout import path established above.
from harness_cli.artifacts import run_command  # noqa: E402
from harness_cli.review_gate import model_aliases  # noqa: E402


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Model output contains duplicate object keys.")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Model output contains a non-JSON numeric constant.")


def parse_answers(text):
    if not isinstance(text, str):
        raise ValueError("Model output must be text containing one JSON array.")
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or lines[0] not in ("```", "```json") or lines[-1] != "```":
            raise ValueError("Model output must contain one complete JSON fence.")
        text = "\n".join(lines[1:-1])
    try:
        data = json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Model output must be one JSON array without duplicate keys or surrounding prose.") from exc
    if (not isinstance(data, list) or not data
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in data)):
        raise ValueError("Model output must be a nonempty array of decision objects with string IDs.")
    return data


def main(argv=None):
    from harness_cli.evals import evaluate, prompt
    from harness_cli.install import home
    parser = argparse.ArgumentParser(description="Run synthetic routing or decision cases with no tools available.")
    parser.add_argument("--kimi", default=shutil.which("kimi"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mode", choices=("routing", "decisions"), default="decisions")
    parser.add_argument("--admission", action="store_true", help="Apply strict decision screening; not a behavior gate.")
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--model", help="Configured Kimi model alias; defaults to the recorded configured default.")
    args = parser.parse_args(argv)
    try:
        evaluate(mode=args.mode, admission=args.admission, threshold=args.threshold)
    except ValueError as exc:
        parser.error(str(exc))
    if args.timeout < 1:
        parser.error("--timeout must be positive.")
    try:
        configured = model_aliases()
    except (OSError, ValueError, TypeError):
        parser.error("Kimi model configuration could not be read; inspect it locally without sharing credentials.")
    chosen_model = args.model if args.model is not None else configured.get("default")
    if (not configured.get("ok") or not isinstance(chosen_model, str) or not chosen_model
            or chosen_model not in configured.get("aliases", [])):
        parser.error("Choose an existing Kimi model alias or configure a valid default; no fallback model is used.")
    executable = args.kimi
    if not executable:
        candidate = Path.home() / ".kimi-code" / "bin" / "kimi.exe"
        executable = str(candidate) if candidate.exists() else None
    if not executable:
        parser.error("Kimi CLI was not found; supply --kimi.")
    directory = args.output_dir or home() / "evals" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = directory.resolve()
    if directory.is_relative_to(ROOT):
        parser.error("Keep evaluation artifacts outside the source repository.")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    (directory / "empty-skills").mkdir()
    context = prompt(mode=args.mode)
    (directory / "prompt.txt").write_text(context, encoding="utf-8")
    skills, cases = context.rsplit("\nSCENARIOS:\n", 1)
    definition = (ROOT / "evals" / "kimi-decisions.md").read_text(encoding="utf-8")
    agent_file = directory / "agent.md"
    agent_file.write_text(definition + "\n" + skills, encoding="utf-8")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("BITRIX_", "GH_", "GITHUB_"))}
    command = [executable, "--agent-file", str(agent_file), "--model", chosen_model,
               "--skills-dir", str(directory / "empty-skills"),
               "--prompt", "Return the JSON decisions for these independent scenarios:\n" + cases,
               "--output-format", "text"]
    started = time.monotonic()
    process = {"status": "error", "exit_code": None, "reason": "runner_error", "log": None}
    report = {"ok": False, "error": "Model evaluation did not complete; inspect private artifacts or retry explicitly."}
    try:
        process = run_command(command, directory, args.timeout, directory / "model-output.json", env=env)
        if process["status"] != "passed":
            raise ValueError("Kimi exited unsuccessfully; inspect private artifacts.")
        output = json.loads((directory / "model-output.json").read_text(encoding="utf-8"),
                            object_pairs_hook=unique_object, parse_constant=reject_constant)
        if not isinstance(output, dict) or output.get("stdout_truncated") is not False:
            raise ValueError("Complete model output is required for evaluation.")
        answers = parse_answers(output.get("stdout"))
        submission = directory / "decisions.json"
        submission.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
        report = evaluate(submission, mode=args.mode, admission=args.admission, threshold=args.threshold)
    except (ValueError, OSError, TypeError, KeyError, RecursionError, subprocess.SubprocessError):
        pass
    report["artifacts"] = str(directory)
    report["model"] = chosen_model
    report["model_selection"] = "explicit" if args.model is not None else "configured-default"
    report["evaluation_mode"] = args.mode
    report["process"] = process
    report["model_call_attempted"] = True
    report["model_executed"] = process.get("status") == "passed"
    report["decision_array_graded"] = "results" in report
    report["autonomous_ready"] = False
    report.setdefault("limitation", "Grades declared decisions, not actual tool behavior or native CLI skill discovery.")
    if args.admission:
        report.setdefault("admission", {"qualified": False, "autonomous_ready": False,
                                        "reason": "No valid complete model submission was graded."})
    report["context_sha256"] = hashlib.sha256((definition + "\n" + context).encode("utf-8")).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["tokens"] = None
    report["token_note"] = "Token usage is not reported by the text CLI transport."
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
