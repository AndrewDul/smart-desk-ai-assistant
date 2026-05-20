from __future__ import annotations

import json

from tests.runtime.diagnostics.look_at_me_runtime_evidence import build_report


def test_look_at_me_runtime_evidence_report_contains_builder_and_status_fields(tmp_path) -> None:
    output = tmp_path / "look_at_me_runtime_evidence.json"

    report = build_report(output=output)

    assert output.exists()
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["live_runtime_builder_wiring"]["runtime_builder"]["class"] == "RuntimeBuilder"
    assert "look_at_me_session_implementations" in loaded["live_runtime_builder_wiring"]
    assert "mobility_backend_evidence" in loaded
    assert "yaw_assist_evidence" in loaded
    assert "tilt_clamp_evidence" in loaded
    assert "test_gap_evidence" in loaded


def test_look_at_me_runtime_evidence_marks_negative_tilt_failure_from_status(tmp_path) -> None:
    output = tmp_path / "look_at_me_runtime_evidence.json"

    report = build_report(output=output)
    tilt = report["tilt_clamp_evidence"]

    if tilt["config_no_tilt_below_center"] and isinstance(
        tilt["look_at_me_status_tilt_command_degrees"],
        (int, float),
    ):
        expected = tilt["look_at_me_status_tilt_command_degrees"] < 0.0
        assert tilt["failure_negative_tilt_while_no_tilt_below_center"] is expected
