from __future__ import annotations

import json
from pathlib import Path

from modules.runtime.stack_shutdown import request_stack_shutdown, stack_state_dir


def test_request_stack_shutdown_writes_request_file(tmp_path: Path) -> None:
    request_path = request_stack_shutdown(reason="unit_test", repo_root=tmp_path)

    assert request_path == tmp_path / "var" / "run" / "nexa_stack" / "shutdown.request"
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["reason"] == "unit_test"
    assert payload["requested_by_pid"] > 0


def test_stack_state_dir_honors_env_override(tmp_path: Path, monkeypatch) -> None:
    override = tmp_path / "custom-state"
    monkeypatch.setenv("NEXA_STACK_STATE_DIR", str(override))

    assert stack_state_dir(repo_root=tmp_path) == override
