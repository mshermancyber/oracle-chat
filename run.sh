#!/usr/bin/env bash
# Oracle launcher.
#
# Behaviour:
#   • First run (no .venv yet): runs venv setup in the foreground so you can
#     see the pip install progress + any errors.
#   • Subsequent runs: forks into a new session and returns immediately, so
#     the terminal you launched from isn't tied up.
#   • Pass `--foreground` (or set ORACLE_FOREGROUND=1) to stay attached —
#     useful for debugging crashes / seeing loguru output.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

# Strip --foreground (if present) before we recurse into the detached call
FOREGROUND=0
if [[ "${1:-}" == "--foreground" || "${ORACLE_FOREGROUND:-0}" == "1" ]]; then
    FOREGROUND=1
    [[ "${1:-}" == "--foreground" ]] && shift
fi

# First-run venv bootstrap is always foreground — user wants to see progress
if [[ ! -x "$VENV/bin/python" ]]; then
    echo "[oracle] First run — creating virtual environment at $VENV" >&2
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip >/dev/null
    "$VENV/bin/pip" install -r "$DIR/requirements.txt"
    echo "[oracle] venv ready." >&2
fi

# Detach into a new session unless we've been told otherwise OR we're already
# inside a detached child process. setsid -f forks + becomes session leader
# in one syscall; redirect IO so the parent shell sees a clean prompt.
if [[ "$FOREGROUND" -eq 0 && -z "${_ORACLE_DETACHED:-}" ]]; then
    export _ORACLE_DETACHED=1
    setsid -f "$VENV/bin/python" "$DIR/oracle.py" "$@" </dev/null >/dev/null 2>&1
    exit 0
fi

# Foreground path (debugging or already-detached child) — exec replaces this shell
exec "$VENV/bin/python" "$DIR/oracle.py" "$@"
