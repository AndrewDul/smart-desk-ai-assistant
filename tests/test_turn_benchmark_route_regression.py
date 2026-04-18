from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.presentation.response_streamer.models import StreamExecutionReport
from modules.runtime.telemetry import TurnBenchmarkService


class TurnBenchmarkRouteRegressionTests(unittest.TestCase):
    def test_finish_turn_persists_action_and_dialogue_route_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "route_regression_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            service.note_wake_detected(source="wake_gate", input_source="wake_word")
            turn_id = service.begin_turn(user_text="help me and set a timer", language="en")
            service.note_listening_started(phase="conversation")
            service.note_speech_finalized(
                text="help me and set a timer",
                phase="conversation",
                language="en",
                input_source="voice",
                latency_ms=210.0,
                audio_duration_ms=1800.0,
                backend_label="faster-whisper",
                mode="conversation",
                confidence=0.89,
            )
            service.note_route_resolved(
                route_kind="mixed",
                primary_intent="support_request",
                confidence=0.87,
            )

            report = StreamExecutionReport(
                chunks_spoken=2,
                full_text="I can help with that and I will start a timer.",
                display_title="CHAT",
                display_lines=["I can help"],
                first_audio_latency_ms=140.0,
                total_elapsed_ms=420.0,
                started_at_monotonic=1.0,
                first_audio_started_at_monotonic=1.14,
                finished_at_monotonic=1.42,
                chunk_kinds=["content", "follow_up"],
                live_streaming=True,
            )

            sample = service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 1100.0,
                    "result": "mixed_route",
                    "handled": True,
                    "route_kind": "mixed",
                    "route_confidence": 0.87,
                    "primary_intent": "support_request",
                    "topics": ["productivity"],
                    "language": "en",
                    "input_source": "voice",
                    "user_text": "help me and set a timer",
                    "response_source": "dialogue_flow",
                    "response_reply_source": "local_llm",
                    "response_display_title": "CHAT",
                    "response_stream_mode": "sentence",
                    "action_name": "timer_start",
                    "action_source": "tool.timer.start",
                    "action_confidence": 0.95,
                    "skill_action": "timer_start",
                    "skill_status": "completed",
                    "skill_handled": True,
                    "skill_response_delivered": True,
                    "skill_source": "tool.timer.start",
                    "dialogue_status": "completed",
                    "dialogue_delivered": True,
                    "dialogue_source": "dialogue_flow",
                    "dialogue_reply_mode": "reply_then_offer",
                    "route_notes": ["mixed_route", "timer_action"],
                },
                llm_snapshot={
                    "ok": True,
                    "latency_ms": 260.0,
                    "first_chunk_latency_ms": 90.0,
                    "source": "hailo-ollama",
                    "error": "",
                },
                response_report=report,
            )

            self.assertEqual(sample["route_kind"], "mixed")
            self.assertEqual(sample["response_source"], "dialogue_flow")
            self.assertEqual(sample["response_reply_source"], "local_llm")
            self.assertEqual(sample["action_name"], "timer_start")
            self.assertEqual(sample["skill_action"], "timer_start")
            self.assertEqual(sample["skill_status"], "completed")
            self.assertTrue(sample["skill_response_delivered"])
            self.assertEqual(sample["dialogue_status"], "completed")
            self.assertTrue(sample["dialogue_delivered"])
            self.assertEqual(sample["dialogue_reply_mode"], "reply_then_offer")
            self.assertEqual(sample["route_notes"], ["mixed_route", "timer_action"])

            payload = service._store.read()
            persisted = payload["samples"][-1]
            self.assertEqual(persisted["action_source"], "tool.timer.start")
            self.assertEqual(persisted["dialogue_source"], "dialogue_flow")


if __name__ == "__main__":
    unittest.main()