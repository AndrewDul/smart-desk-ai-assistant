from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/run_vision_tracking_execution_readiness_check.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_vision_tracking_execution_readiness_check",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_settings() -> dict:
    return {
        "vision_tracking": {
            "enabled": True,
            "persist_status": True,
            "status_path": "var/data/vision_tracking_status.json",
            "policy": {
                "enabled": True,
                "dead_zone_x": 0.08,
                "dead_zone_y": 0.10,
                "pan_gain_degrees": 12.0,
                "tilt_gain_degrees": 8.0,
                "max_step_degrees": 2.0,
                "limit_margin_degrees": 1.0,
                "base_yaw_assist_edge_threshold": 0.42,
            },
            "motion_executor": {
                "dry_run": True,
                "movement_execution_enabled": False,
                "pan_tilt_movement_execution_enabled": False,
                "base_yaw_assist_execution_enabled": False,
                "base_forward_backward_movement_enabled": False,
            },
        },
        "pan_tilt": {
            "enabled": True,
            "backend": "waveshare_serial",
            "hardware_enabled": False,
            "motion_enabled": False,
            "dry_run": True,
            "startup_policy": "no_motion",
            "calibration_required": True,
            "allow_uncalibrated_motion": False,
            "safe_limits": {
                "pan_min_degrees": -15.0,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 15.0,
                "tilt_min_degrees": -8.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 8.0,
            },
            "max_step_degrees": 2.0,
        },
        "mobility": {
            "enabled": False,
            "safety_stop_enabled": True,
            "max_linear_speed": 0.3,
            "max_turn_speed": 0.5,
        },
    }


def test_checklist_command_accepts_safe_current_settings(capsys) -> None:
    module = _load_module()

    exit_code = module.main(["--settings", "config/settings.json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "tracking execution readiness checklist" in captured.out
    assert "[OK] validator passed: YES" in captured.out
    assert "[OK] physical movement is allowed: NO" in captured.out
    assert "[OK] pan-tilt execution is allowed: NO" in captured.out
    assert "[OK] base yaw assist execution is allowed: NO" in captured.out
    assert "[OK] base forward/backward movement is allowed: NO" in captured.out
    assert "Config is valid for continued dry-run vision tracking development." in captured.out
    assert "NOT a permission to execute physical pan-tilt movement" in captured.out


def test_checklist_command_rejects_unsafe_settings_file(tmp_path, capsys) -> None:
    module = _load_module()
    settings = _safe_settings()
    settings["vision_tracking"]["motion_executor"]["movement_execution_enabled"] = True

    settings_path = tmp_path / "unsafe_settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    exit_code = module.main(["--settings", str(settings_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[FAIL] validator passed: NO" in captured.out
    assert "Fix all ERROR issues before continuing." in captured.out
    assert "vision_tracking.motion_executor.movement_execution_enabled" in captured.out


def test_checklist_command_can_print_json_result(tmp_path, capsys) -> None:
    module = _load_module()
    settings_path = tmp_path / "safe_settings.json"
    settings_path.write_text(json.dumps(_safe_settings()), encoding="utf-8")

    exit_code = module.main(["--settings", str(settings_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["safe_to_execute_physical_motion"] is False
    assert payload["movement_execution_allowed"] is False
    assert payload["pan_tilt_execution_allowed"] is False
    assert payload["base_yaw_assist_execution_allowed"] is False
    assert payload["base_forward_backward_movement_allowed"] is False
