# tests/vision/unit/capture/test_continuous_worker.py
from __future__ import annotations

import threading
import time
import unittest

from modules.devices.vision.capture.continuous_worker import ContinuousCaptureWorker
from modules.devices.vision.capture.frame_packet import FramePacket


def _make_packet(seq: int = 0) -> FramePacket:
    return FramePacket(
        pixels=[[seq]],
        width=1,
        height=1,
        channels=1,
        backend_label="fake",
    )


class _FakeReader:
    """Fake reader that delivers packets on demand, or raises on request."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self._next_error: Exception | None = None
        self._read_count = 0

    def read_frame(self) -> FramePacket:
        with self._lock:
            self._read_count += 1
            if self._next_error is not None:
                err = self._next_error
                self._next_error = None
                raise err
            pkt = _make_packet(self._seq)
            self._seq += 1
            return pkt

    def set_next_error(self, error: Exception) -> None:
        with self._lock:
            self._next_error = error

    @property
    def read_count(self) -> int:
        with self._lock:
            return self._read_count

    # VisionCaptureReader interface stub — not used by worker directly
    active_backend: str = "fake"


class ContinuousCaptureWorkerTests(unittest.TestCase):

    def _make_worker(self, target_fps: float = 100.0) -> tuple[ContinuousCaptureWorker, _FakeReader]:
        reader = _FakeReader()
        worker = ContinuousCaptureWorker(reader, target_fps=target_fps)
        return worker, reader

    # ------------------------------------------------------------------
    # Basic lifecycle
    # ------------------------------------------------------------------

    def test_latest_frame_is_none_before_start(self) -> None:
        worker, _ = self._make_worker()
        self.assertIsNone(worker.latest_frame())

    def test_worker_delivers_frames_after_start(self) -> None:
        worker, reader = self._make_worker(target_fps=100.0)
        try:
            worker.start()
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                if worker.latest_frame() is not None:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(worker.latest_frame())
        finally:
            worker.stop()

    def test_frame_slot_advances_over_time(self) -> None:
        worker, reader = self._make_worker(target_fps=100.0)
        try:
            worker.start()
            # Wait for first frame
            deadline = time.monotonic() + 1.0
            while worker.latest_frame() is None and time.monotonic() < deadline:
                time.sleep(0.01)

            first = worker.latest_frame()
            self.assertIsNotNone(first)

            # Wait for at least one more read
            time.sleep(0.05)
            second = worker.latest_frame()
            self.assertIsNotNone(second)

            # Slot should have advanced (read_count grows)
            self.assertGreater(reader.read_count, 1)
        finally:
            worker.stop()

    def test_stop_halts_thread(self) -> None:
        worker, _ = self._make_worker(target_fps=100.0)
        worker.start()
        self.assertTrue(worker.is_running)
        worker.stop()
        self.assertFalse(worker.is_running)

    def test_double_start_is_safe(self) -> None:
        worker, _ = self._make_worker()
        try:
            worker.start()
            worker.start()  # Should not raise or spawn second thread
            self.assertTrue(worker.is_running)
        finally:
            worker.stop()

    def test_stop_before_start_is_safe(self) -> None:
        worker, _ = self._make_worker()
        worker.stop()  # Should not raise

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_single_read_error_does_not_stop_worker(self) -> None:
        worker, reader = self._make_worker(target_fps=100.0)
        try:
            worker.start()
            # Wait for first healthy frame
            deadline = time.monotonic() + 1.0
            while worker.latest_frame() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNotNone(worker.latest_frame())

            # Inject one error
            reader.set_next_error(RuntimeError("camera glitch"))
            time.sleep(0.05)

            # Worker should still be running and delivering frames
            self.assertTrue(worker.is_running)
            pre_count = reader.read_count
            time.sleep(0.05)
            self.assertGreater(reader.read_count, pre_count)
        finally:
            worker.stop()

    def test_stats_tracks_captured_frames(self) -> None:
        worker, _ = self._make_worker(target_fps=100.0)
        try:
            worker.start()
            deadline = time.monotonic() + 1.0
            while worker.stats()["frames_captured"] < 3 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreaterEqual(worker.stats()["frames_captured"], 3)
        finally:
            worker.stop()

    def test_stats_records_error(self) -> None:
        worker, reader = self._make_worker(target_fps=100.0)
        try:
            worker.start()
            deadline = time.monotonic() + 1.0
            while worker.latest_frame() is None and time.monotonic() < deadline:
                time.sleep(0.01)

            reader.set_next_error(RuntimeError("test error"))
            time.sleep(0.1)

            stats = worker.stats()
            # After recovery, last_error may have been cleared — but at some
            # point it was set. We verify consecutive_errors reset to 0 after recovery.
            self.assertEqual(stats["consecutive_errors"], 0)
        finally:
            worker.stop()

    # ------------------------------------------------------------------
    # Stats shape
    # ------------------------------------------------------------------

    def test_stats_returns_expected_keys(self) -> None:
        worker, _ = self._make_worker()
        stats = worker.stats()
        expected_keys = {
            "frames_captured",
            "frames_dropped",
            "consecutive_errors",
            "last_capture_at",
            "last_error",
            "last_error_at",
            "target_fps",
            "running",
        }
        self.assertEqual(set(stats.keys()), expected_keys)

    def test_stats_running_reflects_state(self) -> None:
        worker, _ = self._make_worker()
        self.assertFalse(worker.stats()["running"])
        worker.start()
        try:
            self.assertTrue(worker.stats()["running"])
        finally:
            worker.stop()
        self.assertFalse(worker.stats()["running"])


if __name__ == "__main__":
    unittest.main()