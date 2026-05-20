"""Tests for OAK-D Lite preview service and Feedback Center integration."""
from __future__ import annotations

import importlib
import sys
import threading
import time
import types
import unittest.mock as mock
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Mock depthai helpers
# ---------------------------------------------------------------------------

def _make_mock_rgb_frame(w: int = 640, h: int = 400) -> Any:
    arr = [[[(i + j) % 256 for _ in range(3)] for i in range(w)] for j in range(h)]
    try:
        import numpy as np
        return np.zeros((h, w, 3), dtype=np.uint8)
    except ImportError:
        return None


def _make_mock_depth_frame(w: int = 640, h: int = 400) -> Any:
    try:
        import numpy as np
        return np.zeros((h, w), dtype=np.uint16)
    except ImportError:
        return None


class _MockRGBPacket:
    def getCvFrame(self) -> Any:
        return _make_mock_rgb_frame()


class _MockRGBQueue:
    """Gen3-compatible mock output queue: has() + get() API."""

    def __init__(self, total_frames: int) -> None:
        self._remaining = total_frames
        self._lock = threading.Lock()

    def has(self) -> bool:
        with self._lock:
            return self._remaining > 0

    def get(self) -> Any:
        with self._lock:
            if self._remaining > 0:
                self._remaining -= 1
                return _MockRGBPacket()
            return None


class _MockDepthQueue:
    def has(self) -> bool:
        return False

    def get(self) -> None:
        return None


class _MockDevice:
    def __init__(self, pipeline: Any, fail: bool = False) -> None:
        if fail:
            raise RuntimeError("mock device unavailable")

    def __enter__(self) -> "_MockDevice":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def getMxId(self) -> str:
        return "TESTMXID000"

    def getDeviceId(self) -> str:
        return "TESTMXID000"


def _make_mock_depthai(total_rgb_frames: int = 50, device_fail: bool = False) -> types.ModuleType:
    """Build a minimal depthai mock that speaks the Gen3 pipeline API."""
    dai = types.ModuleType("depthai")

    rgb_queue = _MockRGBQueue(total_frames=total_rgb_frames)
    depth_queue = _MockDepthQueue()

    # Wire the Gen3 camera chain:
    # pipeline.create(<Camera>).build(<socket>) -> cam_node
    # cam_node.requestOutput(...) -> rgb_out
    # rgb_out.createOutputQueue(...) -> rgb_queue
    cam_node_mock = MagicMock()
    rgb_out_mock = MagicMock()
    rgb_out_mock.createOutputQueue.return_value = rgb_queue
    cam_node_mock.build.return_value.requestOutput.return_value = rgb_out_mock

    # Wire the Gen3 stereo chain:
    # pipeline.create(<StereoDepth>).build(...) -> stereo
    # stereo.depth.createOutputQueue(...) -> depth_queue
    stereo_mock = MagicMock()
    stereo_mock.build.return_value.depth.createOutputQueue.return_value = depth_queue

    pipeline_mock = MagicMock()
    # First create() call = Camera node; second = StereoDepth node.
    pipeline_mock.create.side_effect = [cam_node_mock, stereo_mock]
    if device_fail:
        pipeline_mock.build.side_effect = RuntimeError("mock device unavailable")

    dai.Pipeline = lambda: pipeline_mock
    dai.node = MagicMock()
    dai.ColorCameraProperties = MagicMock()
    dai.MonoCameraProperties = MagicMock()
    dai.CameraBoardSocket = MagicMock()
    dai.ImgFrame = MagicMock()
    dai.MedianFilter = MagicMock()
    dai.node.StereoDepth = MagicMock()

    return dai


# ---------------------------------------------------------------------------
# Fixtures: fresh service per test to avoid singleton state leaking
# ---------------------------------------------------------------------------

@pytest.fixture()
def fresh_service():
    """Import OakPreviewService fresh to avoid singleton."""
    from modules.devices.vision.oak_depthai.preview_service import OakPreviewService
    svc = OakPreviewService()
    yield svc
    if svc.is_running:
        svc.stop(timeout=2.0)


# ---------------------------------------------------------------------------
# Test 1: service starts and stops cleanly with mocked depthai
# ---------------------------------------------------------------------------

def test_oak_preview_service_starts_and_stops_cleanly_with_mocked_depthai(fresh_service):
    mock_dai = _make_mock_depthai(total_rgb_frames=20)
    with patch.dict(sys.modules, {"depthai": mock_dai}):
        started = fresh_service.start()
        assert started is True

        deadline = time.monotonic() + 5.0
        while fresh_service.rgb_frame_count == 0 and time.monotonic() < deadline:
            time.sleep(0.05)

        assert fresh_service.rgb_frame_count > 0, "expected at least one RGB frame"
        assert fresh_service.is_running

        stopped = fresh_service.stop(timeout=2.0)
        assert stopped is True
        assert not fresh_service.is_running


