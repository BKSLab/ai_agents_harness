import json
import subprocess

import pytest

from harness_cli.checks import scan_bytes, scan_history
from harness_cli.evals import evaluate, load_scenarios, prompt


def test_scanner_does_not_print_private_values():
    value = b"a-private-profile-value"
    findings = scan_bytes(b"prefix " + value, "file.py", [value])
    assert findings == [{"location": "file.py", "rule": "private_profile_value"}]
    assert value.decode() not in json.dumps(findings)


def test_official_api_docs_are_not_customer_portals():
    assert not scan_bytes(b"https://apidocs.bitrix24.com/api-reference", "docs.md")
    host = b"https://" + b"customer" + b".bitrix24.com"
    assert scan_bytes(host, "file.py")[0]["rule"] == "portal_address"


def test_history_scanner_finds_removed_private_value(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Fixture")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Fixture")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "fixture@example.invalid")
    (root / "file.txt").write_text("private-fixture-value", encoding="utf-8")
    for action in (["add", "file.txt"], ["commit", "-m", "first"]):
        subprocess.run(["git", *action], cwd=root, capture_output=True, check=True)
    (root / "file.txt").write_text("clean", encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "clean"], cwd=root, capture_output=True, check=True)
    from harness_cli.install import home
    home().mkdir(parents=True)
    (home() / "publication-denylist.json").write_text('["private-fixture-value"]', encoding="utf-8")
    result = scan_history(root)
    assert result["findings"] and result["findings"][0]["rule"] == "private_profile_value"
    assert "private-fixture-value" not in json.dumps(result)


def test_eval_prompt_omits_answer_keys():
    content = prompt()
    assert '"expected"' not in content
    assert len(load_scenarios()) >= 15


def test_eval_grader_rejects_a_false_success(tmp_path):
    cases = load_scenarios()
    answers = [{"id": c["id"], **{k: v["one_of"][0] if isinstance(v, dict) and "one_of" in v else v
                                  for k, v in c["expected"].items()}} for c in cases]
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers), encoding="utf-8")
    assert evaluate(path)["passed"] == len(cases)
    next(a for a in answers if a["id"] == "timeout-after-write")["claim_success"] = True
    path.write_text(json.dumps(answers), encoding="utf-8")
    report = evaluate(path)
    assert not report["ok"] and report["passed"] == len(cases) - 1


def test_eval_grader_requires_every_case(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate(path)
