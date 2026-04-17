from __future__ import annotations

import unittest

from modules.presentation.runtime_debug_snapshot import RuntimeDebugSnapshotService


class RuntimeDebugSnapshotServiceTests(unittest.TestCase):
    def test_snapshot_composes_runtime_benchmark_audio_and_overlay_lines(self) -> None:
        service = RuntimeDebugSnapshotService(
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
                    "resume_policy": {"action": "grace"},
                    "command_window_policy": {"action": "retry", "phase": "grace"},
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
                "last_resume_policy": {"action": "grace"},
                "last_command_window_policy": {"action": "retry"},
                "last_capture_handoff": {"applied_owner": "voice_input"},
            },
        )

        snapshot = service.snapshot()

        self.assertEqual(snapshot["wake_backend"], "oww")
        self.assertEqual(snapshot["stt_backend"], "faster")
        self.assertEqual(snapshot["llm_backend"], "hailo")
        self.assertEqual(snapshot["runtime_label"], "premium")
        self.assertEqual(snapshot["llm_label"], "ready")
        self.assertAlmostEqual(snapshot["last_turn_ms"], 910.0)
        self.assertAlmostEqual(snapshot["avg_response_first_audio_ms"], 145.0)
        self.assertAlmostEqual(snapshot["avg_llm_first_chunk_ms"], 82.0)
        self.assertEqual(snapshot["completed_turn_trace"]["resume_action"], "grace")
        self.assertEqual(snapshot["completed_turn_trace"]["command_action"], "retry")
        self.assertEqual(snapshot["completed_turn_trace"]["command_phase"], "grace")
        self.assertEqual(snapshot["audio_lines"][0], "phase: command")
        self.assertTrue(snapshot["audio_overlay_line"])
        self.assertEqual(
            snapshot["developer_overlay_lines"],
            [
                "rt:premium llm:ready",
                "turn:910ms audio:145ms",
                "ph:command own:voice_in rs:grac...",
            ],
        )


if __name__ == "__main__":
    unittest.main()