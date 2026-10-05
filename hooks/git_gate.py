#!/usr/bin/env python3
"""Check managed-task evidence before recognizable literal git commit/push calls.

The gate does not execute the proposed command. It is a Kimi fail-open hook, not
a shell sandbox: aliases, indirect scripts and arbitrary expansion are outside
coverage. Ambiguous recognizable Git commands are refused for managed tasks.
"""

from pathlib import Path
import re
import sys

if __package__:
    from ._common import InvalidPayload, emit, read_payload
    from .protect_secrets import OPERATORS, SHELLS, executable, tokenize
else:
    from _common import InvalidPayload, emit, read_payload
    from protect_secrets import OPERATORS, SHELLS, executable, tokenize


def literal(value):
    return bool(value) and not any(char in value for char in "$`*?\n\r")


READ_ONLY_COMMANDS = {
    "status", "diff", "show", "log", "rev-parse", "ls-files", "ls-tree", "cat-file",
    "help", "version", "grep", "blame", "describe", "for-each-ref", "name-rev",
}
GLOBAL_FLAGS = {
    "-p", "--paginate", "-P", "--no-pager", "--no-replace-objects", "--no-lazy-fetch",
    "--no-optional-locks", "--no-advice", "--literal-pathspecs", "--glob-pathspecs",
    "--noglob-pathspecs", "--icase-pathspecs",
}
DISPLAY_FLAGS = {"-v", "--version", "-h", "--help", "--html-path", "--man-path", "--info-path", "--exec-path"}


def global_options(args, cwd):
    """Resolve -C across known globals; do not approximate alternate Git metadata/worktrees.

    Relative --git-dir/--work-tree use the final -C directory in Git, regardless
    of option order. Such overrides and unknown globals therefore mark the
    mutation target unresolved instead of falling back to the caller's cwd.
    """
    project, offset, ambiguous, unresolved = cwd, 0, False, False
    aliases = {}
    while offset < len(args):
        arg = args[offset]
        if arg in DISPLAY_FLAGS:
            return project, [], ambiguous, unresolved, aliases
        if arg == "-C":
            if offset + 1 >= len(args):
                unresolved = True
                break
            path = args[offset + 1]
            if path and (not literal(path) or path.startswith("~") or "%" in path):
                unresolved = True
            elif path:
                # A slash-rooted Windows spelling depends on the invoking shell's
                # MSYS path conversion; use an explicit C:/... literal instead.
                if sys.platform == "win32" and path.startswith("/"):
                    unresolved = True
                else:
                    project = (project / path).resolve()
            offset += 2
            continue
        if arg == "-c" or arg == "--config-env" or arg.startswith("--config-env="):
            ambiguous = True
            from_environment = arg.startswith("--config-env")
            if arg.startswith("--config-env="):
                setting = arg.split("=", 1)[1]
                offset += 1
            elif offset + 1 < len(args):
                setting = args[offset + 1]
                offset += 2
            else:
                unresolved = True
                break
            name, _, value = setting.partition("=")
            if name.casefold().startswith("alias."):
                aliases[name[6:].casefold()] = None if from_environment else value
            if name.casefold() in {"core.worktree", "core.bare", "include.path"} or name.casefold().startswith("includeif."):
                unresolved = True
            continue
        if arg in GLOBAL_FLAGS:
            offset += 1
            continue
        if arg.startswith("--git-dir=") or arg.startswith("--work-tree="):
            ambiguous = unresolved = True
            offset += 1
            continue
        if arg in {"--git-dir", "--work-tree", "--namespace", "--attr-source"}:
            ambiguous = unresolved = True
            offset += 2
            continue
        if arg.startswith("-"):
            # Unknown option arity is not a basis for concluding that a later
            # mutation targets an unmanaged repository.
            ambiguous = unresolved = True
            offset += 1
            continue
        break
    return project, args[offset:], ambiguous, unresolved, aliases