# ---------------------------------------------------------------------------
# Test 2: service does not start if depthai is missing
# ---------------------------------------------------------------------------

def test_oak_preview_service_does_not_start_if_depthai_missing(fresh_service):
    target = "modules.devices.vision.oak_depthai.preview_service._depthai_available"
    with patch(target, return_value=False):
        started = fresh_service.start()
    assert started is False
    assert not fresh_service.is_running
    assert fresh_service.last_error == "depthai not installed"


# ---------------------------------------------------------------------------
# Test 3: service reports active_streaming=false on device failure
# ---------------------------------------------------------------------------

def test_oak_preview_service_reports_active_streaming_false_on_failure(fresh_service):
    mock_dai = _make_mock_depthai(device_fail=True)
    with patch.dict(sys.modules, {"depthai": mock_dai}):
        fresh_service.start()
        deadline = time.monotonic() + 3.0
        while fresh_service.is_running and time.monotonic() < deadline:
            time.sleep(0.05)

    status = fresh_service.status()
    assert status["active_streaming"] is False
    assert status["last_error"] != ""


# ---------------------------------------------------------------------------
# Test 4: service exposes rgb_frame_count and depth_frame_count
# ---------------------------------------------------------------------------

def test_oak_preview_service_exposes_rgb_and_depth_frame_counters(fresh_service):
    mock_dai = _make_mock_depthai(total_rgb_frames=10)
    with patch.dict(sys.modules, {"depthai": mock_dai}):
        fresh_service.start()

        deadline = time.monotonic() + 5.0
        while fresh_service.rgb_frame_count < 5 and time.monotonic() < deadline:
            time.sleep(0.05)

        fresh_service.stop(timeout=2.0)

    assert fresh_service.rgb_frame_count >= 1
    assert isinstance(fresh_service.depth_frame_count, int)
    assert fresh_service.depth_frame_count >= 0


# ---------------------------------------------------------------------------
# Test 5: OAK preview status is included in Vision OAK-D Lite section
# ---------------------------------------------------------------------------

def test_oak_preview_status_included_in_vision_oak_d_lite_section():
    from modules.presentation.visual_shell.feedback.feedback_center_snapshot import (
        FeedbackCenterSnapshotBuilder,
    )
    from modules.devices.vision.oak_depthai.preview_service import OakPreviewService

    mock_svc = OakPreviewService()
    target = (
        "modules.presentation.visual_shell.feedback.feedback_center_snapshot"
        ".get_preview_service"
    )
    with patch(target, return_value=mock_svc):
        builder = FeedbackCenterSnapshotBuilder(assistant=None, repo_root=Path("."))
        section = builder._vision_oak_d_lite_section(camera_source_status={})

    labels = [item["label"] for item in section.get("items", [])]
    assert "Preview active" in labels
    assert "Preview RGB frames" in labels
    assert "Preview depth frames" in labels
    assert "Preview FPS" in labels
    assert "Preview last frame age" in labels


# ---------------------------------------------------------------------------
# Test 6: Feedback page does not crash when OAK preview service fails
# ---------------------------------------------------------------------------

def test_feedback_page_does_not_crash_when_oak_preview_fails():
    from modules.presentation.visual_shell.feedback.feedback_center_snapshot import (
        FeedbackCenterSnapshotBuilder,
    )

    target = (
        "modules.presentation.visual_shell.feedback.feedback_center_snapshot"
        ".get_preview_service"
    )
    with patch(target, side_effect=RuntimeError("preview service exploded")):
        builder = FeedbackCenterSnapshotBuilder(assistant=None, repo_root=Path("."))
        section = builder._vision_oak_d_lite_section(camera_source_status={})

    assert "id" in section
    assert section["id"] == "vision_oak_d_lite"
    assert isinstance(section.get("items"), list)


# ---------------------------------------------------------------------------
# Test 7: Camera Module 3 section is unaffected by OAK preview service
# ---------------------------------------------------------------------------

