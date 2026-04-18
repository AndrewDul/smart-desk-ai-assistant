from __future__ import annotations

import types
import unittest

from modules.core.session.voice_session import VoiceSessionController
from modules.runtime.main_loop.barge_in import try_handle_barge_in_during_output
from modules.runtime.main_loop.session_state import MainLoopRuntimeState
from tests.support.fakes import FakeAudioCoordinator, FakeVoiceOutput, FakeWakeBackend


class _BenchmarkProbe:
    def __init__(self) -> None:
        self.annotated: list[dict[str, object]] = []

    def note_wake_detected(self, *, source: str) -> None:
        self.last_source = source

    def annotate_last_completed_turn(
        self,
        *,
        interrupt_snapshot=None,
        resume_policy=None,
        command_window_policy=None,
    ) -> bool:
        del resume_policy, command_window_policy
        self.annotated.append(dict(interrupt_snapshot or {}))
        return True


class BargeInInterruptSnapshotTests(unittest.TestCase):
    def _build_assistant(self) -> object:
        voice_session = VoiceSessionController(active_listen_window_seconds=5.0)
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        voice_output.audio_coordinator = FakeAudioCoordinator(
            active_output=True,
            blocked=False,
            output_age_seconds=1.2,
        )
        wake_backend = FakeWakeBackend(result="nexa")
        benchmark = _BenchmarkProbe()

        self.request_calls: list[dict[str, object]] = []

        def request_interrupt(*, reason: str, source: str, metadata: dict[str, object]) -> None:
            self.request_calls.append(
                {
                    "reason": reason,
                    "source": source,
                    "metadata": dict(metadata),
                }
            )

        assistant = types.SimpleNamespace(
            settings={
                "voice_input": {
                    "wake_barge_in_enabled": True,
                    "wake_barge_in_timeout_seconds": 0.18,
                    "wake_barge_in_min_output_age_seconds": 0.35,
                    "wake_barge_in_resume_timeout_seconds": 0.3,
                    "wake_barge_in_refractory_seconds": 0.4,
                },
                "audio_coordination": {
                    "listen_resume_poll_seconds": 0.01,
                },
            },
            voice_session=voice_session,
            voice_out=voice_output,
            wake_gate=wake_backend,
            voice_in=object(),
            audio_coordinator=voice_output.audio_coordinator,
            pending_confirmation=None,
            pending_follow_up=None,
            turn_benchmark_service=benchmark,
            request_interrupt=request_interrupt,
            _last_interrupt_snapshot={},
        )
        return assistant

    def test_barge_in_stores_structured_interrupt_snapshot(self) -> None:
        assistant = self._build_assistant()
        state_flags = MainLoopRuntimeState()

        accepted = try_handle_barge_in_during_output(assistant, state_flags)

        self.assertTrue(accepted)
        snapshot = assistant._last_interrupt_snapshot
        self.assertEqual(snapshot["reason"], "wake_barge_in")
        self.assertEqual(snapshot["source"], "wake_gate")
        self.assertEqual(snapshot["kind"], "barge_in")
        self.assertEqual(snapshot["metadata"]["backend"], "runtime.wake_gate")
        self.assertTrue(snapshot["metadata"]["reopened_command_window"])
        self.assertEqual(assistant.turn_benchmark_service.annotated[-1]["kind"], "barge_in")


if __name__ == "__main__":
    unittest.main()