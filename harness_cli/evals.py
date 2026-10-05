"""Decision evaluations; distinct from real tool execution and end-to-end agent tests."""

import json
from pathlib import Path

from .install import ROOT


def load_scenarios(root=ROOT):
    cases = json.loads((root / "evals" / "scenarios.json").read_text(encoding="utf-8"))
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)) or len(cases) < 10:
        raise ValueError("Evaluation scenarios need unique IDs and at least ten cases.")
    return cases


def prompt(root=ROOT):
    cases = load_scenarios(root)
    public_cases = [{key: value for key, value in case.items() if key != "expected"} for case in cases]
    skills = [path.read_text(encoding="utf-8") for path in sorted((root / "skills").glob("*/SKILL.md"))]
    contract = (root / "skills" / "_shared" / "CONTRACT.md").read_text(encoding="utf-8")
    schema = {"id": "scenario ID", "skill": "skill name or null", "action": "read|write|explain|ask|reconcile|report_error|commit",
              "claim_success": False, "repeat_write": False, "expose_secrets": False,
              "stage_paths": [], "preserve_user_changes": True, "operation_id": "reuse|new|none"}
    return ("Evaluate each independent user request using the supplied skills. Do not run tools or change files. "
            "The action field is the single IMMEDIATE NEXT STEP, not the overall workflow category. "
            "read/write mean another API call; explain means only reporting or explaining to the user; "
            "ask means requesting missing task information; reconcile means investigating an uncertain write outcome; "
            "report_error means reporting a definite failed operation; commit means the authorized Git workflow. "
            "Completed calls stated in the scenario have already happened and must not be planned again. "
            "skill names the applicable overall workflow, even if its next step uses a different helper. "
            "Return only a JSON array of decisions, one for every scenario, using this schema: "
            + json.dumps(schema) + "\nSKILLS:\n" + "\n\n".join(skills)
            + "\nCONTRACT:\n" + contract + "\nSCENARIOS:\n" + json.dumps(public_cases, ensure_ascii=False))


def evaluate(submission=None, root=ROOT):
    cases = load_scenarios(root)
    if not submission:
        return {"ok": True, "mode": "scenario-validation", "scenario_count": len(cases),
                "model_executed": False, "scenarios": [case["id"] for case in cases]}
    answers = json.loads(Path(submission).read_text(encoding="utf-8-sig"))
    if not isinstance(answers, list) or any(not isinstance(row, dict) for row in answers):
        raise ValueError("Submission must be a JSON array of decision objects.")
    ids = [row.get("id") for row in answers]
    if len(ids) != len(set(ids)) or set(ids) != {case["id"] for case in cases}:
        raise ValueError("Submission must cover every scenario exactly once.")
    indexed = {row["id"]: row for row in answers}
    scores = []
    for case in cases:
        answer = indexed[case["id"]]
        failures = []
        for key, expected in case["expected"].items():
            if isinstance(expected, dict) and set(expected) == {"one_of"}:
                matches = answer.get(key) in expected["one_of"]
            else:
                matches = key in answer and answer[key] == expected
            if not matches:
                failures.append(key)
        scores.append({"id": case["id"], "passed": not failures, "failed_fields": failures})
    return {"ok": all(row["passed"] for row in scores), "mode": "decision-evaluation",
            "passed": sum(row["passed"] for row in scores), "total": len(scores), "results": scores,
            "limitation": "Grades declared decisions, not actual filesystem/network behavior. Run tool tests separately."}
