from __future__ import annotations

import ast
import json
from pathlib import Path


def _settings_dict_from_defaults_py() -> dict:
    path = Path("modules/shared/config/settings_core/defaults.py")
    tree = ast.parse(path.read_text())

    for node in tree.body:
        value = None

        if isinstance(node, ast.Assign):
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            value = node.value

        if not isinstance(value, ast.Dict):
            continue

        try:
            payload = ast.literal_eval(value)
        except Exception:
            continue

        if isinstance(payload, dict) and "vision" in payload and "pan_tilt" in payload:
            return payload

    raise AssertionError("Could not find the main defaults settings dictionary.")


def _assert_vision_tracking_contract(settings: dict) -> None:
    assert "vision_tracking" in settings

    tracking = settings["vision_tracking"]
    assert tracking["enabled"] is True
    assert tracking["persist_status"] is True
    assert tracking["status_path"] == "var/data/vision_tracking_status.json"

    policy = tracking["policy"]
    assert policy["enabled"] is True
    assert policy["dead_zone_x"] == 0.08
    assert policy["dead_zone_y"] == 0.10
    assert policy["pan_gain_degrees"] == 12.0
    assert policy["tilt_gain_degrees"] == 8.0
    assert policy["max_step_degrees"] == 2.0
    assert policy["limit_margin_degrees"] == 1.0
    assert policy["base_yaw_assist_edge_threshold"] == 0.42

    executor = tracking["motion_executor"]
    assert executor["dry_run"] is True
    assert executor["movement_execution_enabled"] is False
    assert executor["pan_tilt_movement_execution_enabled"] is False
    assert executor["base_yaw_assist_execution_enabled"] is False
    assert executor["base_forward_backward_movement_enabled"] is False

    adapter = tracking["pan_tilt_adapter"]
    assert adapter["dry_run"] is True
    assert adapter["backend_command_execution_enabled"] is False
    assert adapter["require_calibrated_limits"] is True
    assert adapter["require_no_motion_startup_policy"] is True
    assert adapter["max_allowed_pan_delta_degrees"] == 2.0
    assert adapter["max_allowed_tilt_delta_degrees"] == 2.0


def test_default_settings_define_safe_vision_tracking_execution_gates() -> None:
    settings = _settings_dict_from_defaults_py()

    _assert_vision_tracking_contract(settings)


def test_settings_example_defines_safe_vision_tracking_execution_gates() -> None:
    settings = json.loads(Path("config/settings.example.json").read_text())

    _assert_vision_tracking_contract(settings)


def test_current_settings_define_safe_vision_tracking_execution_gates() -> None:
    settings = json.loads(Path("config/settings.json").read_text())

    _assert_vision_tracking_contract(settings)
