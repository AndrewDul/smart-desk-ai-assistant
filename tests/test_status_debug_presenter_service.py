from __future__ import annotations

import unittest

from modules.presentation.status_debug_presenter.service import StatusDebugPresenterService


class StatusDebugPresenterServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = StatusDebugPresenterService()

    def test_build_status_presentation_includes_runtime_benchmark_and_feature_summary(self) -> None:
        presentation = self.service.build_status_presentation(
            language="en",
            runtime_status_spoken="Premium mode is ready. Wake uses oww, STT uses faster, and LLM uses hailo.",
            runtime_status_lines=["premium: YES", "core: YES", "wake: oww"],
            benchmark_spoken=(
                "The latest full turn took 910 milliseconds. "
                "Average voice start is 145 milliseconds, "
                "and average LLM first chunk is 82 milliseconds."
            ),
            runtime_metadata={
                "completed_turn_lines": [
                    "trace: conversation",
                    "result: conversation_route",
                ]
            },
            focus_on=True,
            break_on=False,
            current_timer="focus",
            memory_count=1,
            reminder_count=2,
            timer_running=True,
        )

        self.assertIn("Premium mode is ready", presentation.spoken_text)
        self.assertIn("latest full turn took 910 milliseconds", presentation.spoken_text)
        self.assertIn("Focus is on", presentation.spoken_text)
        self.assertEqual(
            presentation.display_lines,
            [
                "premium: YES",
                "core: YES",
                "trace: conversation",
                "focus: ON",
                "break: OFF",
                "timer: focus",
            ],
        )

    def test_build_debug_status_presentation_prefers_overlay_lines(self) -> None:
        presentation = self.service.build_debug_status_presentation(
            language="en",
            runtime_status_spoken="Premium mode is ready. Wake uses oww, STT uses faster, and LLM uses hailo.",
            benchmark_spoken=(
                "The latest full turn took 910 milliseconds. "
                "Average voice start is 145 milliseconds, "
                "and average LLM first chunk is 82 milliseconds."
            ),
            runtime_metadata={
                "runtime_debug_snapshot": {
                    "developer_overlay_lines": [
                        "rt:premium llm:ready",
                        "turn:910ms audio:145ms",
                    ]
                },
                "benchmark_snapshot": {
                    "latest_sample": {
                        "result": "conversation_route",
                    }
                },
                "completed_turn_trace": {
                    "route_kind": "conversation",
                    "result": "conversation_route",
                    "resume_action": "grace",
                    "command_action": "retry",
                },
                "completed_turn_lines": [
                    "trace: conversation",
                    "result: conversation_route",
                ],
                "runtime_snapshot": {
                    "startup_mode": "premium",
                },
                "avg_response_first_audio_ms": 145.0,
                "avg_llm_first_chunk_ms": 82.0,
            },
            audio_snapshot={
                "interaction_phase": "command",
                "input_owner": "voice_input",
                "last_resume_policy": {"action": "grace"},
                "last_command_window_policy": {"action": "retry"},
                "last_capture_handoff": {"applied_owner": "voice_input"},
            },
        )

        self.assertIn("technical debug status", presentation.spoken_text.lower())
        self.assertIn("audio phase is command", presentation.spoken_text.lower())
        self.assertIn("latest completed turn ended with result conversation_route", presentation.spoken_text.lower())
        self.assertEqual(
            presentation.display_lines,
            [
                "rt:premium llm:ready",
                "turn:910ms audio:145ms",
            ],
        )
        self.assertEqual(
            presentation.metadata["audio_lines"][0],
            "phase: command",
        )


if __name__ == "__main__":
    unittest.main()