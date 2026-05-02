from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_official_absolute_side_test.py")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "waveshare_pan_tilt_official_absolute_side_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_sequence_uses_official_t133_side_only_absolute_control() -> None:
    module = load_module()

    sequence = module.build_sequence(
        degrees=1.5,
        speed=300,
        acc=120,
        pause_seconds=0.7,
    )

    movement_commands = [step["command"] for step in sequence if step["command"].get("T") == 133]

    assert movement_commands == [
        {"T": 133, "X": -1.5, "Y": 0, "SPD": 300, "ACC": 120},
        {"T": 133, "X": 0, "Y": 0, "SPD": 300, "ACC": 120},
        {"T": 133, "X": 1.5, "Y": 0, "SPD": 300, "ACC": 120},
        {"T": 133, "X": 0, "Y": 0, "SPD": 300, "ACC": 120},
    ]


def test_build_sequence_never_sends_vertical_or_continuous_gimbal_motion() -> None:
    module = load_module()

    sequence = module.build_sequence(
        degrees=2.0,
        speed=250,
        acc=100,
        pause_seconds=0.5,
    )

    for step in sequence:
        command = step["command"]
        assert command.get("T") != 134
        if command.get("T") == 133:
            assert command["Y"] == 0
            assert abs(float(command["X"])) <= 2.0


def test_hard_stop_uses_neutral_user_control_and_stop_only() -> None:
    module = load_module()

    class FakeSerial:
        def __init__(self) -> None:
            self.payloads: list[str] = []

        def write(self, payload: bytes) -> None:
            self.payloads.append(payload.decode("utf-8"))

        def flush(self) -> None:
            return

    fake = FakeSerial()
    sent = module.send_hard_stop(fake)

    assert len(sent) == 16
    assert sent[0] == {"T": 141, "X": 0, "Y": 0, "SPD": 0}
    assert sent[1] == {"T": 135}
    assert all(command in ({"T": 141, "X": 0, "Y": 0, "SPD": 0}, {"T": 135}) for command in sent)
