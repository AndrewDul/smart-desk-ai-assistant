from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_safe_center_recovery.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "waveshare_pan_tilt_safe_center_recovery",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_state(path: Path, *, x: float = 0.0, y: float = 80.0) -> None:
    path.write_text(
        json.dumps(
            {
                "port": "/dev/serial0",
                "baudrate": 115200,
                "x": x,
                "y": y,
                "marked_limits": {
                    "pan_left_x": -89.67032623,
                    "pan_right_x": 89.67032623,
                    "tilt_min_y": -18.0,
                    "tilt_max_y": 80.0,
                },
            }
        ),
        encoding="utf-8",
    )


def test_center_recovery_preview_does_not_open_serial_or_move_hardware(tmp_path, capsys) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path, x=0.0, y=80.0)

    exit_code = module.main(
        [
            "--settings",
            "config/settings.json",
            "--state",
            str(state_path),
            "--max-step",
            "2.0",
            "--speed",
            "35",
            "--acceleration",
            "35",
            "--settle",
            "0.15",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PREVIEW ONLY" in captured.out
    assert "no serial port opened" in captured.out
    assert "current_y=80.0" in captured.out
    assert "target_y=0.0" in captured.out
    assert "center recovery step" in captured.out
    assert '"T":133' in captured.out


def test_center_recovery_builds_small_step_waypoints_to_center() -> None:
    module = _load_module()

    waypoints = module.build_center_waypoints(current_x=0.0, current_y=80.0, max_step=2.0)

    assert waypoints[0] == (0.0, 78.0)
    assert waypoints[-1] == (0.0, 0.0)
    assert len(waypoints) == 40

    previous_y = 80.0
    for _, y in waypoints:
        assert abs(previous_y - y) <= 2.0
        previous_y = y


def test_center_recovery_execute_requires_all_confirmations(tmp_path, monkeypatch) -> None:
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
                "--execute",
            ]
        )
    except SystemExit as error:
        assert "--i-understand-this-moves-hardware" in str(error)
    else:
        raise AssertionError("Expected SystemExit when execute confirmation is missing.")


def test_center_recovery_rejects_request_above_step_limit(tmp_path) -> None:
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
                "--max-step",
                "4.0",
            ]
        )
    except SystemExit as error:
        assert "max step outside" in str(error)
    else:
        raise AssertionError("Expected SystemExit for unsafe max step.")


def test_center_recovery_rejects_current_pose_outside_limits(tmp_path) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path, x=0.0, y=120.0)

    try:
        module.main(
            [
                "--settings",
                "config/settings.json",
                "--state",
                str(state_path),
            ]
        )
    except SystemExit as error:
        assert "current pose" in str(error)
        assert "outside tilt limits" in str(error)
    else:
        raise AssertionError("Expected SystemExit for current pose outside limits.")


def test_center_recovery_refuses_total_delta_above_global_limit() -> None:
    module = _load_module()

    try:
        module.build_center_waypoints(current_x=120.0, current_y=80.0, max_step=2.0)
    except SystemExit as error:
        assert "Maximum allowed total delta" in str(error)
    else:
        raise AssertionError("Expected SystemExit for excessive total delta.")
