from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.presentation.response_streamer.models import StreamExecutionReport
from modules.runtime.telemetry import TurnBenchmarkService


class TurnBenchmarkSkillLatencyRegressionTests(unittest.TestCase):
    def test_finish_turn_persists_skill_latency_and_response_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "skill_latency_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            service.note_wake_detected(source="wake_gate", input_source="wake_word")
            turn_id = service.begin_turn(user_text="start a timer", language="en")
            service.note_listening_started(phase="command")
            service.note_speech_finalized(
                text="start a timer",
                phase="command",
                language="en",
                input_source="voice",
                latency_ms=120.0,
                audio_duration_ms=900.0,
                backend_label="faster-whisper",
                mode="command",
                confidence=0.95,
            )
            service.note_route_resolved(
                route_kind="action",
                primary_intent="timer_start",
                confidence=0.94,
            )

            report = StreamExecutionReport(
                chunks_spoken=0,
                full_text="",
                display_title="",
                display_lines=[],
                first_audio_latency_ms=0.0,
                total_elapsed_ms=0.0,
                started_at_monotonic=1.0,
                first_audio_started_at_monotonic=0.0,
                finished_at_monotonic=1.01,
                chunk_kinds=[],
                live_streaming=False,
            )

            sample = service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 310.0,
                    "result": "action_route",
                    "handled": True,
                    "route_kind": "action",
                    "route_confidence": 0.94,
                    "primary_intent": "timer_start",
                    "topics": [],
                    "language": "en",
                    "input_source": "voice",
                    "user_text": "start a timer",
                    "skill_action": "timer_start",
                    "skill_status": "accepted",
                    "skill_handled": True,
                    "skill_response_delivered": False,
                    "skill_source": "timer_service.start",
                    "skill_latency_ms": 12.5,
                    "skill_response_kind": "accepted_only",
                },
                llm_snapshot={},
                response_report=report,
            )

            self.assertEqual(sample["skill_action"], "timer_start")
            self.assertEqual(sample["skill_status"], "accepted")
            self.assertEqual(sample["skill_source"], "timer_service.start")
            self.assertAlmostEqual(sample["skill_latency_ms"], 12.5)
            self.assertEqual(sample["skill_response_kind"], "accepted_only")

            payload = service._store.read()
            persisted = payload["samples"][-1]
            self.assertAlmostEqual(persisted["skill_latency_ms"], 12.5)
            self.assertEqual(persisted["skill_response_kind"], "accepted_only")


if __name__ == "__main__":
    unittest.main()