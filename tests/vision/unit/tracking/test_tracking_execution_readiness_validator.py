from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/validate_vision_tracking_execution_readiness.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_vision_tracking_execution_readiness",
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
            "pan_tilt_adapter": {
                "dry_run": True,
                "backend_command_execution_enabled": False,
                "runtime_hardware_execution_enabled": False,
                "physical_movement_confirmed": False,
                "require_calibrated_limits": True,
                "require_no_motion_startup_policy": True,
                "max_allowed_pan_delta_degrees": 2.0,
                "max_allowed_tilt_delta_degrees": 2.0,
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


def test_validator_accepts_safe_dry_run_tracking_execution_contract() -> None:
    module = _load_module()

    result = module.validate_settings(_safe_settings())

    assert result["ok"] is True
    assert result["safe_to_execute_physical_motion"] is False
    assert result["movement_execution_allowed"] is False
    assert result["pan_tilt_execution_allowed"] is False
    assert result["base_yaw_assist_execution_allowed"] is False
    assert result["base_forward_backward_movement_allowed"] is False
    assert result["summary"]["errors"] == 0


def test_validator_rejects_enabled_tracking_motion_gates() -> None:
    module = _load_module()
    settings = _safe_settings()
    settings["vision_tracking"]["motion_executor"]["movement_execution_enabled"] = True
    settings["vision_tracking"]["motion_executor"]["pan_tilt_movement_execution_enabled"] = True
    settings["vision_tracking"]["motion_executor"]["base_yaw_assist_execution_enabled"] = True
    settings["vision_tracking"]["motion_executor"]["base_forward_backward_movement_enabled"] = True

    result = module.validate_settings(settings)

    assert result["ok"] is False
    issue_paths = {issue["path"] for issue in result["issues"]}
    assert "vision_tracking.motion_executor.movement_execution_enabled" in issue_paths
    assert "vision_tracking.motion_executor.pan_tilt_movement_execution_enabled" in issue_paths
    assert "vision_tracking.motion_executor.base_yaw_assist_execution_enabled" in issue_paths
    assert "vision_tracking.motion_executor.base_forward_backward_movement_enabled" in issue_paths


def test_validator_rejects_unsafe_pan_tilt_adapter_gates() -> None:
    module = _load_module()
    settings = _safe_settings()
    settings["vision_tracking"]["pan_tilt_adapter"]["dry_run"] = False
    settings["vision_tracking"]["pan_tilt_adapter"]["backend_command_execution_enabled"] = True
    settings["vision_tracking"]["pan_tilt_adapter"]["runtime_hardware_execution_enabled"] = True
    settings["vision_tracking"]["pan_tilt_adapter"]["physical_movement_confirmed"] = True
    settings["vision_tracking"]["pan_tilt_adapter"]["require_calibrated_limits"] = False
    settings["vision_tracking"]["pan_tilt_adapter"]["require_no_motion_startup_policy"] = False
    settings["vision_tracking"]["pan_tilt_adapter"]["max_allowed_pan_delta_degrees"] = 4.0
    settings["vision_tracking"]["pan_tilt_adapter"]["max_allowed_tilt_delta_degrees"] = 3.0

    result = module.validate_settings(settings)

    assert result["ok"] is False
    issue_paths = {issue["path"] for issue in result["issues"]}
    assert "vision_tracking.pan_tilt_adapter.dry_run" in issue_paths
    assert "vision_tracking.pan_tilt_adapter.backend_command_execution_enabled" in issue_paths
    assert "vision_tracking.pan_tilt_adapter.runtime_hardware_execution_enabled" in issue_paths
    assert "vision_tracking.pan_tilt_adapter.physical_movement_confirmed" in issue_paths
    assert "vision_tracking.pan_tilt_adapter.require_calibrated_limits" in issue_paths
    assert "vision_tracking.pan_tilt_adapter.require_no_motion_startup_policy" in issue_paths
    assert "vision_tracking.pan_tilt_adapter.max_allowed_pan_delta_degrees" in issue_paths
    assert "vision_tracking.pan_tilt_adapter.max_allowed_tilt_delta_degrees" in issue_paths


def test_validator_rejects_unsafe_pan_tilt_hardware_gates() -> None:
    module = _load_module()
    settings = _safe_settings()
    settings["pan_tilt"]["dry_run"] = False
    settings["pan_tilt"]["hardware_enabled"] = True
    settings["pan_tilt"]["motion_enabled"] = True
    settings["pan_tilt"]["allow_uncalibrated_motion"] = True

    result = module.validate_settings(settings)

    assert result["ok"] is False
    issue_paths = {issue["path"] for issue in result["issues"]}
    assert "pan_tilt.dry_run" in issue_paths
    assert "pan_tilt.hardware_enabled" in issue_paths
    assert "pan_tilt.motion_enabled" in issue_paths
    assert "pan_tilt.allow_uncalibrated_motion" in issue_paths


def test_validator_rejects_invalid_safe_limits() -> None:
    module = _load_module()
    settings = _safe_settings()
    settings["pan_tilt"]["safe_limits"]["pan_min_degrees"] = 20.0

    result = module.validate_settings(settings)

    assert result["ok"] is False
    assert any(issue["path"] == "pan_tilt.safe_limits" for issue in result["issues"])


def test_validator_cli_accepts_current_settings_json() -> None:
    module = _load_module()

    exit_code = module.main(["--settings", "config/settings.json", "--json"])

    assert exit_code == 0


def test_validator_cli_rejects_unsafe_settings_file(tmp_path) -> None:
    module = _load_module()
    settings = _safe_settings()
    settings["vision_tracking"]["motion_executor"]["movement_execution_enabled"] = True

    path = tmp_path / "unsafe_settings.json"
    path.write_text(json.dumps(settings))

    exit_code = module.main(["--settings", str(path), "--json"])

    assert exit_code == 1
