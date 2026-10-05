#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for interpreter in python3 python; do
    if command -v "$interpreter" >/dev/null 2>&1 && "$interpreter" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        exec "$interpreter" "$repo_dir/install.py" "$@"
    fi
done
echo 'Python 3.11 or newer was not found.' >&2
exit 1
