from __future__ import annotations

import threading
import time
import types
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

from modules.presentation.visual_shell.feedback.feedback_lane import FeedbackLane


class FakeCameraService:
    """Minimal camera stub that does not expose _worker — prevents cv2 import in streamer."""

    def __init__(self) -> None:
        self.started = False
        self.start_called = threading.Event()

    def start(self) -> None:
        self.started = True
        self.start_called.set()

    def status(self) -> dict:
        return {"ok": False, "enabled": True}


class SlowCameraService:
    """Camera stub whose start() method sleeps to simulate libcamera initialisation."""

    def __init__(self, delay: float = 0.2) -> None:
        self._delay = delay
        self.start_called = threading.Event()
        self.start_blocking = threading.Event()
        self.start_count = 0

    def start(self) -> None:
        self.start_count += 1
        self.start_blocking.set()
        time.sleep(self._delay)
        self.start_called.set()

    def status(self) -> dict:
        return {"ok": False, "enabled": True}


@dataclass(slots=True)
class FakeVisualShellLane:
    _ctrl: Any = field(default_factory=MagicMock)

    def _controller(self) -> Any:
        return self._ctrl


def _make_lane(*, cam: Any = None, camera_delay_s: float = 0.05) -> FeedbackLane:
    controller = MagicMock()
    controller.show_feedback.return_value = None
    controller.hide_feedback.return_value = None
    controller.feedback_status_update.return_value = None

    visual_shell_lane = FakeVisualShellLane(_ctrl=controller)

    assistant = types.SimpleNamespace(
        vision=cam,
        camera_service=None,
        vision_service=None,
        runtime=None,
        backend_statuses={},
        speech_recognition=None,
        voice_out=None,
        wake_gate=None,
        settings={},
    )

    lane = FeedbackLane(visual_shell_lane=visual_shell_lane, assistant=assistant)
    # Use a short delay for tests so we don't wait 750 ms
    lane._CAMERA_START_DELAY_S = camera_delay_s
    return lane


# ---------------------------------------------------------------------------
# turn_on() must NOT schedule camera — camera is post-response only
# ---------------------------------------------------------------------------

def test_turn_on_does_not_schedule_camera() -> None:
    """turn_on() must not call camera.start() at all.

    Camera scheduling moved to schedule_post_response_camera_start() so that
    libcamera stdout never appears before the DIAGNOSTICS box.
    """
    cam = FakeCameraService()
    lane = _make_lane(cam=cam, camera_delay_s=0.05)

    with patch.object(lane, "_publish_status_snapshot"):
        lane.turn_on()

    # Even waiting well past the old 750ms delay — camera must not start
    called = cam.start_called.wait(timeout=0.3)
    assert not called, (
        "camera.start() was called from turn_on() — must only be called via "
        "schedule_post_response_camera_start()"
    )
    lane.turn_off()


def test_feedback_on_does_not_call_camera_start_synchronously() -> None:
    """turn_on() must return before any camera.start() path could complete.

    Even if camera scheduling were still in turn_on(), the call must be async.
    With the post-response architecture this passes trivially.
    """
    delay = 0.15
    cam = SlowCameraService(delay=0.05)
    lane = _make_lane(cam=cam, camera_delay_s=delay)

    with patch.object(lane, "_publish_status_snapshot"):
        t0 = time.monotonic()
        result = lane.turn_on()
        elapsed = time.monotonic() - t0

    assert result is True
    assert elapsed < delay * 0.8, (
        f"turn_on() blocked for {elapsed:.3f}s — exceeds {delay * 0.8:.3f}s threshold"
    )
    assert not cam.start_called.is_set(), (
        "camera.start() was already called synchronously in turn_on()"
    )
    lane.turn_off()


# ---------------------------------------------------------------------------
# schedule_post_response_camera_start() — the new external trigger
# ---------------------------------------------------------------------------

def test_schedule_post_response_calls_camera_start() -> None:
    """schedule_post_response_camera_start() must trigger camera.start() after delay."""
    cam = FakeCameraService()
    lane = _make_lane(cam=cam, camera_delay_s=0.05)

    with patch.object(lane, "_publish_status_snapshot"):
        lane.turn_on()

    # Camera must NOT be started yet (no scheduling from turn_on)
    assert not cam.start_called.is_set()

    # Now simulate post-response hook
    lane.schedule_post_response_camera_start(delay_seconds=0.05)

    called = cam.start_called.wait(timeout=1.0)
    assert called, "camera.start() was never called by schedule_post_response_camera_start()"

    lane.turn_off()


def test_post_response_camera_start_skipped_if_feedback_inactive() -> None:
    """If turn_off() is called before the delay elapses, camera.start() must NOT run."""
    cam = FakeCameraService()
    lane = _make_lane(cam=cam, camera_delay_s=0.20)

    with patch.object(lane, "_publish_status_snapshot"):
        lane.turn_on()

    lane.schedule_post_response_camera_start(delay_seconds=0.20)
    lane.turn_off()

    called = cam.start_called.wait(timeout=0.40)
    assert not called, (
        "camera.start() was called even though feedback was turned off before the delay"
    )


def test_post_response_camera_start_not_called_without_camera() -> None:
    """schedule_post_response_camera_start() is a no-op when no camera is present."""
    lane = _make_lane(cam=None, camera_delay_s=0.05)

    with patch.object(lane, "_publish_status_snapshot"):
        lane.turn_on()

    # Must not raise; no thread should be spawned
    lane.schedule_post_response_camera_start(delay_seconds=0.05)
    time.sleep(0.15)

    lane.turn_off()


