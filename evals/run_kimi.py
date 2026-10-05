"""Run synthetic decision evaluations with a tool-free Kimi profile and private artifacts."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parse_answers(text):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "[":
            continue
        try:
            data, _ = decoder.raw_decode(text[index:])
            if isinstance(data, list) and data and all(isinstance(row, dict) and "id" in row for row in data):
                return data
        except ValueError:
            pass
    raise ValueError("Model output did not contain a decision array.")


def main(argv=None):
    from harness_cli.evals import evaluate, prompt
    from harness_cli.install import home
    parser = argparse.ArgumentParser(description="Run one Kimi call over 15 synthetic decision cases; no tools are available.")
    parser.add_argument("--kimi", default=shutil.which("kimi"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
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
    context = prompt()
    skills, cases = context.rsplit("\nSCENARIOS:\n", 1)
    definition = (ROOT / "evals" / "kimi-decisions.md").read_text(encoding="utf-8")
    agent_file = directory / "agent.md"
    agent_file.write_text(definition + "\n" + skills, encoding="utf-8")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("BITRIX_") and key not in ("GH_TOKEN", "GITHUB_TOKEN")}
    command = [executable, "--agent-file", str(agent_file), "--skills-dir", str(directory / "empty-skills"),
               "--prompt", "Return the JSON decisions for these independent scenarios:\n" + cases,
               "--output-format", "text"]
    try:
        result = subprocess.run(command, cwd=directory, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=args.timeout)
        (directory / "stdout.txt").write_text(result.stdout, encoding="utf-8")
        (directory / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            raise ValueError("Kimi exited unsuccessfully; inspect private artifacts.")
        answers = parse_answers(result.stdout)
        submission = directory / "decisions.json"
        submission.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
        report = evaluate(submission)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        report = {"ok": False, "error": "Model evaluation did not complete; inspect private artifacts or retry explicitly."}
    report["artifacts"] = str(directory)
    report["model_executed"] = True
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