def git_invocation(args, cwd, complex_command):
    project, tail, ambiguous, unresolved, aliases = global_options(args, cwd)
    ambiguous |= complex_command
    seen_aliases = set()
    while tail and tail[0].casefold() in aliases and tail[0] not in READ_ONLY_COMMANDS | {"commit", "push"}:
        name = tail[0].casefold()
        expansion = aliases[name]
        if name in seen_aliases or expansion is None or expansion.startswith("!"):
            # Inline shell/config-env aliases may select a different repository.
            # Never label these unresolved executions as harmless unmanaged Git.
            return {"project": project, "action": "alias", "target": None,
                    "ambiguous": True, "unresolved_target": True}
        seen_aliases.add(name)
        expanded = tokenize(expansion)
        if any(not token.quoted and token.value in OPERATORS for token in expanded):
            return {"project": project, "action": "alias", "target": None,
                    "ambiguous": True, "unresolved_target": True}
        project, tail, _, alias_unresolved, more_aliases = global_options(
            [token.value for token in expanded] + tail[1:], project,
        )
        aliases.update(more_aliases)
        ambiguous = True
        unresolved |= alias_unresolved
    if not tail or tail[0] in READ_ONLY_COMMANDS:
        return None
    action = tail[0]
    if action not in {"commit", "push"}:
        if not unresolved:
            return None
        # An unknown global may have an argument before a later literal action.
        action = next((arg for arg in tail if arg in {"commit", "push"}), "")
        if not action:
            return None
        tail = tail[tail.index(action):]
    options = tail[1:]
    target = None
    if action == "commit":
        cursor = 0
        while cursor < len(options):
            value = options[cursor]
            if value in {"-m", "--message"} and cursor + 1 < len(options):
                cursor += 2
            elif value.startswith("--message=") or (value.startswith("-m") and len(value) > 2):
                cursor += 1
            else:
                ambiguous = True
                break
    else:
        if options[:1] == ["--"]:
            options = options[1:]
        if len(options) > 2 or any(not literal(arg) or arg.startswith(("-", "+")) for arg in options):
            ambiguous = True
        if options:
            target = {"remote": options[0], "refspec": options[1] if len(options) > 1 else None}
    return {"project": project, "action": action, "target": target,
            "ambiguous": ambiguous, "unresolved_target": unresolved}


def changed_directory(tokens, index, cwd):
    if executable(tokens[index].value) in {"popd", "pop-location"}:
        return cwd, True  # The previous directory stack is not part of the event.
    arguments = []
    for token in tokens[index + 1:]:
        if not token.quoted and token.value in OPERATORS:
            break
        arguments.append(token.value)
    if arguments and arguments[0].casefold() in {"-literalpath", "-path", "/d"}:
        arguments = arguments[1:]
    if len(arguments) != 1:
        return cwd, True
    path = arguments[0]
    if (not literal(path) or path.startswith(("-", "~")) or "%" in path
            or (sys.platform == "win32" and path.startswith("/"))
            or re.fullmatch(r"[A-Za-z]:", path)):
        return cwd, True
    return (cwd / path).resolve(), False


