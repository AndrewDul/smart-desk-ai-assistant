from __future__ import annotations

import threading
import time
import unittest

from modules.core.presence import PresenceHeartbeatManager


class _PresenceVoice:
    def __init__(self, *, speak_seconds: float = 0.0) -> None:
        self.speak_seconds = float(speak_seconds)
        self.calls: list[tuple[str, str | None]] = []
        self.stop_calls = 0
        self.presence_stop_calls = 0
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def speak_presence(self, text: str, language: str | None = None) -> bool:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append((str(text), language))
        try:
            time.sleep(self.speak_seconds)
            return True
        finally:
            with self.lock:
                self.active -= 1

    def stop_playback(self) -> None:
        self.stop_calls += 1

    def stop_presence_playback(self) -> None:
        self.presence_stop_calls += 1


class PresenceHeartbeatTests(unittest.TestCase):
    def test_heartbeat_starts_after_configured_delay(self) -> None:
        voice = _PresenceVoice()
        heartbeat = PresenceHeartbeatManager(
            voice_output=voice,
            first_delay_s=0.02,
            repeat_interval_s=1.0,
        )

        heartbeat.start()
        time.sleep(0.01)
        self.assertEqual(heartbeat.heartbeat_count, 0)

        time.sleep(0.04)
        heartbeat.cancel()

        self.assertEqual(heartbeat.heartbeat_count, 1)
        self.assertGreaterEqual(heartbeat.first_heartbeat_ms, 15.0)

    def test_heartbeat_repeats_while_operation_is_running(self) -> None:
        voice = _PresenceVoice()
        heartbeat = PresenceHeartbeatManager(
            voice_output=voice,
            first_delay_s=0.01,
            repeat_interval_s=0.02,
            max_heartbeats=4,
        )

        heartbeat.start()
        time.sleep(0.09)
        heartbeat.cancel()

        self.assertGreaterEqual(heartbeat.heartbeat_count, 3)

    def test_heartbeat_cancels_before_first_phrase(self) -> None:
        voice = _PresenceVoice()
        heartbeat = PresenceHeartbeatManager(
            voice_output=voice,
            first_delay_s=0.05,
            repeat_interval_s=0.02,
        )

        heartbeat.start()
        heartbeat.cancel()
        time.sleep(0.07)

        self.assertEqual(heartbeat.heartbeat_count, 0)
        self.assertTrue(heartbeat.metrics().cancelled)

    def test_heartbeat_does_not_block_real_worker(self) -> None:
        voice = _PresenceVoice(speak_seconds=0.08)
        heartbeat = PresenceHeartbeatManager(
            voice_output=voice,
            first_delay_s=0.01,
            repeat_interval_s=0.2,
        )
        worker_done = threading.Event()

        heartbeat.start()
        time.sleep(0.02)

        def _real_work() -> None:
            time.sleep(0.01)
            worker_done.set()

        worker = threading.Thread(target=_real_work)
        worker.start()
        self.assertTrue(worker_done.wait(0.04))
        heartbeat.cancel()
        worker.join(timeout=0.1)

    def test_heartbeat_does_not_overlap_or_enqueue_stale_fillers(self) -> None:
        voice = _PresenceVoice(speak_seconds=0.05)
        heartbeat = PresenceHeartbeatManager(
            voice_output=voice,
            first_delay_s=0.01,
            repeat_interval_s=0.01,
            max_heartbeats=3,
        )

        heartbeat.start()
        time.sleep(0.13)
        heartbeat.cancel()

        self.assertLessEqual(voice.max_active, 1)
        self.assertLessEqual(heartbeat.heartbeat_count, 3)

    def test_cancel_real_audio_started_uses_presence_stop_path(self) -> None:
        voice = _PresenceVoice(speak_seconds=0.05)
        heartbeat = PresenceHeartbeatManager(
            voice_output=voice,
            first_delay_s=0.01,
            repeat_interval_s=0.2,
        )

        heartbeat.start()
        time.sleep(0.02)
        heartbeat.cancel(reason="real_audio_started")

        self.assertEqual(voice.presence_stop_calls, 1)
        self.assertEqual(voice.stop_calls, 0)
        self.assertEqual(heartbeat.metrics().cancelled_reason, "real_audio_started")


if __name__ == "__main__":
    unittest.main()
