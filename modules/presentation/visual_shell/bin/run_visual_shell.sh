#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$SCRIPT_PATH" != /* ]]; then
  SCRIPT_PATH="$(pwd)/$SCRIPT_PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GODOT_APP_DIR="$REPO_ROOT/modules/presentation/visual_shell/godot_app"

VISUAL_SHELL_LOCK_FILE="${NEXA_VISUAL_SHELL_LOCK_FILE:-/tmp/nexa_visual_shell.lock}"
VISUAL_SHELL_AUDIO_DRIVER="${NEXA_VISUAL_SHELL_AUDIO_DRIVER:-Dummy}"
VISUAL_SHELL_VIDEO_DRIVER="${NEXA_VISUAL_SHELL_VIDEO_DRIVER:-GLES2}"
VISUAL_SHELL_RESOLUTION="${NEXA_VISUAL_SHELL_RESOLUTION:-1280x800}"

if ! command -v godot3 >/dev/null 2>&1; then
  echo "ERROR: godot3 command not found. Install it with: sudo apt install godot3" >&2
  exit 127
fi

if ! command -v flock >/dev/null 2>&1; then
  echo "ERROR: flock command not found. Install util-linux before starting Visual Shell." >&2
  exit 127
fi

if [ ! -f "$GODOT_APP_DIR/project.godot" ]; then
  echo "ERROR: Godot project not found at: $GODOT_APP_DIR/project.godot" >&2
  exit 2
fi

mkdir -p "$(dirname "$VISUAL_SHELL_LOCK_FILE")"
exec 9>"$VISUAL_SHELL_LOCK_FILE"

if ! flock -n 9; then
  echo "Visual Shell singleton guard: another launcher holds the lock."
  exit 0
fi

existing_pid="$(
python3 - "$GODOT_APP_DIR" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

target = Path(sys.argv[1]).resolve()

for proc in Path("/proc").iterdir():
    if not proc.name.isdigit():
        continue

    try:
        cwd = Path(os.readlink(proc / "cwd")).resolve()
        raw_cmdline = (proc / "cmdline").read_bytes()
    except OSError:
        continue

    if cwd != target:
        continue

    cmdline = raw_cmdline.replace(b"\x00", b" ").decode("utf-8", "ignore")
    if "godot3" not in cmdline and "godot" not in cmdline:
        continue

    print(proc.name)
    break
PY
)"

if [ -n "$existing_pid" ]; then
  echo "Visual Shell singleton guard: existing Visual Shell process detected pid=$existing_pid."
  exit 0
fi

cd "$GODOT_APP_DIR"

godot3 \
  --audio-driver "$VISUAL_SHELL_AUDIO_DRIVER" \
  --video-driver "$VISUAL_SHELL_VIDEO_DRIVER" \
  --resolution "$VISUAL_SHELL_RESOLUTION" \
  --position "0,0" \
  --path . \
  "$@" &

GODOT_PID="$!"

if [ -x "$SCRIPT_DIR/enforce_visual_shell_window.sh" ]; then
  "$SCRIPT_DIR/enforce_visual_shell_window.sh" "$GODOT_PID" 1280 800 0 0 10 &
fi

wait "$GODOT_PID"
