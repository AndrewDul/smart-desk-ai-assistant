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

    def test_build_status_metadata_merges_expected_fields(self) -> None:
        metadata = self.service.build_status_metadata(
            resolved_source="route.primary_intent",
            timer_running=True,
            focus_mode=True,
            break_mode=False,
            memory_count=1,
            reminder_count=2,
            current_timer="focus",
            audio_runtime_snapshot={"interaction_phase": "command"},
            runtime_debug_snapshot={"wake_backend": "oww"},
            runtime_status_metadata={"runtime_primary_ready": True},
            runtime_metadata={"last_turn_ms": 910.0},
            presentation_metadata={"feature_lines": ["focus: ON"]},
        )

        self.assertEqual(metadata["resolved_source"], "route.primary_intent")
        self.assertTrue(metadata["timer_running"])
        self.assertTrue(metadata["focus_mode"])
        self.assertEqual(metadata["memory_count"], 1)
        self.assertEqual(metadata["audio_runtime_snapshot"]["interaction_phase"], "command")
        self.assertEqual(metadata["runtime_debug_snapshot"]["wake_backend"], "oww")
        self.assertTrue(metadata["runtime_primary_ready"])
        self.assertAlmostEqual(metadata["last_turn_ms"], 910.0)
        self.assertEqual(metadata["feature_lines"], ["focus: ON"])

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

    def test_build_debug_status_metadata_merges_expected_fields(self) -> None:
        metadata = self.service.build_debug_status_metadata(
            resolved_source="route.primary_intent",
            audio_runtime_snapshot={"interaction_phase": "command"},
            runtime_debug_snapshot={"developer_overlay_lines": ["rt:premium llm:ready"]},
            runtime_status_metadata={"runtime_primary_ready": True},
            runtime_metadata={"wake_backend": "oww"},
            presentation_metadata={"debug_lines": ["mode: premium"]},
        )

        self.assertEqual(metadata["resolved_source"], "route.primary_intent")
        self.assertEqual(metadata["audio_runtime_snapshot"]["interaction_phase"], "command")
        self.assertTrue(metadata["runtime_primary_ready"])
        self.assertEqual(metadata["wake_backend"], "oww")
        self.assertEqual(metadata["debug_lines"], ["mode: premium"])


if __name__ == "__main__":
    unittest.main()