#!/usr/bin/env python3
"""Intercept recognizable literal secret-file reads before Kimi's Bash tool.

This is a partial command filter, NOT a shell parser or an OS sandbox. Variable
expansion, aliases, encodings, arbitrary scripts and indirect reads are outside
its coverage. Runtime errors fail open visibly, as required by Kimi's contract.
The proposed shell/Python command is inspected, never executed.
"""

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
import sys

if __package__:
    from ._common import InvalidPayload, emit, read_payload
else:
    from _common import InvalidPayload, emit, read_payload


@dataclass
class Token:
    value: str
    quoted: bool = False
    expanding: str = ""


OPERATORS = {";", "&&", "||", "|", "\n", "(", ")", "&", "<", ">", ">>", "<<"}
READERS = {
    "cat", "type", "more", "less", "head", "tail", "bat", "get-content", "gc",
    "select-string", "sls", "copy", "xcopy", "cp", "copy-item", "scp", "rsync",
    "tar", "zip", "7z", "base64", "xxd", "od", "strings", "hexdump", "sort", "uniq",
    "wc", "sed", "awk", "gawk", "cut", "paste", "certutil",
}
SHELLS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell", "cmd"}


def tokenize(command):
    """Preserve literal Windows backslashes and quoted strings; do not evaluate."""
    tokens = []
    value = []
    expanding = []
    quoted = False
    quote = None
    index = 0

    def finish():
        nonlocal value, expanding, quoted
        if value or quoted:
            tokens.append(Token("".join(value), quoted, "".join(expanding)))
            value = []
            expanding = []
            quoted = False

    while index < len(command):
        char = command[index]
        if quote:
            if char == quote:
                if quote == "'" and index + 1 < len(command) and command[index + 1] == "'":
                    value.append("'")
                    index += 2
                    continue
                quote = None
            elif char in ("\\", "`") and quote == '"' and index + 1 < len(command) and (
                command[index + 1] in ('"', "`", "$")
            ):
                value.append(command[index + 1])
                index += 2
                continue
            else:
                value.append(char)
                if quote == '"':
                    expanding.append(char)
        elif char in ("'", '"'):
            quote = char
            quoted = True
        elif char in ("\\", "`") and index + 1 < len(command) and command[index + 1].isspace():
            following = command[index + 1]
            if following == "\r" and index + 2 < len(command) and command[index + 2] == "\n":
                index += 1
                following = "\n"
            if following != "\n":
                value.append(following)
                expanding.append(following)
            index += 2
            continue
        elif char == "#" and not value:
            finish()
            newline = command.find("\n", index)
            if newline < 0:
                break
            tokens.append(Token("\n"))
            index = newline + 1
            continue
        elif char.isspace() and char != "\n":
            finish()
        elif char in ";|&<>\n()":
            finish()
            operator = char
            if index + 1 < len(command) and char == command[index + 1] and char in "|&<>":
                operator += char
                index += 1
            tokens.append(Token(operator))
        else:
            value.append(char)
            expanding.append(char)
        index += 1
    if quote:
        raise ValueError("unsupported_shell_syntax")
    finish()
    return tokens


def sensitive_path(value):
    value = value.strip().replace("\\", "/").strip('"\'')
    if not value or "://" in value:
        return False
    # curl @file and named options; a git revision:path is also a literal path.
    value = value.rsplit("=", 1)[-1].lstrip("@")
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    name = PurePosixPath(value).name.casefold()
    if name in {".env", ".env*"}:
        return True
    if name.startswith(".env."):
        return name.rsplit(".", 1)[-1] not in {"example", "sample", "template", "dist"}
    if name in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "id_*", "credentials",
                "credentials.json", "application_default_credentials.json", ".netrc", ".pypirc"}:
        return True
    return name.endswith((".key", ".p12", ".pfx")) or bool(
        re.fullmatch(r".*(?:private[-_]key|private)\.pem", name)
    )


def executable(token):
    return token.replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")


