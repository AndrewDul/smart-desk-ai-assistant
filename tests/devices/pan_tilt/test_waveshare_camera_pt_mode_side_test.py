from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_camera_pt_mode_side_test.py")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "waveshare_pan_tilt_camera_pt_mode_side_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sequence_sets_camera_pt_before_motion() -> None:
    module = load_module()

    sequence = module.build_sequence(degrees=8.0, speed=350, acc=120, pause_seconds=1.0)

    assert sequence[1]["label"] == "set_camera_pt_module"
    assert sequence[1]["command"] == {"T": 900, "main": 2, "module": 2}


def test_sequence_is_side_only() -> None:
    module = load_module()

    sequence = module.build_sequence(degrees=8.0, speed=350, acc=120, pause_seconds=1.0)

    for item in sequence:
        command = item["command"]
        if command.get("T") in {133, 134, 141}:
            assert command.get("Y", 0) == 0
        assert module.has_vertical_movement(command) is False


def test_final_stop_commands_are_safe() -> None:
    module = load_module()

    commands = module.build_final_stop_commands()

    assert commands
    for command in commands:
        assert command in (
            {"T": 134, "X": 0, "Y": 0, "SX": 0, "SY": 0},
            {"T": 141, "X": 0, "Y": 0, "SPD": 0},
            {"T": 135},
        )
