from __future__ import annotations

from pathlib import Path


def test_async_notification_requests_one_shot_capture_force_close() -> None:
    source = Path("modules/core/flows/notification_flow/internals.py").read_text()

    assert "_force_next_capture_handoff_close" in source
    assert "Async notification requested force-close on next standby capture handoff" in source


def test_capture_handoff_prioritizes_force_close_before_soft_release() -> None:
    source = Path("modules/runtime/main_loop/capture_ownership.py").read_text()

    method = source.split("def _safe_release_runtime_component", 1)[1]

    force_close_index = method.index("_force_next_capture_handoff_close")
    soft_release_index = method.index("release_capture_ownership")

    assert force_close_index < soft_release_index
    assert "Capture handoff force-close consumed before soft release" in method
    assert 'return closed, "close" if closed else "none"' in method