def test_repeated_post_response_schedule_does_not_double_start() -> None:
    """Calling schedule_post_response_camera_start() twice must not spawn two threads."""
    cam = SlowCameraService(delay=0.05)
    lane = _make_lane(cam=cam, camera_delay_s=0.05)

    with patch.object(lane, "_publish_status_snapshot"):
        lane.turn_on()

    lane.schedule_post_response_camera_start(delay_seconds=0.05)
    lane.schedule_post_response_camera_start(delay_seconds=0.05)  # duplicate — must be idempotent

    cam.start_called.wait(timeout=1.0)
    time.sleep(0.15)

    assert cam.start_count <= 1, (
        f"camera.start() was called {cam.start_count} times — expected at most 1"
    )
    lane.turn_off()


# ---------------------------------------------------------------------------
# Regression: existing behavior must not regress
# ---------------------------------------------------------------------------

def test_feedback_on_does_not_call_publish_snapshot_synchronously() -> None:
    """_publish_status_snapshot() must NOT be called during turn_on() itself.

    Patch _status_loop to a no-op so the daemon thread never calls
    _publish_status_snapshot — that removes the scheduling race and leaves
    only the synchronous path under test.
    """
    cam = FakeCameraService()
    lane = _make_lane(cam=cam)

    with patch.object(lane, "_status_loop"), \
         patch.object(lane, "_publish_status_snapshot") as mock_snap:
        lane.turn_on()
        mock_snap.assert_not_called()

    lane.turn_off()


def test_feedback_on_does_not_build_feedback_center_snapshot_synchronously() -> None:
    """turn_on() must not build the heavy structured snapshot inline."""
    lane = _make_lane(cam=None)

    with patch.object(lane, "_status_loop"), \
         patch("modules.presentation.visual_shell.feedback.feedback_lane.build_feedback_center_snapshot") as mock_build:
        lane.turn_on()
        mock_build.assert_not_called()

    lane.turn_off()


def test_status_loop_can_publish_full_snapshot_after_open_delay() -> None:
    """The full diagnostics payload remains available through the status path."""
    lane = _make_lane(cam=None)
    lane._FIRST_STATUS_SNAPSHOT_DELAY_S = 0.01
    controller = lane._controller()

    with patch("modules.presentation.visual_shell.feedback.feedback_lane.build_feedback_center_snapshot") as mock_build:
        mock_build.return_value = {
            "sections": [
                {
                    "id": "performance",
                    "title": "Performance / Timings",
                    "items": [
                        {
                            "label": "Timing data",
                            "value": "not measured yet",
                            "hint": "loaded after shell open",
                            "severity": "unknown",
                        }
                    ],
                }
            ]
        }
        lane.turn_on()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not controller.feedback_status_update.called:
            time.sleep(0.01)

    assert controller.feedback_status_update.called
    _, kwargs = controller.feedback_status_update.call_args
    assert kwargs["sections"][0]["id"] == "performance"
    lane.turn_off()


def test_performance_snapshot_builder_does_not_block_basic_shell_open() -> None:
    """A slow performance/snapshot source must not delay turn_on()."""
    lane = _make_lane(cam=None)

    def slow_snapshot(*args, **kwargs):
        del args, kwargs
        time.sleep(0.25)
        return {"sections": []}

    with patch.object(lane, "_status_loop"), \
         patch("modules.presentation.visual_shell.feedback.feedback_lane.build_feedback_center_snapshot", side_effect=slow_snapshot):
        started = time.monotonic()
        result = lane.turn_on()
        elapsed = time.monotonic() - started

    assert result is True
    assert elapsed < 0.1
    lane.turn_off()


def test_feedback_on_returns_true_with_camera_present() -> None:
    """turn_on() must return True and create a streamer when camera is present."""
    cam = FakeCameraService()
    lane = _make_lane(cam=cam)

    with patch.object(lane, "_publish_status_snapshot"):
        result = lane.turn_on()

    assert result is True
    assert lane._streamer is not None

    lane.turn_off()


def test_feedback_on_returns_true_without_camera() -> None:
    """turn_on() must return True even when no camera backend is found."""
    lane = _make_lane(cam=None)

    with patch.object(lane, "_publish_status_snapshot"):
        result = lane.turn_on()

    assert result is True
    assert lane._streamer is None

    lane.turn_off()


def test_repeated_feedback_on_refreshes_shell_without_new_status_loop() -> None:
    lane = _make_lane(cam=None)

    with patch.object(lane, "_publish_status_snapshot"):
        assert lane.turn_on() is True
        first_thread = lane._status_thread
        assert lane.turn_on() is True

    assert lane._status_thread is first_thread
    lane.turn_off()


def test_feedback_on_is_fast_without_camera() -> None:
    """Without camera, turn_on() must complete in well under 100 ms."""
    lane = _make_lane(cam=None)

    with patch.object(lane, "_publish_status_snapshot"):
        t0 = time.monotonic()
        lane.turn_on()
        elapsed = time.monotonic() - t0

    assert elapsed < 0.1, f"turn_on() took {elapsed:.3f}s — expected < 100 ms"
    lane.turn_off()
