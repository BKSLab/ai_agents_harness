---
name: git-commit-push
description: "Безопасная подготовка git-коммита и push: проверка статуса, выбор только нужных файлов, базовые проверки, коммит по шаблону и отправка. Используй, когда пользователь явно просит закоммитить и запушить изменения."
---

# Git Commit Push

Use this skill only when the user explicitly asks to commit and push.

## Safety Rules

- Inspect `git status --short` first.
- Stage only files that belong to the current user request. Do not stage unrelated dirty files unless the user explicitly asks to include everything.
- Never revert user changes unless explicitly requested.
- Before committing, check for obvious secrets, debug prints, temporary files, and accidental large/generated files.
- Use non-interactive git commands.

## Procedure

1. Run `git status --short` and identify intended files.
2. Run relevant tests or linters for the changed area when practical.
3. Stage intended files with `git add -- <file1> <file2>`.
4. Review staged diff with `git diff --cached`.
5. Commit with Russian past-tense message:

```text
[BITRIX_ID] <type>: <описание>
```

Use type: `feat`, `fix`, `refactor`, `test`, `docs`, or `chore`.

6. Run `git push`.
7. Report commit hash, pushed branch, and any checks that were skipped.
