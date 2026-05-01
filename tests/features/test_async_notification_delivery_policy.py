from __future__ import annotations

from pathlib import Path


def test_async_notifications_do_not_request_global_audio_interrupt() -> None:
    source = Path("modules/core/flows/notification_flow/delivery.py").read_text()

    assert "reason=f\"async_notification:{source}\"" in source
    assert "interrupt_output=False" in source
    assert "interrupt_output=True" not in source.split(
        "reason=f\"async_notification:{source}\"",
        1,
    )[1].split(")", 1)[0]
