from __future__ import annotations

import unittest

from modules.presentation.developer_overlay import DeveloperOverlayService
from modules.presentation.runtime_debug_snapshot import RuntimeDebugSnapshotService
from modules.presentation.status_debug_presenter.service import StatusDebugPresenterService


class _FakeDisplay:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.clear_calls = 0

    def set_developer_overlay(self, title: str, lines: list[str]) -> None:
        self.calls.append({"title": str(title), "lines": list(lines)})

    def clear_developer_overlay(self) -> None:
        self.clear_calls += 1


class Stage3ObservabilityContractTests(unittest.TestCase):
    def test_runtime_debug_snapshot_overlay_and_presenter_stay_consistent(self) -> None:
        runtime_debug = RuntimeDebugSnapshotService(
            runtime_snapshot_provider=lambda: {
                "premium_ready": True,
                "llm_enabled": True,
                "llm_warmup_ready": True,
                "services": {
                    "wake_gate": {"backend": "openwakeword"},
                    "voice_input": {"backend": "faster_whisper"},
                    "llm": {"backend": "hailo-ollama"},
                },
            },
            benchmark_snapshot_provider=lambda: {
                "latest_sample": {
                    "total_turn_ms": 910.0,
                    "result": "conversation_route",
                    "route_kind": "conversation",
                    "resume_policy": {
                        "action": "grace",
                        "reason": "response_delivered",
                    },
                    "command_window_policy": {
                        "action": "retry",
                        "reason": "empty_capture",
                        "phase": "grace",
                    },
                },
                "summary": {
                    "avg_response_first_audio_ms": 145.0,
                    "avg_llm_first_chunk_ms": 82.0,
                },
                "overlay_lines": [
                    "turn:910ms audio:145ms",
                    "llm:82ms result:conver",
                ],
            },
            audio_snapshot_provider=lambda: {
                "interaction_phase": "command",
                "input_owner": "voice_input",
                "active_window_remaining_seconds": 2.4,
                "last_resume_policy": {
                    "action": "grace",
                    "reason": "response_delivered",
                },
                "last_command_window_policy": {
                    "action": "retry",
                    "reason": "empty_capture",
                },
                "last_capture_handoff": {
                    "applied_owner": "voice_input",
                },
            },
        )

        debug_snapshot = runtime_debug.snapshot()

        self.assertEqual(debug_snapshot["wake_backend"], "oww")
        self.assertEqual(debug_snapshot["stt_backend"], "faster")
        self.assertEqual(debug_snapshot["llm_backend"], "hailo")
        self.assertEqual(debug_snapshot["completed_turn_trace"]["resume_action"], "grace")
        self.assertEqual(debug_snapshot["completed_turn_trace"]["command_action"], "retry")

        display = _FakeDisplay()
        overlay = DeveloperOverlayService(
            display=display,
            runtime_snapshot_provider=lambda: {},
            benchmark_snapshot_provider=lambda: {},
            audio_snapshot_provider=lambda: {},
            debug_snapshot_provider=lambda: debug_snapshot,
            enabled=True,
            title="DEV",
        )

        refreshed = overlay.refresh(reason="turn_finished")

        self.assertTrue(refreshed)
        self.assertEqual(len(display.calls), 1)
        self.assertEqual(
            display.calls[0]["lines"],
            [
                "rt:premium llm:ready",
                "turn:910ms audio:145ms",
                "ph:command own:voice_in rs:grac...",
            ],
        )

        presenter = StatusDebugPresenterService()
        runtime_metadata = {
            "runtime_snapshot": dict(debug_snapshot.get("runtime_snapshot", {}) or {}),
            "benchmark_snapshot": dict(debug_snapshot.get("benchmark_snapshot", {}) or {}),
            "wake_backend": debug_snapshot.get("wake_backend"),
            "stt_backend": debug_snapshot.get("stt_backend"),
            "llm_backend": debug_snapshot.get("llm_backend"),
            "last_turn_ms": debug_snapshot.get("last_turn_ms"),
            "avg_response_first_audio_ms": debug_snapshot.get("avg_response_first_audio_ms"),
            "avg_llm_first_chunk_ms": debug_snapshot.get("avg_llm_first_chunk_ms"),
            "completed_turn_trace": dict(debug_snapshot.get("completed_turn_trace", {}) or {}),
            "completed_turn_lines": list(debug_snapshot.get("completed_turn_lines", []) or []),
            "runtime_debug_snapshot": dict(debug_snapshot or {}),
        }

        status_presentation = presenter.build_status_presentation(
            language="en",
            runtime_status_spoken="Premium mode is ready. Wake uses oww, STT uses faster, and LLM uses hailo.",
            runtime_status_lines=["premium: YES", "core: YES", "wake: oww"],
            benchmark_spoken=(
                "The latest full turn took 910 milliseconds. "
                "Average voice start is 145 milliseconds, and average LLM first chunk is 82 milliseconds."
            ),
            runtime_metadata=runtime_metadata,
            focus_on=True,
            break_on=False,
            current_timer="focus",
            memory_count=1,
            reminder_count=2,
            timer_running=True,
        )

        self.assertIn("latest full turn took 910 milliseconds", status_presentation.spoken_text.lower())
        self.assertEqual(status_presentation.display_lines[2], "trace: conversation")

        debug_presentation = presenter.build_debug_status_presentation(
            language="en",
            runtime_status_spoken="Premium mode is ready. Wake uses oww, STT uses faster, and LLM uses hailo.",
            benchmark_spoken=(
                "The latest full turn took 910 milliseconds. "
                "Average voice start is 145 milliseconds, and average LLM first chunk is 82 milliseconds."
            ),
            runtime_metadata=runtime_metadata,
            audio_snapshot=dict(debug_snapshot.get("audio_runtime_snapshot", {}) or {}),
        )

        self.assertIn("technical debug status", debug_presentation.spoken_text.lower())
        self.assertIn(
            "latest completed turn ended with result conversation_route",
            debug_presentation.spoken_text.lower(),
        )
        self.assertEqual(debug_presentation.display_lines[0], "rt:premium llm:ready")
        self.assertEqual(
            debug_presentation.metadata["completed_turn_trace"]["resume_action"],
            "grace",
        )


if __name__ == "__main__":
    unittest.main()