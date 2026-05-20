from __future__ import annotations

import json
from types import SimpleNamespace

from modules.devices.vision.oak_depthai import device_probe
from tests.runtime.diagnostics import oak_depthai_detection_probe


class _FakeDeviceInfo:
    def __str__(self) -> str:
        return (
            "DeviceInfo(name=3.1.1, deviceId=19443010C1A0E47D00, "
            "X_LINK_UNBOOTED, X_LINK_USB_VSC, X_LINK_MYRIAD_X, X_LINK_SUCCESS)"
        )


def _settings_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "vision": {
                    "enabled": True,
                    "backend": "picamera2",
                    "fallback_backend": "opencv",
                    "camera_index": 0,
                    "object_detector_backend": "hailo_yolov11",
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _fake_lsusb(cmd):
    assert cmd == ["lsusb"]
    return {
        "stdout": "Bus 003 Device 004: ID 03e7:2485 Intel Movidius MyriadX\n",
        "stderr": "",
        "returncode": 0,
    }


def _fake_depthai_module():
    return SimpleNamespace(
        Device=SimpleNamespace(
            getAllAvailableDevices=lambda: [_FakeDeviceInfo()],
        )
    )


def test_oak_status_reports_depthai_available_when_module_exists(tmp_path) -> None:
    report = device_probe.build_vision_camera_status(
        settings_path=_settings_file(tmp_path),
        vision_root=tmp_path / "vision",
        run=_fake_lsusb,
        module_available=lambda name: name == "depthai",
        import_depthai=_fake_depthai_module,
    )

    oak = report["oak_d_lite"]

    assert oak["depthai_available"] is True
    assert oak["depthai_device_count"] == 1
    assert oak["mxid"] == "19443010C1A0E47D00"
    assert oak["state"] == "X_LINK_UNBOOTED"


def test_oak_status_reports_usb_detected_from_lsusb_output(tmp_path) -> None:
    report = device_probe.build_vision_camera_status(
        settings_path=_settings_file(tmp_path),
        vision_root=tmp_path / "vision",
        run=_fake_lsusb,
        module_available=lambda name: False,
    )

    oak = report["oak_d_lite"]

    assert oak["usb_detected"] is True
    assert oak["usb_matches"] == [
        "Bus 003 Device 004: ID 03e7:2485 Intel Movidius MyriadX"
    ]


def test_oak_status_does_not_claim_runtime_adapter_when_only_probe_exists(tmp_path) -> None:
    vision_root = tmp_path / "vision"
    (vision_root / "oak_depthai").mkdir(parents=True)
    (vision_root / "oak_depthai" / "device_probe.py").write_text(
        "import depthai\n",
        encoding="utf-8",
    )

    report = device_probe.build_vision_camera_status(
        settings_path=_settings_file(tmp_path),
        vision_root=vision_root,
        run=_fake_lsusb,
        module_available=lambda name: name == "depthai",
        import_depthai=_fake_depthai_module,
    )

    oak = report["oak_d_lite"]

    assert oak["repo_has_oak_adapter"] is False
    assert "Add a non-default OAK runtime adapter" in oak["recommended_next_step"]


def test_camera_module_and_oak_status_are_separate_entries(tmp_path) -> None:
    report = device_probe.build_vision_camera_status(
        settings_path=_settings_file(tmp_path),
        vision_root=tmp_path / "vision",
        run=_fake_lsusb,
        module_available=lambda name: name == "depthai",
        import_depthai=_fake_depthai_module,
    )

    entries = {entry["id"]: entry for entry in report["camera_sources"]}

    assert entries["camera_module_3_wide"]["backend"] == "picamera2"
    assert entries["camera_module_3_wide"]["active_runtime_backend"] is True
    assert entries["oak_d_lite_fixed_focus"]["backend"] == "depthai"
    assert entries["oak_d_lite_fixed_focus"]["active_streaming"] is False


def test_diagnostic_shape_reports_oak_without_streaming(monkeypatch, tmp_path) -> None:
    def _fake_status(settings_path, vision_root):
        del settings_path, vision_root
        oak = {
            "id": "oak_d_lite_fixed_focus",
            "label": "Luxonis OAK-D Lite Fixed Focus / DepthAI",
            "backend": "depthai",
            "usb_detected": True,
            "usb_matches": ["Bus 003 Device 004: ID 03e7:2485 Intel Movidius MyriadX"],
            "lsusb_returncode": 0,
            "lsusb_error": "",
            "depthai_available": True,
            "depthai_device_count": 1,
            "devices": [{"mxid": "19443010C1A0E47D00", "state": "X_LINK_UNBOOTED"}],
            "device_info": {"mxid": "19443010C1A0E47D00", "state": "X_LINK_UNBOOTED"},
            "mxid": "19443010C1A0E47D00",
            "state": "X_LINK_UNBOOTED",
            "repo_has_oak_adapter": False,
            "active_streaming": False,
            "recommended_next_step": "Add a non-default OAK runtime adapter after a separate RGB/depth smoke test.",
            "error": "",
        }
        camera = {
            "id": "camera_module_3_wide",
            "label": "Camera Module 3 Wide / picamera2",
            "backend": "picamera2",
            "active_streaming": True,
        }
        return {
            "camera_sources": [camera, oak],
            "configured_vision_backend": {"backend": "picamera2", "fallback_backend": "opencv"},
            "oak_d_lite": oak,
            "camera_module_3_wide": camera,
        }

    monkeypatch.setattr(oak_depthai_detection_probe, "build_vision_camera_status", _fake_status)

    report = oak_depthai_detection_probe.build_report()

    assert report["oak_d_lite"]["depthai_available"] is True
    assert report["oak_d_lite"]["depthai_device_count"] == 1
    assert report["oak_d_lite"]["active_streaming"] is False
    assert report["camera_sources"][0]["id"] == "camera_module_3_wide"
    assert report["camera_sources"][1]["id"] == "oak_d_lite_fixed_focus"
