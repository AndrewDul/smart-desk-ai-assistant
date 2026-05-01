#!/usr/bin/env bash
set -u

PID="${1:-}"
WIDTH="${2:-1280}"
HEIGHT="${3:-800}"
X="${4:-0}"
Y="${5:-0}"
DURATION_SEC="${6:-10}"

if [ -z "$PID" ]; then
  exit 0
fi

if ! command -v xdotool >/dev/null 2>&1; then
  echo "Visual Shell window enforcer skipped: xdotool is not installed." >&2
  exit 0
fi

END=$((SECONDS + DURATION_SEC))

while [ "$SECONDS" -lt "$END" ]; do
  if ! kill -0 "$PID" 2>/dev/null; then
    exit 0
  fi

  WIDS="$(xdotool search --pid "$PID" 2>/dev/null || true)"

  if [ -z "$WIDS" ]; then
    WIDS="$(xdotool search --onlyvisible --class godot 2>/dev/null || true)"
  fi

  if [ -z "$WIDS" ]; then
    WIDS="$(xdotool search --onlyvisible --name Godot 2>/dev/null || true)"
  fi

  for WID in $WIDS; do
    xdotool windowmap "$WID" 2>/dev/null || true
    xdotool windowsize "$WID" "$WIDTH" "$HEIGHT" 2>/dev/null || true
    xdotool windowmove "$WID" "$X" "$Y" 2>/dev/null || true
  done

  sleep 0.15
done