def invocations(command, cwd, depth=0):
    if depth > 4:
        raise InvalidPayload("command_nesting_limit")
    tokens = tokenize(command)
    complex_command = any(
        (not token.quoted and token.value in OPERATORS) or "$(" in token.expanding or "`" in token.expanding
        for token in tokens
    )
    if tokens and tokens[0].value == "&":
        tokens = tokens[1:]
        complex_command = any(
            (not token.quoted and token.value in OPERATORS) or "$(" in token.expanding or "`" in token.expanding
            for token in tokens
        )
    found = []
    index = 0
    current_cwd = cwd
    cwd_unresolved = False
    while index < len(tokens):
        starts_command = index == 0 or (
            not tokens[index - 1].quoted and tokens[index - 1].value in OPERATORS
        )
        start = index
        while start > 0 and (tokens[start - 1].quoted or tokens[start - 1].value not in OPERATORS):
            start -= 1
        prefix = tokens[start:index]
        wrapped_command = bool(prefix) and all(
            executable(token.value) in {"env", "sudo", "command", "exec"}
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token.value)
            for token in prefix
        )
        if not starts_command and not wrapped_command:
            index += 1
            continue
        program = executable(tokens[index].value)
        if program in {"cd", "set-location", "pushd", "push-location", "popd", "pop-location"}:
            current_cwd, unresolved_change = changed_directory(tokens, index, current_cwd)
            cwd_unresolved |= unresolved_change
        if program in SHELLS:
            for offset in range(index + 1, len(tokens) - 1):
                if tokens[offset].value.casefold() in {"-c", "-command", "/c"}:
                    script = tokens[offset + 1].value if tokens[offset + 1].quoted else " ".join(
                        token.value for token in tokens[offset + 1:]
                    )
                    nested = invocations(script, current_cwd, depth + 1)
                    for invocation in nested:
                        invocation["ambiguous"] = True
                        invocation["unresolved_target"] |= cwd_unresolved
                    found.extend(nested)
                    return found
        if program != "git":
            index += 1
            continue
        end = index + 1
        while end < len(tokens) and (tokens[end].quoted or tokens[end].value not in OPERATORS):
            end += 1
        args = [token.value for token in tokens[index + 1:end]]
        invocation = git_invocation(args, current_cwd, complex_command or index != 0)
        if invocation:
            invocation["unresolved_target"] |= cwd_unresolved
            # Literal shell variable overrides of Git's repository selection
            # are not inherited by the hook process and cannot be probed as cwd.
            if any(re.match(r"GIT_(?:DIR|WORK_TREE|COMMON_DIR|CONFIG[^=]*)=", token.value, re.I) for token in prefix):
                invocation["unresolved_target"] = True
            found.append(invocation)
        index = max(index + 1, end)
    return found


def check(project, action, target):
    # Installed as a repository-managed script with an explicit interpreter.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from harness_cli.tasks import git_gate
    return git_gate(project, action, target)


def inspect(payload, checker=check):
    tool_input = payload["tool_input"]
    command = tool_input.get("command")
    raw_cwd = tool_input.get("cwd", payload.get("cwd", str(Path.cwd())))
    if not isinstance(command, str) or not command or len(command) > 65536:
        raise InvalidPayload("invalid_command")
    if not isinstance(raw_cwd, str) or not raw_cwd or "\0" in raw_cwd:
        raise InvalidPayload("invalid_cwd")
    cwd = Path(raw_cwd).resolve()
    calls = invocations(command, cwd)
    if not calls:
        return True, "not_git_mutation", {}
    for invocation in calls:
        if invocation.get("unresolved_target"):
            return False, "ambiguous_git_target", {}
        if invocation["ambiguous"]:
            probe = checker(invocation["project"], "probe", None)
            if not isinstance(probe, dict) or not isinstance(probe.get("managed"), bool):
                raise InvalidPayload("invalid_gate_result")
            if probe["managed"]:
                return False, "ambiguous_git_command", {"task_id": probe.get("task_id")}
            continue
        result = checker(invocation["project"], invocation["action"], invocation["target"])
        if not isinstance(result, dict) or not isinstance(result.get("allowed"), bool):
            raise InvalidPayload("invalid_gate_result")
        if not result["allowed"]:
            return False, result.get("reason", "task_evidence_required"), {"task_id": result.get("task_id")}
        if len(calls) == 1:
            return True, result.get("reason", "task_evidence_valid"), {"task_id": result.get("task_id")}
    return True, "unmanaged", {}


def main():
    try:
        allowed, reason, details = inspect(read_payload())
        if reason != "not_git_mutation":
            emit("git_gate", "allowed" if allowed else "blocked", reason, **details)
        if not allowed:
            print("Managed task Git action blocked. Check task status, current verification/review, "
                  "and authorization for this exact action; use a separate literal git command.", file=sys.stderr)
            return 2
    except InvalidPayload as error:
        emit("git_gate", "error", str(error), fail_open=True)
    except ValueError:
        emit("git_gate", "error", "unsupported_shell_syntax", fail_open=True)
    except Exception:
        emit("git_gate", "error", "internal_error", fail_open=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
