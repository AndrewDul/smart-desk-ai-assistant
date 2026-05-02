from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_axis_command_audit.py")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "waveshare_pan_tilt_axis_command_audit",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_probe_plan_is_side_only() -> None:
    module = load_module()

    probes = module.build_probe_plan(
        absolute_degrees=5.0,
        speed=400,
        acc=100,
        pulse_seconds=0.12,
        pause_seconds=0.8,
        include_y_axis=False,
    )

    assert probes
    for probe in probes:
        command = probe["command"]
        if command.get("T") in {133, 134, 141}:
            assert command.get("Y", 0) == 0


def test_default_probe_plan_covers_known_waveshare_control_families() -> None:
    module = load_module()

    probes = module.build_probe_plan(
        absolute_degrees=5.0,
        speed=400,
        acc=100,
        pulse_seconds=0.12,
        pause_seconds=0.8,
        include_y_axis=False,
    )

    families = {probe["family"] for probe in probes}

    assert "T133_ABSOLUTE_X" in families
    assert "T134_CONTINUOUS_X" in families
    assert "T141_UI_X" in families


def test_vertical_detection_catches_y_movement() -> None:
    module = load_module()

    assert module.command_has_vertical_motion({"T": 133, "X": 0, "Y": 0}) is False
    assert module.command_has_vertical_motion({"T": 133, "X": 0, "Y": 0.5}) is True
    assert module.command_has_vertical_motion({"T": 134, "X": 0, "Y": -0.5}) is True
    assert module.command_has_vertical_motion({"T": 141, "X": 0, "Y": 1}) is True


def test_final_stop_commands_are_only_neutral_or_stop() -> None:
    module = load_module()

    commands = module.build_final_stop_commands()

    assert commands
    for command in commands:
        assert command in (
            {"T": 134, "X": 0, "Y": 0, "SX": 0, "SY": 0},
            {"T": 141, "X": 0, "Y": 0, "SPD": 0},
            {"T": 135},
            {"T": 143, "cmd": 0},
        )
