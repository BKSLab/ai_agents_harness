"""Durable task evidence and scoped permissions for a cooperating agent/controller.

This journal is writable by its OS user. It is not a sandbox or an authorization
authority: references record permissions the user actually granted in the session.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import uuid

from .artifacts import (GIT_DEADLINE, check_private, digest, git, git_inventory, head_tree, index_tree, inventory,
                        project_root, python_for, redact, remaining_time, run_command, safe_relative,
                        supported_git_attributes)
from .install import atomic_write, home, json_bytes
from .task_schemas import ID, PLAN, REVIEW, validate


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    validate(value, ID)
    return value


class Store:
    def __init__(self, project):
        self.project = project_root(project)
        self.root = home() / "tasks"
        if self.root.is_relative_to(self.project):
            raise ValueError("Keep HARNESS_HOME outside the project being verified.")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.project_key = hashlib.sha256(os.path.normcase(str(self.project)).encode()).hexdigest()[:24]
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    key TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS active (project TEXT PRIMARY KEY, task_key TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY, task_key TEXT NOT NULL,
                    at TEXT NOT NULL, kind TEXT NOT NULL, details TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "tasks.sqlite3", timeout=remaining_time(5))
        try:
            with db:
                yield db
        finally:
            db.close()

    def key(self, task_id):
        return self.project_key + ":" + identifier(task_id)

    def directory(self, task_id):
        # Windows is case-insensitive; SQL task IDs are not. Hash artifact names.
        return self.root / self.project_key / ("task-" + digest(identifier(task_id))[:24])

    def load(self, task_id):
        with self.connect() as db:
            row = db.execute("SELECT revision,data FROM tasks WHERE key=?", (self.key(task_id),)).fetchone()
        if not row:
            raise ValueError("Task not found in this project.")
        state = json.loads(row[1])
        if state.get("schema_version") != 1:
            raise ValueError("Unsupported task state version.")
        state["revision"] = row[0]
        return state

    def save(self, state, kind, details=None, *, create=False):
        state = dict(state)
        revision = state.pop("revision", 0)
        state["updated_at"] = now()
        key = self.key(state["id"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if create:
                try:
                    db.execute("INSERT INTO tasks VALUES (?,?,?)", (key, 1, json.dumps(state, ensure_ascii=False)))
                except sqlite3.IntegrityError as exc:
                    raise ValueError("Task already exists; use status to resume it.") from exc
            else:
                changed = db.execute("UPDATE tasks SET revision=?,data=? WHERE key=? AND revision=?",
                                     (revision + 1, json.dumps(state, ensure_ascii=False), key, revision))
                if changed.rowcount != 1:
                    raise ValueError("Task changed concurrently; reload status before retrying.")
            db.execute("INSERT INTO events(task_key,at,kind,details) VALUES(?,?,?,?)",
                       (key, now(), kind, json.dumps(details or {}, ensure_ascii=False)))
        saved = self.load(state["id"])
        # Readable recovery view. Gates always consult SQLite, never this editable view.
        checkpoint = {key: value for key, value in saved.items()
                      if key not in ("baseline", "protected", "snapshots", "verifications", "reviews")}
        checkpoint["latest_verification"] = saved["verifications"][-1] if saved["verifications"] else None
        checkpoint["latest_review"] = saved["reviews"][-1] if saved["reviews"] else None
        checkpoint["snapshots"] = [{"id": key, "path": value["path"], "fingerprint": value["fingerprint"]}
                                   for key, value in saved["snapshots"].items()]
        try:
            atomic_write(self.directory(state["id"]) / "checkpoint.json", json_bytes(checkpoint))
        except OSError as exc:
            raise ValueError("Task state committed to SQLite, but checkpoint view could not be written. "
                             "Use task status before retrying.") from exc
        return saved

    def activate(self, task_id):
        self.load(task_id)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO active VALUES (?,?)", (self.project_key, self.key(task_id)))

    def active(self):
        with self.connect() as db:
            row = db.execute("SELECT task_key FROM active WHERE project=?", (self.project_key,)).fetchone()
        return row[0].split(":", 1)[1] if row else None


def mutable(state):
    if state.get("active_run"):
        raise ValueError("A verification is active. Wait or explicitly recover an interrupted run.")


def repository_identity(root):
    remotes = {}
    for remote in git(root, "remote").splitlines():
        urls = git(root, "remote", "get-url", "--push", "--all", remote).splitlines()
        if any(re.search(r"https?://[^/]*@", url) for url in urls):
            raise ValueError("Use credential helpers; do not embed credentials in Git remote URLs.")
        remotes[remote] = urls
    return {"root": str(root), "branch": git(root, "symbolic-ref", "--short", "HEAD", check=False),
            "remotes": remotes}


def valid_branch(root, branch):
    if not branch or branch.startswith(("-", "refs/")):
        return False
    try:
        git(root, "check-ref-format", "refs/heads/" + branch)
    except ValueError:
        return False
    return True


def init(task_id, project, title, mode="standard", adopt_changes=(), journal=None):
    if mode not in ("light", "standard", "high-risk"):
        raise ValueError("Unknown workflow mode.")
    identifier(task_id)
    check_private(title)
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Task title is required.")
    store = Store(project)
    baseline = inventory(store.project)
    # Track pre-existing modifications separately from changes owned by this task.
    dirty = set(git(store.project, "diff", "HEAD", "--name-only", "-z", check=False).split("\0"))
    dirty |= set(git(store.project, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    dirty.discard("")
    adopted = {safe_relative(path) for path in adopt_changes}
    if not adopted <= dirty:
        raise ValueError("Adopt only explicitly requested pre-existing changed paths.")
    if journal is not None:
        journal = safe_relative(journal)
    state = {"schema_version": 1, "id": task_id, "title": title, "mode": mode,
             "project": str(store.project), "repository": repository_identity(store.project),
             "base_sha": git(store.project, "rev-parse", "--verify", "HEAD"),
             "created_at": now(), "baseline": baseline,
             "protected": {path: baseline.get(path) for path in sorted(dirty - adopted)},
             "adopted": sorted(adopted), "journal": journal,
             "plan": None, "plan_hash": None, "approval": None, "grants": [],
             "verifications": [], "snapshots": {}, "reviews": [], "active_run": None}
    store.save(state, "created", {"mode": mode}, create=True)
    store.activate(task_id)
    return status(task_id, project)


def set_plan(task_id, project, plan):
    store, plan = Store(project), validate(plan, PLAN)
    state = store.load(task_id)
    mutable(state)
    check_private(plan)
    plan = json.loads(json.dumps(plan))
    plan["scope"] = [safe_relative(path) for path in plan["scope"]]
    checks = {check["id"] for check in plan["checks"]}
    if len(checks) != len(plan["checks"]):
        raise ValueError("Check IDs must be unique.")
    for category in ("acceptance", "risks"):
        ids = [item["id"] for item in plan[category]]
        if len(ids) != len(set(ids)):
            raise ValueError("Acceptance and risk IDs must be unique within their category.")
        if any(not set(item["checks"]) <= checks for item in plan[category]):
            raise ValueError("Every acceptance criterion and risk must reference defined checks.")
    if state["mode"] == "high-risk" and not all(plan.get(key) for key in ("rollback", "compatibility")):
        raise ValueError("High-risk work needs rollback and compatibility plans.")
    plan_hash = digest(plan)
    if state["plan_hash"] != plan_hash:
        state.update(plan=plan, plan_hash=plan_hash, approval=None, grants=[])
        store.save(state, "plan_updated", {"plan_hash": plan_hash})
    return status(task_id, project)


def approve(task_id, project, reference):
    store = Store(project)
    state = store.load(task_id)
    mutable(state)
    if not state["plan"] or not reference.strip():
        raise ValueError("A plan and a reference to actual user authorization are required.")
    check_private(reference)
    state["approval"] = {"plan_hash": state["plan_hash"], "reference": reference, "at": now()}
    store.save(state, "plan_approved", {"plan_hash": state["plan_hash"]})
    return status(task_id, project)


def approved(state):
    return bool(state["approval"] and state["approval"]["plan_hash"] == state["plan_hash"])


def scope_problems(state, current):
    problems = []
    changed = {p for p in set(current) | set(state["baseline"])
               if current.get(p) != state["baseline"].get(p)} | set(state["adopted"])
    if any(current.get(p) != value for p, value in state["protected"].items()):
        problems.append("preexisting_changes_modified")
    if state["plan"]:
        def inside(path):
            return any(s == "." or path == s or path.startswith(s.rstrip("/") + "/")
                       for s in state["plan"]["scope"])
        if any(not inside(p) for p in changed):
            problems.append("changes_outside_approved_scope")
    return problems


def matching_run(state, fingerprint, snapshot_id=None):
    return next((run for run in reversed(state["verifications"])
                 if run["fingerprint"] == fingerprint and run["plan_hash"] == state["plan_hash"]
                 and run.get("snapshot_id") == snapshot_id), None)


def status(task_id, project):
    store = Store(project)
    state = store.load(task_id)
    current = inventory(store.project)
    fingerprint = digest(current)
    blockers = scope_problems(state, current)
    if not state["plan"]:
        blockers.append("plan_missing")
    elif not approved(state):
        blockers.append("plan_not_approved")
    if repository_identity(store.project) != state["repository"]:
        blockers.append("repository_target_changed")
    if state["active_run"]:
        blockers.append("verification_in_progress")
    verification = matching_run(state, fingerprint)
    if not verification or verification["status"] != "passed":
        blockers.append("current_checks_not_passed")
    reviews = [r for r in state["reviews"] if r["plan_hash"] == state["plan_hash"]
               and r["fingerprint"] == fingerprint]
    review = reviews[-1] if reviews else None
    review_receipt = matching_run(state, fingerprint, review["snapshot_id"]) if review else None
    review_valid = (review and review["status"] == "approved" and review_receipt
                    and review_receipt["id"] == review["verification_id"] and review_receipt["status"] == "passed")
    model_attempts = state.get("review_gate_attempts", {}).get(state["plan_hash"], 0)
    if state["mode"] != "light" and not review_valid:
        blockers.append("independent_review_required")
        if model_attempts >= 3:
            blockers.append("model_review_attempt_limit")
    same_plan_reviews = [r for r in state["reviews"] if r["plan_hash"] == state["plan_hash"]]
    if len(same_plan_reviews) >= 3 and (not review or review["status"] != "approved"):
        blockers.append("review_iteration_limit")
    if len(same_plan_reviews) >= 2:
        previous, latest = same_plan_reviews[-2:]
        if (previous["status"] == latest["status"] == "changes_requested"
                and previous["fingerprint"] == latest["fingerprint"]
                and digest(previous["findings"]) == digest(latest["findings"])):
            blockers.append("review_no_progress")
    if not blockers:
        stage, next_step = "ready", "Perform only separately authorized delivery actions."
    elif "plan_missing" in blockers:
        stage, next_step = "planning", "Record acceptance, scope, risks and executable checks."
    elif "plan_not_approved" in blockers:
        stage, next_step = "awaiting_plan_approval", "Record the user's existing or newly obtained plan authorization."
    elif any(b in blockers for b in ("review_iteration_limit", "model_review_attempt_limit", "review_no_progress", "repository_target_changed",
                                    "preexisting_changes_modified", "changes_outside_approved_scope")):
        stage, next_step = "blocked", "Resolve the listed scope/evidence issue with the task owner."
    elif "verification_in_progress" in blockers:
        stage, next_step = "verifying", "Wait for the controller; recover only an interrupted run."
    elif "current_checks_not_passed" in blockers:
        stage, next_step = "implementing", "Run task verify after addressing failures or changed code."
    elif review and review["status"] != "approved":
        stage, next_step = review["status"], "Address evidenced findings or unavailable checks."
    else:
        stage, next_step = "reviewing", "Create a snapshot and obtain an independent review."
    return {"ok": True, "task_id": task_id, "title": state["title"], "mode": state["mode"],
            "stage": stage, "ready": not blockers, "blockers": blockers, "next_step": next_step,
            "fingerprint": fingerprint, "plan_hash": state["plan_hash"], "plan_approved": approved(state),
            "verification": verification, "review": review, "review_iterations": len(same_plan_reviews),
            "model_review_attempts": model_attempts, "model_review_attempt_limit": 3,
            "acceptance_count": len(state["plan"]["acceptance"]) if state["plan"] else 0,
            "risk_count": len(state["plan"]["risks"]) if state["plan"] else 0,
            "state_directory": str(store.directory(task_id)), "journal": state["journal"]}


def verify(task_id, project, snapshot_id=None):
    store = Store(project)
    state = store.load(task_id)
    mutable(state)
    if not approved(state):
        raise ValueError("Only an approved plan can execute checks.")
    current = inventory(store.project)
    if scope_problems(state, current) or repository_identity(store.project) != state["repository"]:
        raise ValueError("Scope or repository identity changed; inspect task status.")
    root = store.project
    fingerprint = digest(current)
    if snapshot_id:
        snapshot = state["snapshots"].get(identifier(snapshot_id))
        if not snapshot or snapshot["plan_hash"] != state["plan_hash"]:
            raise ValueError("Snapshot is missing or belongs to an older plan.")
        root = Path(snapshot["path"])
        if digest(inventory(root)) != snapshot["fingerprint"] or fingerprint != snapshot["fingerprint"]:
            raise ValueError("Snapshot or source changed; create a fresh snapshot.")
        fingerprint = snapshot["fingerprint"]
    run_id = "verify-" + uuid.uuid4().hex[:16]
    state["active_run"] = {"id": run_id, "started_at": now(), "snapshot_id": snapshot_id}
    state = store.save(state, "verification_started", state["active_run"])
    record = {"id": run_id, "fingerprint": fingerprint, "plan_hash": state["plan_hash"],
              "snapshot_id": snapshot_id, "started_at": now(), "checks": [], "status": "error"}
    try:
        for check in state["plan"]["checks"]:
            command = [python_for(store.project) if arg == "{python}" else arg for arg in check["argv"]]
            output = store.directory(task_id) / "runs" / run_id / (digest(check["id"])[:24] + ".json")
            result = run_command(command, root, check.get("timeout_seconds", 120), output)
            record["checks"].append({"id": check["id"], **result})
        unchanged = (digest(inventory(root)) == fingerprint and digest(inventory(store.project)) == fingerprint)
        record["status"] = ("passed" if unchanged and all(c["status"] == "passed" for c in record["checks"])
                            else "failed")
        if not unchanged:
            record["reason"] = "files_changed_during_verification"
    except (OSError, ValueError, subprocess.SubprocessError):
        record["reason"] = "verification_controller_error"
    record["finished_at"] = now()
    latest = store.load(task_id)
    if not latest.get("active_run") or latest["active_run"]["id"] != run_id:
        raise ValueError("Verification was recovered or superseded; its result cannot authorize actions.")
    latest["active_run"] = None
    latest["verifications"].append(record)
    store.save(latest, "verification_finished", {"id": run_id, "status": record["status"]})
    return {"ok": record["status"] == "passed", **record}


def recover(task_id, project, reference):
    if not reference.strip():
        raise ValueError("Describe why the previous controller run is no longer active.")
    store = Store(project)
    state = store.load(task_id)
    if state.get("active_run"):
        interrupted = state.pop("active_run")
        state["active_run"] = None
        store.save(state, "verification_abandoned", {"run_id": interrupted["id"], "reference": redact(reference)})
    return status(task_id, project)


def release(task_id, project, reference):
    """Leave the managed task context without claiming delivery or completion."""
    if not reference.strip():
        raise ValueError("Record why this project is leaving the managed task context.")
    check_private(reference)
    store = Store(project)
    state = store.load(task_id)
    mutable(state)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        revision = db.execute("SELECT revision FROM tasks WHERE key=?", (store.key(task_id),)).fetchone()[0]
        if revision != state["revision"]:
            raise ValueError("Task changed concurrently; inspect status before releasing its context.")
        db.execute("DELETE FROM active WHERE project=? AND task_key=?", (store.project_key, store.key(task_id)))
        db.execute("INSERT INTO events(task_key,at,kind,details) VALUES(?,?,?,?)",
                   (store.key(task_id), now(), "context_released", json.dumps({"reference": reference})))
    return {"ok": True, "task_id": task_id, "active_task": store.active(), "delivery_claimed": False}


def snapshot(task_id, project):
    store = Store(project)
    state = store.load(task_id)
    mutable(state)
    if not approved(state):
        raise ValueError("Approve the plan before preparing its review snapshot.")
    manifest = inventory(store.project, inspect_contents=True)
    supported_git_attributes(store.project, manifest)
    fingerprint = digest(manifest)
    if scope_problems(state, manifest):
        raise ValueError("Resolve scope violations before review.")
    snapshot_id = "snapshot-" + uuid.uuid4().hex[:16]
    # Keep the Git workspace shallow: nested project/task hashes can push even
    # .git/objects past MAX_PATH on Windows. Existing packets retain their paths.
    directory = store.root.parent / "snapshots" / snapshot_id
    root = directory / "workspace"
    if directory.resolve().is_relative_to(store.project):
        raise ValueError("Keep snapshot storage outside the project being verified.")
    if os.name == "nt" and len(str(root)) > 200:
        raise ValueError("Snapshot workspace path is too long for Windows Git; use a shorter HARNESS_HOME.")
    directory.mkdir(parents=True, mode=0o700)
    root.mkdir(mode=0o700)
    for path, expected in manifest.items():
        data = (store.project / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError("Source changed while preparing snapshot; retry explicitly.")
        atomic_write(root / path, data)
        if os.name != "nt":
            (root / path).chmod(0o755 if expected["mode"] == "100755" else 0o644)
    git(root, "init", "--initial-branch=review")
    # Source-local .git/info/attributes is deliberately not copied. Re-evaluate
    # transformations in the new repository before Git can invoke a clean filter.
    supported_git_attributes(root, manifest)
    git(root, "add", "--all")
    for path, entry in manifest.items():
        if entry["mode"] == "100755":
            git(root, "update-index", "--chmod=+x", "--", path)
    git(root, "-c", "core.hooksPath=" + str(directory / "no-hooks"), "-c", "commit.gpgsign=false",
        "-c", "user.name=Harness Snapshot", "-c", "user.email=noreply@users.noreply.github.com",
        "commit", "--allow-empty", "-m", "Review snapshot")
    if digest(inventory(root)) != fingerprint or digest(inventory(store.project)) != fingerprint:
        raise ValueError("Source or copied snapshot changed; retry explicitly.")
    diff = git(store.project, "diff", "--no-ext-diff", "--no-textconv", state["base_sha"], check=False)
    atomic_write(directory / "changes.patch", (redact(diff) + "\n").encode())
    packet = {"schema_version": 1, "snapshot_id": snapshot_id, "fingerprint": fingerprint,
              "plan_hash": state["plan_hash"], "title": state["title"], "mode": state["mode"],
              "base_sha": state["base_sha"], "plan": state["plan"],
              "changed_paths": sorted({p for p in manifest.keys() | state["baseline"].keys()
                                       if manifest.get(p) != state["baseline"].get(p)} | set(state["adopted"])),
              "untracked_files": git(store.project, "ls-files", "--others", "--exclude-standard").splitlines(),
              "manifest": manifest, "path": str(root), "created_at": now()}
    atomic_write(directory / "packet.json", json_bytes(packet))
    state["snapshots"][snapshot_id] = packet
    store.save(state, "snapshot_created", {"snapshot_id": snapshot_id, "fingerprint": fingerprint})
    return {"ok": True, **packet, "packet": str(directory / "packet.json")}


def review(task_id, project, verdict):
    verdict = validate(verdict, REVIEW)
    check_private(verdict)
    store = Store(project)
    state = store.load(task_id)
    mutable(state)
    packet = state["snapshots"].get(verdict["snapshot_id"])
    current = digest(inventory(store.project))
    if (not approved(state) or not packet or verdict["fingerprint"] != current
            or packet["fingerprint"] != current or verdict["plan_hash"] != state["plan_hash"]
            or packet["plan_hash"] != state["plan_hash"]
            or digest(inventory(Path(packet["path"]))) != current):
        raise ValueError("Review references a stale/missing plan or snapshot.")
    receipt = next((r for r in state["verifications"] if r["id"] == verdict["verification_id"]), None)
    if (not receipt or receipt["snapshot_id"] != verdict["snapshot_id"]
            or receipt["fingerprint"] != current or receipt["plan_hash"] != state["plan_hash"]
            or receipt != matching_run(state, current, verdict["snapshot_id"])):
        raise ValueError("Review requires the latest controller-generated verification receipt for this snapshot.")
    findings = verdict["findings"]
    if len({f["id"] for f in findings}) != len(findings):
        raise ValueError("Finding IDs must be unique.")
    for finding in findings:
        location, separator, line = finding["location"].rpartition(":")
        if not separator or not line.isdigit() or int(line) < 1:
            raise ValueError("A finding needs a project-relative file:line location.")
        location = safe_relative(location)
        if location not in packet["manifest"] and location not in state["baseline"]:
            raise ValueError("Finding references a file outside the reviewed snapshot/base.")
    severe = any(f["severity"] in ("major", "blocker") for f in findings)
    if verdict["status"] == "approved" and (severe or receipt["status"] != "passed"):
        raise ValueError("Approval requires passing snapshot checks and no major/blocker findings.")
    if verdict["status"] == "changes_requested" and not findings:
        raise ValueError("Changes requested must include concrete findings.")
    if verdict["status"] == "blocked" and not verdict["limitations"]:
        raise ValueError("A blocked review must explain its missing evidence.")
    prior = [r for r in state["reviews"] if r["plan_hash"] == state["plan_hash"]]
    if len(prior) >= 3:
        raise ValueError("Review iteration limit reached; escalate and revise the plan with the owner.")
    state["reviews"].append({**verdict, "at": now()})
    store.save(state, "review_recorded", {"status": verdict["status"], "snapshot_id": verdict["snapshot_id"]})
    return status(task_id, project)


def authorize(task_id, project, action, target, reference):
    if action not in ("commit", "push", "comment") or not target or not reference.strip():
        raise ValueError("Record an explicit action, exact target and actual user authorization reference.")
    store = Store(project)
    state = store.load(task_id)
    mutable(state)
    if not approved(state):
        raise ValueError("Approve the current plan before recording delivery authorization.")
    identity = repository_identity(store.project)
    if identity != state["repository"]:
        raise ValueError("Repository identity changed; authorization cannot be expanded silently.")
    if action == "push":
        remote, slash, branch = target.partition("/")
        if not slash or remote not in identity["remotes"] or not valid_branch(store.project, branch):
            raise ValueError("Push target must identify an existing remote and exact branch: origin/main.")
    if action == "commit" and target != identity["branch"]:
        raise ValueError("Commit target must be the current branch.")
    check_private(reference)
    grant = {"action": action, "target": target, "reference": reference, "repository": identity,
             "plan_hash": state["plan_hash"], "at": now()}
    state["grants"] = [g for g in state["grants"] if (g["action"], g["target"]) != (action, target)] + [grant]
    store.save(state, "action_authorized", {"action": action, "target": target})
    return {"ok": True, "action": action, "target": target, "executed": False}


def check_authorization(task_id, project, action, target):
    store = Store(project)
    state = store.load(task_id)
    identity = repository_identity(store.project)
    permitted = approved(state) and any(g["action"] == action and g["target"] == target
                                       and g["plan_hash"] == state["plan_hash"] and g["repository"] == identity
                                       for g in state["grants"])
    readiness = status(task_id, project)
    unchanged = store.load(task_id)["revision"] == state["revision"]
    return {"ok": bool(permitted and readiness["ready"] and unchanged), "authorized": bool(permitted),
            "ready": readiness["ready"], "blockers": readiness["blockers"], "action": action, "target": target,
            "fingerprint": readiness["fingerprint"], "state_revision": state["revision"]}


def git_gate(project, action, target=None):
    budget = GIT_DEADLINE.set(time.monotonic() + 6)
    try:
        return _git_gate(project, action, target)
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError):
        return {"allowed": False, "managed": True, "reason": "task_evidence_unavailable"}
    finally:
        GIT_DEADLINE.reset(budget)


def _git_gate(project, action, target=None):
    # Do not create a registry or change settings merely because a hook was invoked.
    if not (home() / "tasks" / "tasks.sqlite3").is_file():
        return {"allowed": True, "managed": False, "reason": "unmanaged_project"}
    store = Store(project)
    task_id = store.active()
    if not task_id:
        return {"allowed": True, "managed": False, "reason": "unmanaged_project"}
    if action == "probe":
        return {"allowed": False, "managed": True, "task_id": task_id, "reason": "task_managed_project"}
    identity = repository_identity(store.project)
    if action == "commit":
        exact_target = identity["branch"]
    elif action == "push":
        target = target or {}
        remote, refspec = target.get("remote"), target.get("refspec")
        if not remote or not refspec or remote not in identity["remotes"]:
            return {"allowed": False, "managed": True, "reason": "explicit_push_target_required"}
        if (len(identity["remotes"][remote]) != 1
                or git(store.project, "config", "--bool", "--get", "push.followTags", check=False) == "true"
                or git(store.project, "config", "--bool", "--get", f"remote.{remote}.mirror", check=False) == "true"):
            return {"allowed": False, "managed": True, "reason": "push_expands_beyond_exact_target"}
        if ":" in refspec:
            source, refspec = refspec.split(":", 1)
            if source not in ("HEAD", identity["branch"]):
                return {"allowed": False, "managed": True, "reason": "push_source_not_reviewed"}
        elif refspec != identity["branch"]:
            return {"allowed": False, "managed": True, "reason": "push_source_not_reviewed"}
        branch = refspec.removeprefix("refs/heads/")
        if not valid_branch(store.project, branch):
            return {"allowed": False, "managed": True, "reason": "invalid_push_branch"}
        exact_target = remote + "/" + branch
    else:
        return {"allowed": False, "managed": True, "reason": "unsupported_git_action"}
    result = check_authorization(task_id, project, action, exact_target)
    if result["ok"]:
        state = store.load(task_id)
        current = inventory(store.project)
        if state["revision"] != result["state_revision"] or digest(current) != result["fingerprint"]:
            return {"allowed": False, "managed": True, "reason": "task_changed_during_git_gate"}
        expected = git_inventory(store.project, current)
        actual = index_tree(store.project) if action == "commit" else head_tree(store.project)
        reason = None
        if expected != actual:
            reason = "git_inputs_differ_from_verified_files"
        elif action == "commit":
            staged = set(git(store.project, "diff", "--cached", "--name-only", "-z").split("\0")) - {""}
            if staged & state["protected"].keys():
                reason = "preexisting_changes_staged"
        # Catch an ordinary concurrent edit during canonicalization as well.
        if digest(inventory(store.project)) != digest(current):
            reason = "files_changed_during_git_gate"
        if (store.load(task_id)["revision"] != state["revision"]
                or store.active() != task_id
                or repository_identity(store.project) != identity
                or actual != (index_tree(store.project) if action == "commit" else head_tree(store.project))):
            reason = "task_changed_during_git_gate"
        if reason:
            return {"allowed": False, "managed": True, "task_id": task_id, "target": exact_target,
                    "reason": reason, "hint": "Verify and review exactly the files being delivered. "
                    "Use an isolated checkout if unrelated local changes prevent that; never stage them automatically."}
    return {"allowed": result["ok"], "managed": True, "task_id": task_id, "target": exact_target,
            "reason": "ready_and_authorized" if result["ok"] else "task_not_ready_or_not_authorized",
            "blockers": result["blockers"]}
