from __future__ import annotations

import unittest

from modules.presentation.runtime_debug_snapshot import RuntimeDebugSnapshotService


class AiBrokerDebugSnapshotTests(unittest.TestCase):
    def test_snapshot_includes_ai_broker_payload_and_recovery_line(self) -> None:
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
            ai_broker_snapshot_provider=lambda: {
                "mode": "recovery_window",
                "owner": "balanced",
                "profile": {"heavy_lane_cadence_hz": 1.0},
                "recovery_window_active": True,
            },
        )

        snapshot = service.snapshot()

        self.assertEqual(snapshot["ai_broker_snapshot"]["mode"], "recovery_window")
        self.assertEqual(snapshot["ai_broker_line"], "ai:recovery_w own:balanced hv:1...")
        self.assertEqual(
            snapshot["developer_overlay_lines"],
            [
                "rt:premium llm:ready",
                "ai:recovery_w own:balanced hv:1...",
                "ph:command own:voice_in rs:grac...",
            ],
        )


if __name__ == "__main__":
    unittest.main()