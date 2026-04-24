#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
GODOT_APP_DIR="$REPO_ROOT/modules/presentation/visual_shell/godot_app"

if ! command -v godot3 >/dev/null 2>&1; then
  echo "ERROR: godot3 command not found. Install it with: sudo apt install godot3" >&2
  exit 127
fi

if [ ! -f "$GODOT_APP_DIR/project.godot" ]; then
  echo "ERROR: Godot project not found at: $GODOT_APP_DIR/project.godot" >&2
  exit 2
fi

cd "$GODOT_APP_DIR"
exec godot3 --path . "$@"