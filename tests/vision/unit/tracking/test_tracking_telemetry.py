from __future__ import annotations

import json

from modules.devices.vision.tracking.telemetry import VisionTrackingTelemetryWriter


def test_vision_tracking_telemetry_writer_persists_latest_snapshot_atomically(tmp_path) -> None:
    path = tmp_path / "vision_tracking_status.json"
    writer = VisionTrackingTelemetryWriter(path=path)

    writer.write_snapshot(
        {
            "event": "vision_tracking_plan",
            "dry_run": True,
            "movement_execution_enabled": False,
            "last_plan": {
                "has_target": True,
                "base_yaw_assist_required": True,
                "base_yaw_direction": "right",
                "base_forward_velocity": 0.0,
                "base_backward_velocity": 0.0,
            },
        }
    )

    payload = json.loads(path.read_text())

    assert payload["event"] == "vision_tracking_plan"
    assert payload["dry_run"] is True
    assert payload["movement_execution_enabled"] is False
    assert payload["last_plan"]["base_yaw_assist_required"] is True
    assert payload["last_plan"]["base_yaw_direction"] == "right"
    assert payload["last_plan"]["base_forward_velocity"] == 0.0
    assert payload["last_plan"]["base_backward_velocity"] == 0.0