def python_reads_secret(code):
    """Recognize direct Python open/Path reads and simple literal assignments."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    literals = {}

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return literals.get(node.id)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            if name in {"Path", "PurePath", "PurePosixPath", "PureWindowsPath"} and node.args:
                parts = [literal(arg) for arg in node.args]
                if all(part is not None for part in parts):
                    return "/".join(parts)
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = literal(node.value)
            if value is not None:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        literals[target.id] = value
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else ""
        )
        if name == "open":
            path = literal(node.args[0]) if node.args else next(
                (literal(kw.value) for kw in node.keywords if kw.arg == "file"), None
            )
            mode = literal(node.args[1]) if len(node.args) > 1 else next(
                (literal(kw.value) for kw in node.keywords if kw.arg == "mode"), "r"
            )
            if isinstance(node.func, ast.Attribute) and (base := literal(node.func.value)) is not None:
                path = base
                mode = literal(node.args[0]) if node.args else next(
                    (literal(kw.value) for kw in node.keywords if kw.arg == "mode"), "r"
                )
            if path and sensitive_path(path) and (mode is None or "r" in mode or "+" in mode):
                return True
        if isinstance(node.func, ast.Attribute) and name in {"read_text", "read_bytes"}:
            path = literal(node.func.value)
            if path and sensitive_path(path):
                return True
        if name in {"copy", "copyfile", "copy2", "copyfileobj"} and node.args:
            path = literal(node.args[0])
            if path and sensitive_path(path):
                return True
    return False


def search_reads_secret(arguments):
    if "--files" in arguments:
        return False
    pattern_consumed = False
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        if arg in {"-f", "--file", "-g", "--glob", "--iglob"}:
            if index + 1 < len(arguments) and sensitive_path(arguments[index + 1]):
                return True
            index += 2
            continue
        if arg in {"-e", "--regexp"}:
            pattern_consumed = True
            index += 2
            continue
        if arg.startswith(("--file=", "--glob=", "--iglob=")) and sensitive_path(arg):
            return True
        if arg.startswith("-e") and len(arg) > 2:
            pattern_consumed = True
        elif not arg.startswith("-"):
            if not pattern_consumed:
                pattern_consumed = True
            elif sensitive_path(arg):
                return True
        index += 1
    return False


def segment_reads_secret(tokens, depth):
    if not tokens:
        return False
    arguments = [token.value for token in tokens]
    while arguments and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", arguments[0]) or
                         executable(arguments[0]) in {"sudo", "command", "exec", "env"}):
        arguments.pop(0)
    if not arguments:
        return False
    program = executable(arguments.pop(0))
    if program in SHELLS:
        for index, arg in enumerate(arguments):
            if arg.casefold() in {"-c", "-command", "/c"} and index + 1 < len(arguments):
                return command_reads_secret(" ".join(arguments[index + 1:]), depth + 1)
    if re.fullmatch(r"python(?:\d+(?:\.\d+)?)?|py", program):
        if "-c" in arguments:
            index = arguments.index("-c")
            return index + 1 < len(arguments) and python_reads_secret(arguments[index + 1])
        return False
    if program in {"rg", "grep", "egrep", "fgrep"}:
        return search_reads_secret(arguments)
    if program in {"curl", "curl.exe", "invoke-webrequest", "iwr", "invoke-restmethod", "irm"}:
        for index, arg in enumerate(arguments):
            lower = arg.casefold()
            if lower in {"--upload-file", "-t", "--config", "-k", "-infile"}:
                if index + 1 < len(arguments) and sensitive_path(arguments[index + 1]):
                    return True
            if "@" in arg and sensitive_path(arg.split("@", 1)[1]):
                return True
            if arg.startswith(("-T", "-K")) and sensitive_path(arg[2:]):
                return True
        return False
    if program == "git":
        # --status and path names are safe; commands that print/archive/stage contents are not.
        if any(arg in {"show", "diff", "grep", "archive", "add"} for arg in arguments):
            return any(sensitive_path(arg) for arg in arguments)
        return False
    return program in READERS and any(sensitive_path(arg) for arg in arguments)


def command_reads_secret(command, depth=0):
    if depth > 4:
        raise ValueError("command_nesting_limit")
    tokens = tokenize(command)
    segment = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        # Inspect literal command substitutions, including those inside quoted output strings.
        if "$(" in token.expanding:
            for nested in re.findall(r"\$\(([^()]*)\)", token.expanding):
                if command_reads_secret(nested, depth + 1):
                    return True
        if not token.quoted and token.value in {"<", "<<", ">", ">>"}:
            if index + 1 < len(tokens):
                if token.value == "<" and sensitive_path(tokens[index + 1].value):
                    return True
                index += 2
                continue
        if not token.quoted and token.value in OPERATORS:
            if segment_reads_secret(segment, depth):
                return True
            segment = []
        else:
            segment.append(token)
        index += 1
    return segment_reads_secret(segment, depth)


def main():
    try:
        payload = read_payload()
        command = payload["tool_input"].get("command")
        if not isinstance(command, str) or not command or len(command) > 65536:
            raise InvalidPayload("invalid_command")
        if command_reads_secret(command):
            emit("protect_secrets", "blocked", "sensitive_file_access")
            print("Recognizable secret-file read or upload blocked. Use variable names and .env.example; "
                  "do not print or upload secret values.", file=sys.stderr)
            return 2
    except InvalidPayload as error:
        emit("protect_secrets", "error", str(error), fail_open=True)
    except ValueError:
        emit("protect_secrets", "error", "unsupported_shell_syntax", fail_open=True)
    except Exception:
        emit("protect_secrets", "error", "internal_error", fail_open=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
