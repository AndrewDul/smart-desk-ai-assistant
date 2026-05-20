#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$SCRIPT_PATH" != /* ]]; then
  SCRIPT_PATH="$(pwd)/$SCRIPT_PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_BIN="${NEXA_STACK_PYTHON:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${NEXA_STACK_PYTHON:-python3}"
fi

exec "$PYTHON_BIN" "$REPO_ROOT/scripts/start_nexa_product_runtime.py" --repo-root "$REPO_ROOT" "$@"
