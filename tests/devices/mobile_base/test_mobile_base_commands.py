from __future__ import annotations

import pytest

from modules.devices.mobile_base.commands import (
    MobileBaseCommandError,
    build_ros_velocity_command,
    build_wheel_velocity_command,
    build_stop_command,
    build_stop_sequence,
    serialize_json_line,
)


def test_build_stop_command_uses_zero_velocity() -> None:
    assert build_stop_command() == {"T": 13, "X": 0.0, "Z": 0.0}


def test_stop_sequence_repeats_stop_only() -> None:
    assert build_stop_sequence(repeat=3) == [
        {"T": 13, "X": 0.0, "Z": 0.0},
        {"T": 13, "X": 0.0, "Z": 0.0},
        {"T": 13, "X": 0.0, "Z": 0.0},
    ]


def test_rejects_invalid_stop_repeat() -> None:
    with pytest.raises(MobileBaseCommandError):
        build_stop_sequence(repeat=0)

    with pytest.raises(MobileBaseCommandError):
        build_stop_sequence(repeat=11)


def test_ros_velocity_command_rejects_non_finite_values() -> None:
    with pytest.raises(MobileBaseCommandError):
        build_ros_velocity_command(linear_x_mps=float("nan"), angular_z_rad_s=0.0)


def test_serialize_json_line_is_compact_and_newline_terminated() -> None:
    assert serialize_json_line(build_stop_command()) == '{"T":13,"X":0.0,"Z":0.0}\n'


def test_build_wheel_velocity_command_uses_left_right_velocity() -> None:
    assert build_wheel_velocity_command(left_mps=-0.12, right_mps=0.12) == {"T": 1, "L": -0.12, "R": 0.12}


def test_wheel_stop_profile_uses_left_right_zero_velocity() -> None:
    assert build_stop_command(command_profile="wheel") == {"T": 1, "L": 0.0, "R": 0.0}
    assert build_stop_sequence(repeat=2, command_profile="wheel") == [
        {"T": 1, "L": 0.0, "R": 0.0},
        {"T": 1, "L": 0.0, "R": 0.0},
    ]