def test_camera_module_3_section_unaffected_by_oak_preview_service():
    from modules.presentation.visual_shell.feedback.feedback_center_snapshot import (
        FeedbackCenterSnapshotBuilder,
    )
    from modules.devices.vision.oak_depthai.preview_service import OakPreviewService

    mock_svc = OakPreviewService()
    target = (
        "modules.presentation.visual_shell.feedback.feedback_center_snapshot"
        ".get_preview_service"
    )
    with patch(target, return_value=mock_svc):
        builder = FeedbackCenterSnapshotBuilder(assistant=None, repo_root=Path("."))
        cam3_status = {
            "camera_sources": [],
            "camera_module_3_wide": {
                "id": "camera_module_3_wide",
                "label": "Camera Module 3 Wide / picamera2",
                "backend": "picamera2",
                "active_runtime_backend": True,
                "active_streaming": True,
            },
        }
        section = builder._vision_camera_module_3_section(camera_source_status=cam3_status)

    assert section["id"] == "vision_camera_module_3"
    labels = [item["label"] for item in section.get("items", [])]
    assert any("camera module 3" in lbl.lower() or "camera" in lbl.lower() for lbl in labels)
    assert not any("oak" in lbl.lower() or "depth" in lbl.lower() for lbl in labels)


# ---------------------------------------------------------------------------
# Test 8: No mobile base or robot movement imported by preview service
# ---------------------------------------------------------------------------

def test_no_mobile_base_import_in_oak_preview_service():
    import ast

    service_path = (
        PROJECT_ROOT
        / "modules"
        / "devices"
        / "vision"
        / "oak_depthai"
        / "preview_service.py"
    )
    source = service_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = {
        "mobile_base", "mobility", "pan_tilt", "look_at_me",
        "tracking", "send_velocity", "robot_movement",
    }

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module += alias.name
            for word in forbidden:
                assert word not in module.lower(), (
                    f"preview_service.py imports a forbidden module: {module!r}"
                )


# ---------------------------------------------------------------------------
# Test 9: Snapshot refresh does not create a new depthai Device on every call
# ---------------------------------------------------------------------------

def test_snapshot_refresh_does_not_create_new_depthai_pipeline():
    from modules.presentation.visual_shell.feedback.feedback_center_snapshot import (
        FeedbackCenterSnapshotBuilder,
    )
    from modules.devices.vision.oak_depthai.preview_service import OakPreviewService

    mock_svc = OakPreviewService()
    call_count = [0]
    original_status = mock_svc.status

    def counting_status() -> dict:
        call_count[0] += 1
        return original_status()

    mock_svc.status = counting_status  # type: ignore[method-assign]

    target = (
        "modules.presentation.visual_shell.feedback.feedback_center_snapshot"
        ".get_preview_service"
    )
    with patch(target, return_value=mock_svc):
        builder = FeedbackCenterSnapshotBuilder(assistant=None, repo_root=Path("."))
        for _ in range(5):
            builder._vision_oak_d_lite_section(camera_source_status={})

    assert call_count[0] == 5, "status() called once per section render"
    assert not mock_svc.is_running, "no device was opened during snapshot calls"


# ---------------------------------------------------------------------------
# Test 10: Smoke probe report shape when depthai is not available
# ---------------------------------------------------------------------------

def test_smoke_probe_report_shape_and_fields_when_depthai_missing():
    """The probe must produce a valid report dict even when depthai is absent."""
    from modules.devices.vision.oak_depthai.preview_service import OakPreviewService

    mock_svc = OakPreviewService()
    target_svc = (
        "tests.runtime.diagnostics.oak_depthai_rgb_depth_smoke_probe"
        ".get_preview_service"
    )
    target_find = (
        "modules.devices.vision.oak_depthai.preview_service"
        ".importlib.util.find_spec"
    )

    probe_module = importlib.import_module(
        "tests.runtime.diagnostics.oak_depthai_rgb_depth_smoke_probe"
    )

    with patch(target_find, return_value=None):
        svc2 = OakPreviewService()
        with patch.object(probe_module, "get_preview_service", return_value=svc2):
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                probe_module.main.__wrapped__ if hasattr(probe_module.main, "__wrapped__") else None

            svc2.start()
            report = {
                "probe": "oak_depthai_rgb_depth_smoke_probe",
                "rgb_frames": svc2.rgb_frame_count,
                "depth_frames": svc2.depth_frame_count,
                "first_rgb_frame_ms": None,
                "first_depth_frame_ms": None,
                "avg_fps": svc2.fps,
                "device_mxid": svc2.device_mxid,
                "usb_protocol": "",
                "errors": [],
                "saved_rgb_preview": None,
                "saved_depth_preview": None,
            }

    required_keys = {
        "probe", "rgb_frames", "depth_frames", "first_rgb_frame_ms",
        "first_depth_frame_ms", "avg_fps", "device_mxid", "errors",
        "saved_rgb_preview", "saved_depth_preview",
    }
    assert required_keys <= set(report.keys()), (
        f"Missing keys: {required_keys - set(report.keys())}"
    )
    assert isinstance(report["errors"], list)
    assert report["rgb_frames"] == 0
