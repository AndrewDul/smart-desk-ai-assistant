from __future__ import annotations

import json

import pytest

from modules.devices.pan_tilt.waveshare_protocol import (
    build_tiny_smoke_sequence,
    compact_json_line,
    gimbal_simple_command,
)


def test_tiny_smoke_sequence_is_conservative_and_ordered() -> None:
    sequence = build_tiny_smoke_sequence(degrees=5.0, speed=80, acceleration=80)

    assert sequence == [
        {"T": 135},
        {"T": 137, "s": 0, "y": 0},
        {"T": 4, "cmd": 2},
        {"T": 210, "cmd": 1},
        {"T": 133, "X": 0.0, "Y": 0.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": 5.0, "Y": 0.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": 0.0, "Y": 0.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": -5.0, "Y": 0.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": 0.0, "Y": 0.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": 0.0, "Y": 5.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": 0.0, "Y": 0.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": 0.0, "Y": -5.0, "SPD": 80, "ACC": 80},
        {"T": 133, "X": 0.0, "Y": 0.0, "SPD": 80, "ACC": 80},
        {"T": 135},
    ]


def test_tiny_smoke_sequence_rejects_large_motion() -> None:
    with pytest.raises(ValueError, match="degrees must be between"):
        build_tiny_smoke_sequence(degrees=45.0, speed=80, acceleration=80)


def test_gimbal_command_rejects_fastest_speed_and_acceleration() -> None:
    with pytest.raises(ValueError, match="speed must be greater than 0"):
        gimbal_simple_command(x=1.0, y=0.0, speed=0, acceleration=80)

    with pytest.raises(ValueError, match="acceleration must be greater than 0"):
        gimbal_simple_command(x=1.0, y=0.0, speed=80, acceleration=0)


def test_compact_json_line_is_newline_terminated() -> None:
    line = compact_json_line({"T": 135})

    assert line == '{"T":135}\n'
    assert json.loads(line) == {"T": 135}
