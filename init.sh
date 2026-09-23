#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

venv_dir="${PSKA_VENV_DIR:-.venv}"
python_bin="$venv_dir/bin/python"
ruff_bin="$venv_dir/bin/ruff"

if [[ ! -x "$python_bin" || ! -x "$ruff_bin" ]]; then
  echo "Project environment is missing or incomplete at: $venv_dir" >&2
  echo "Create/sync the isolated environment using docs/DEPENDENCY_BASELINE.md; do not install into system Python." >&2
  exit 2
fi

echo "[1/4] pytest"
"$python_bin" -m pytest

echo "[2/4] ruff lint"
"$ruff_bin" check .

echo "[3/4] ruff format check"
"$ruff_bin" format --check .

echo "[4/4] whitespace/conflict check"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  GIT_PAGER=cat git diff --check
else
  echo "Skipped git diff --check: this copy has no Git metadata."
fi

echo "Harness verification passed."
