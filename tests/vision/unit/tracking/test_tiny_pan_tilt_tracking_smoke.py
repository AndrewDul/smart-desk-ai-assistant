from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_tiny_tracking_smoke.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "waveshare_pan_tilt_tiny_tracking_smoke",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_state(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "port": "/dev/serial0",
                "baudrate": 115200,
                "x": 0.0,
                "y": 0.0,
                "marked_limits": {
                    "pan_left_x": -15.0,
                    "pan_right_x": 15.0,
                    "tilt_min_y": -8.0,
                    "tilt_max_y": 8.0,
                },
            }
        ),
        encoding="utf-8",
    )


def test_tiny_smoke_preview_does_not_open_serial_or_move_hardware(tmp_path, capsys) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path)

    exit_code = module.main(
        [
            "--settings",
            "config/settings.json",
            "--state",
            str(state_path),
            "--pan-delta",
            "0.25",
            "--tilt-delta",
            "0.0",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PREVIEW ONLY" in captured.out
    assert "no serial port opened" in captured.out
    assert '"T":133' in captured.out
    assert "target_x=0.25" in captured.out


def test_tiny_smoke_rejects_delta_above_tiny_limit(tmp_path) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path)

    try:
        module.main(
            [
                "--settings",
                "config/settings.json",
                "--state",
                str(state_path),
                "--pan-delta",
                "0.75",
            ]
        )
    except SystemExit as error:
        assert "Maximum tiny pan delta" in str(error)
    else:
        raise AssertionError("Expected SystemExit for unsafe pan delta.")


def test_tiny_smoke_execute_requires_all_confirmations(tmp_path, monkeypatch) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path)
    monkeypatch.delenv(module.CONFIRM_ENV_NAME, raising=False)

    try:
        module.main(
            [
                "--settings",
                "config/settings.json",
                "--state",
                str(state_path),
                "--pan-delta",
                "0.25",
                "--execute",
            ]
        )
    except SystemExit as error:
        assert "--i-understand-this-moves-hardware" in str(error)
    else:
        raise AssertionError("Expected SystemExit when execute confirmation is missing.")


def test_tiny_smoke_rejects_target_outside_marked_limits(tmp_path) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    state_path.write_text(
        json.dumps(
            {
                "port": "/dev/serial0",
                "baudrate": 115200,
                "marked_limits": {
                    "pan_left_x": -0.1,
                    "pan_right_x": 0.1,
                    "tilt_min_y": -8.0,
                    "tilt_max_y": 8.0,
                },
            }
        ),
        encoding="utf-8",
    )

    try:
        module.main(
            [
                "--settings",
                "config/settings.json",
                "--state",
                str(state_path),
                "--pan-delta",
                "0.25",
            ]
        )
    except SystemExit as error:
        assert "outside marked calibration limits" in str(error)
    else:
        raise AssertionError("Expected SystemExit for target outside marked limits.")


def test_tiny_smoke_build_sequence_returns_to_center_and_stops() -> None:
    module = _load_module()

    sequence = module.build_sequence(
        target_x=0.25,
        target_y=0.0,
        speed=45,
        acceleration=45,
        settle=0.6,
    )

    assert sequence[0][1] == {"T": 135}
    assert sequence[4][0] == "center"
    assert sequence[5][0] == "tiny tracking target"
    assert sequence[6][0] == "return center"
    assert sequence[-1][0] == "final stop"
    assert sequence[-1][1] == {"T": 135}



def test_tiny_smoke_execute_rejects_non_centered_calibration_state(tmp_path, monkeypatch) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    state_path.write_text(
        json.dumps(
            {
                "port": "/dev/serial0",
                "baudrate": 115200,
                "x": 0.0,
                "y": 80.0,
                "marked_limits": {
                    "pan_left_x": -15.0,
                    "pan_right_x": 15.0,
                    "tilt_min_y": -8.0,
                    "tilt_max_y": 80.0,
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv(module.CONFIRM_ENV_NAME, module.CONFIRM_VALUE)

    try:
        module.main(
            [
                "--settings",
                "config/settings.json",
                "--state",
                str(state_path),
                "--pan-delta",
                "0.25",
                "--execute",
                "--i-understand-this-moves-hardware",
                "--confirm-text",
                module.CONFIRM_VALUE,
            ]
        )
    except SystemExit as error:
        assert "calibration state is not near center" in str(error)
        assert "Y=80.0" in str(error)
    else:
        raise AssertionError("Expected SystemExit for non-centered calibration state.")
