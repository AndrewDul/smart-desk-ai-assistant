from __future__ import annotations

import unittest
from types import SimpleNamespace

from modules.runtime.audio_runtime_snapshot import AudioRuntimeSnapshotService


class _FakeVoiceSession:
    def snapshot(self):
        return SimpleNamespace(
            state="listening",
            detail="active_window:command",
            interaction_phase="command",
            input_owner="voice_input",
            active_window_open=True,
            active_window_remaining_seconds=2.75,
            active_window_generation=4,
            state_age_seconds=0.42,
        )


class _AssistantProbe:
    def __init__(self) -> None:
        self._last_capture_handoff = {
            "applied_owner": "voice_input",
            "wake_backend_label": "runtime.wake_gate",
        }
        self._last_resume_policy_snapshot = {
            "action": "grace",
            "reason": "response_delivered",
        }
        self._last_command_window_policy_snapshot = {
            "action": "retry",
            "reason": "empty_capture",
        }


class AudioRuntimeSnapshotServiceTests(unittest.TestCase):
    def test_snapshot_contains_voice_session_and_audio_policy_state(self) -> None:
        service = AudioRuntimeSnapshotService(voice_session=_FakeVoiceSession())
        assistant = _AssistantProbe()

        snapshot = service.snapshot(assistant=assistant)

        self.assertEqual(snapshot["state"], "listening")
        self.assertEqual(snapshot["interaction_phase"], "command")
        self.assertEqual(snapshot["input_owner"], "voice_input")
        self.assertTrue(snapshot["active_window_open"])
        self.assertAlmostEqual(snapshot["active_window_remaining_seconds"], 2.75)
        self.assertEqual(snapshot["active_window_generation"], 4)
        self.assertEqual(snapshot["last_capture_handoff"]["applied_owner"], "voice_input")
        self.assertEqual(snapshot["last_resume_policy"]["action"], "grace")
        self.assertEqual(snapshot["last_command_window_policy"]["action"], "retry")
        self.assertTrue(snapshot["lines"])
        self.assertIn("phase:command", snapshot["lines"][0])


if __name__ == "__main__":
    unittest.main()