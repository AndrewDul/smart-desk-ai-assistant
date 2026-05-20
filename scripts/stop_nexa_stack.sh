#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$SCRIPT_PATH" != /* ]]; then
  SCRIPT_PATH="$(pwd)/$SCRIPT_PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_DIR="${NEXA_STACK_STATE_DIR:-$REPO_ROOT/var/run/nexa_stack}"
REQUEST_FILE="$STATE_DIR/shutdown.request"
TIMEOUT_SECONDS="${NEXA_STACK_STOP_TIMEOUT_SECONDS:-12}"

mkdir -p "$STATE_DIR"
printf '{"reason":"stop_script","requested_by_pid":%s}\n' "$$" > "$REQUEST_FILE"
echo "[stop-stack] shutdown requested: $REQUEST_FILE"

launcher_pid=""
if [[ -f "$STATE_DIR/launcher.pid" ]]; then
  launcher_pid="$(tr -cd '0-9' < "$STATE_DIR/launcher.pid" || true)"
fi

if [[ -n "$launcher_pid" ]] && kill -0 "$launcher_pid" 2>/dev/null; then
  echo "[stop-stack] waiting for launcher pid=$launcher_pid"
  deadline=$((SECONDS + TIMEOUT_SECONDS))
  while kill -0 "$launcher_pid" 2>/dev/null && (( SECONDS < deadline )); do
    sleep 0.2
  done

  if kill -0 "$launcher_pid" 2>/dev/null; then
    echo "[stop-stack] launcher did not exit before timeout; sending SIGTERM to pid=$launcher_pid"
    kill -TERM "$launcher_pid" 2>/dev/null || true
    deadline=$((SECONDS + 3))
    while kill -0 "$launcher_pid" 2>/dev/null && (( SECONDS < deadline )); do
      sleep 0.2
    done
    if ! kill -0 "$launcher_pid" 2>/dev/null; then
      echo "[stop-stack] launcher stopped after SIGTERM"
      exit 0
    fi
  else
    echo "[stop-stack] launcher stopped cleanly"
    exit 0
  fi
fi

python3 - "$STATE_DIR" <<'PY'
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

state_dir = Path(sys.argv[1])
state_path = state_dir / "state.json"
if not state_path.exists():
    print("[stop-stack] no state.json remains; nothing else to stop")
    raise SystemExit(0)

try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as error:
    print(f"[stop-stack] cannot read state.json: {error}")
    raise SystemExit(1)

children = list(state.get("children", []) or [])
owned = [item for item in children if bool(item.get("owned"))]
for sig, label, pause in (
    (signal.SIGINT, "SIGINT", 0.4),
    (signal.SIGTERM, "SIGTERM", 1.5),
    (signal.SIGKILL, "SIGKILL", 0.0),
):
    remaining = []
    for child in reversed(owned):
        name = str(child.get("name") or "unknown")
        pgid = int(child.get("pgid") or child.get("pid") or 0)
        if pgid <= 0:
            continue
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            print(f"[stop-stack] already stopped: {name} pgid={pgid}")
            continue
        except OSError:
            continue
        try:
            os.killpg(pgid, sig)
            print(f"[stop-stack] sent {label}: {name} pgid={pgid}")
            remaining.append(child)
        except ProcessLookupError:
            print(f"[stop-stack] already stopped: {name} pgid={pgid}")
        except OSError as error:
            print(f"[stop-stack] failed to signal {name} pgid={pgid}: {error}")
            remaining.append(child)
    owned = remaining
    if not owned:
        break
    if pause:
        time.sleep(pause)

for path in state_dir.iterdir():
    if path.is_file():
        try:
            path.unlink()
        except OSError as error:
            print(f"[stop-stack] failed to remove {path}: {error}")
try:
    state_dir.rmdir()
except OSError:
    pass
PY
