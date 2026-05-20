from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_STACK_STATE_DIR = "var/run/nexa_stack"


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def stack_state_dir(*, repo_root: Path | None = None) -> Path:
    configured = os.environ.get("NEXA_STACK_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root = repo_root or default_repo_root()
    return root / DEFAULT_STACK_STATE_DIR


def request_stack_shutdown(
    *,
    reason: str = "runtime_exit_command",
    repo_root: Path | None = None,
) -> Path:
    state_dir = stack_state_dir(repo_root=repo_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / "shutdown.request"
    payload = {
        "reason": str(reason or "runtime_exit_command"),
        "requested_at": time.time(),
        "requested_by_pid": os.getpid(),
    }
    tmp_path = state_dir / "shutdown.request.tmp"
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(target)
    return target


__all__ = ["DEFAULT_STACK_STATE_DIR", "request_stack_shutdown", "stack_state_dir"]
