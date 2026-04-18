from __future__ import annotations

import unittest
from types import SimpleNamespace

from modules.runtime.audio_runtime_snapshot import AudioRuntimeSnapshotService


class _FakeVoiceSession:
    def snapshot(self):
        return SimpleNamespace(
            state="listening",
            detail="awaiting_command_after_barge_in",
            interaction_phase="command",
            input_owner="voice_input",
            active_window_open=True,
            active_window_remaining_seconds=2.0,
            active_window_generation=3,
            state_age_seconds=0.2,
        )


class _AssistantProbe:
    def __init__(self) -> None:
        self._last_capture_handoff = {}
        self._last_resume_policy_snapshot = {}
        self._last_command_window_policy_snapshot = {}
        self._last_session_continuity_snapshot = {
            "action": "command_window_open",
            "phase": "command",
        }
        self._last_interrupt_snapshot = {
            "requested": True,
            "generation": 2,
            "reason": "wake_barge_in",
            "source": "wake_gate",
            "kind": "barge_in",
            "metadata": {"backend": "runtime.wake_gate"},
        }


class AudioRuntimeInterruptSnapshotTests(unittest.TestCase):
    def test_snapshot_contains_last_interrupt_context(self) -> None:
        service = AudioRuntimeSnapshotService(voice_session=_FakeVoiceSession())
        snapshot = service.snapshot(assistant=_AssistantProbe())

        self.assertEqual(snapshot["last_interrupt"]["kind"], "barge_in")
        self.assertEqual(snapshot["last_interrupt"]["source"], "wake_gate")
        self.assertIn("intr:barge_in", snapshot["lines"][3])


if __name__ == "__main__":
    unittest.main()