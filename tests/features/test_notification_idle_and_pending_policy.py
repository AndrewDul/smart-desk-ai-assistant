from __future__ import annotations

from pathlib import Path


def test_async_notification_returns_visual_shell_to_idle() -> None:
    source = Path("modules/core/flows/notification_flow/internals.py").read_text()

    assert "notify_visual_shell_idle" in source
    assert 'source="notification_flow"' in source
    assert 'detail=f"{detail}:complete"' in source


def test_async_notification_uses_notification_voice_phase() -> None:
    source = Path("modules/core/flows/notification_flow/internals.py").read_text()

    assert "VOICE_PHASE_NOTIFICATION" in source
    assert "phase=VOICE_PHASE_NOTIFICATION" in source


def test_async_notification_uses_short_output_hold_when_supported() -> None:
    source = Path("modules/core/flows/notification_flow/internals.py").read_text()

    assert "notification_output_hold_seconds" in source
    assert "output_hold_seconds" in source
    assert "inspect.signature" in source


def test_async_notification_preserves_pending_interaction_context() -> None:
    context_source = Path("modules/core/flows/notification_flow/context.py").read_text()
    delivery_source = Path("modules/core/flows/notification_flow/delivery.py").read_text()

    assert "preserve_pending: bool = False" in context_source
    assert "if not preserve_pending:" in context_source
    assert "has_pending_interaction" in delivery_source
    assert "preserve_pending=has_pending_interaction" in delivery_source
    assert "close_active_window=not has_pending_interaction" in delivery_source
