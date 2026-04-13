from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.presentation.response_streamer.models import StreamExecutionReport
from modules.runtime.telemetry import TurnBenchmarkService


class TurnBenchmarkServiceTests(unittest.TestCase):
    def test_finish_turn_persists_sample_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            service.note_wake_detected(source="wake_gate")
            turn_id = service.begin_turn(user_text="what time is it", language="en")
            service.note_listening_started(phase="command")
            service.note_speech_finalized(text="what time is it", phase="command")
            service.note_route_resolved(route_kind="action", primary_intent="time_query", confidence=0.95)

            response_report = StreamExecutionReport(
                chunks_spoken=1,
                full_text="It is 10 o'clock.",
                display_title="ACTION",
                display_lines=["It is 10"],
                first_audio_latency_ms=120.0,
                total_elapsed_ms=340.0,
                started_at_monotonic=1.0,
                first_audio_started_at_monotonic=1.12,
                finished_at_monotonic=1.34,
                chunk_kinds=["content"],
                live_streaming=False,
            )

            sample = service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 950.0,
                    "result": "action_done",
                    "handled": True,
                    "route_kind": "action",
                    "route_confidence": 0.95,
                    "primary_intent": "time_query",
                    "topics": ["time"],
                    "language": "en",
                    "input_source": "voice",
                    "user_text": "what time is it",
                },
                llm_snapshot={
                    "ok": True,
                    "latency_ms": 210.0,
                    "first_chunk_latency_ms": 85.0,
                    "source": "hailo-ollama",
                    "error": "",
                },
                response_report=response_report,
            )

            self.assertEqual(sample["turn_id"], turn_id)
            self.assertEqual(sample["result"], "action_done")
            self.assertEqual(sample["route_kind"], "action")
            self.assertAlmostEqual(sample["total_turn_ms"], 950.0)
            self.assertAlmostEqual(sample["response_first_audio_ms"], 120.0)
            self.assertAlmostEqual(sample["llm_first_chunk_ms"], 85.0)

            payload = service._store.read()
            self.assertEqual(len(payload["samples"]), 1)
            self.assertEqual(payload["summary"]["sample_count"], 1)
            self.assertEqual(payload["summary"]["last_turn_id"], turn_id)

    def test_max_samples_trims_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trimmed_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=20,
                summary_window=5,
            )

            for index in range(25):
                service.note_wake_detected(source=f"wake:{index}")
                turn_id = service.begin_turn(user_text=f"cmd {index}", language="en")
                service.note_listening_started(phase="command")
                service.note_speech_finalized(text=f"cmd {index}", phase="command")
                service.note_route_resolved(route_kind="action", primary_intent="test", confidence=1.0)
                service.finish_turn(
                    telemetry={
                        "benchmark_turn_id": turn_id,
                        "total_ms": 100.0 + index,
                        "result": "ok",
                        "handled": True,
                    },
                    llm_snapshot=None,
                    response_report=None,
                )

            payload = service._store.read()
            self.assertEqual(len(payload["samples"]), 20)
            self.assertEqual(payload["summary"]["sample_count"], 20)
            self.assertEqual(payload["summary"]["window_size"], 5)
            kept_ids = [item["turn_id"] for item in payload["samples"]]
            self.assertEqual(len(set(kept_ids)), 20)


if __name__ == "__main__":
    unittest.main()