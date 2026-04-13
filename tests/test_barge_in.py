from __future__ import annotations

import types
import unittest

from modules.core.session.voice_session import VoiceSessionController
from modules.runtime.main_loop.barge_in import try_handle_barge_in_during_output, wake_barge_in_status
from modules.runtime.main_loop.session_state import MainLoopRuntimeState
from tests.support.fakes import (
    FakeAudioCoordinator,
    FakeBenchmarkRecorder,
    FakeVoiceOutput,
    FakeWakeBackend,
)


class BargeInTests(unittest.TestCase):
    def _build_assistant(self) -> object:
        voice_session = VoiceSessionController(active_listen_window_seconds=5.0)
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        voice_output.audio_coordinator = FakeAudioCoordinator(
            active_output=True,
            blocked=False,
            output_age_seconds=1.2,
        )
        wake_backend = FakeWakeBackend(result="nexa")
        benchmark = FakeBenchmarkRecorder()
        interrupt_calls: list[dict[str, object]] = []

        def request_interrupt(*, reason: str, source: str, metadata: dict[str, object]) -> None:
            interrupt_calls.append(
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
        )
        assistant._interrupt_calls = interrupt_calls
        return assistant

    def test_status_reports_dedicated_wake_backend(self) -> None:
        assistant = self._build_assistant()

        enabled, detail = wake_barge_in_status(assistant)

        self.assertTrue(enabled)
        self.assertEqual(detail, "runtime.wake_gate")

    def test_barge_in_interrupts_output_and_reopens_command_window(self) -> None:
        assistant = self._build_assistant()
        state_flags = MainLoopRuntimeState()

        accepted = try_handle_barge_in_during_output(assistant, state_flags)

        self.assertTrue(accepted)
        self.assertEqual(len(assistant._interrupt_calls), 1)
        self.assertEqual(assistant._interrupt_calls[0]["reason"], "wake_barge_in")
        self.assertEqual(assistant.voice_out.stop_calls, 1)
        self.assertTrue(assistant.voice_session.active_window_open())
        self.assertEqual(assistant.voice_session.state, "listening")
        self.assertEqual(assistant.turn_benchmark_service.wake_sources, ["barge_in:runtime.wake_gate"])


if __name__ == "__main__":
    unittest.main()