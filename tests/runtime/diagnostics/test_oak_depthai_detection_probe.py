from __future__ import annotations

from tests.runtime.diagnostics import oak_depthai_detection_probe


def test_oak_probe_reports_usb_matches_without_streaming(monkeypatch) -> None:
    monkeypatch.setattr(
        oak_depthai_detection_probe,
        "_run",
        lambda cmd: {
            "stdout": "Bus 003 Device 004: ID 03e7:2485 Intel Movidius MyriadX\n",
            "stderr": "",
            "returncode": 0,
        },
    )
    monkeypatch.setattr(
        oak_depthai_detection_probe,
        "_depthai_devices",
        lambda: {
            "depthai_available": False,
            "available_devices": [],
            "error": "depthai module not installed",
        },
    )
    monkeypatch.setattr(
        oak_depthai_detection_probe,
        "_configured_vision_backend",
        lambda: {"backend": "picamera2", "fallback_backend": "opencv"},
    )
    monkeypatch.setattr(oak_depthai_detection_probe, "_repo_has_oak_adapter", lambda: False)

    report = oak_depthai_detection_probe.build_report()

    assert report["lsusb_matching_devices"] == [
        "Bus 003 Device 004: ID 03e7:2485 Intel Movidius MyriadX"
    ]
    assert report["depthai_available"] is False
    assert report["depthai_available_devices"] == []
    assert report["configured_vision_backend"]["backend"] == "picamera2"
    assert report["repo_has_oak_adapter"] is False
