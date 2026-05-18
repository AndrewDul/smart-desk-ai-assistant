from __future__ import annotations

from modules.runtime.turn_timeline import render_turn_timeline_line


def test_turn_timeline_formatter_quotes_unsafe_values() -> None:
    line = render_turn_timeline_line(
        turn_id="turn 1",
        event="heard_printed",
        text='show "system" status',
        delta_ms="12.3",
        ok=True,
    )

    assert line.startswith("[turn-timeline] ")
    assert "turn_id=turn_1" in line
    assert "event=heard_printed" in line
    assert 'text="show \\"system\\" status"' in line
    assert "delta_ms=12.3" in line
    assert "ok=true" in line


def test_turn_timeline_formatter_handles_missing_turn_id() -> None:
    line = render_turn_timeline_line(turn_id="", event="status_snapshot_started")

    assert line == "[turn-timeline] turn_id=- event=status_snapshot_started"
