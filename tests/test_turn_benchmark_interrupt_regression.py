from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.runtime.telemetry import TurnBenchmarkService


class TurnBenchmarkInterruptRegressionTests(unittest.TestCase):
    def test_annotate_last_completed_turn_persists_interrupt_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "interrupt_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            turn_id = service.begin_turn(user_text="hello", language="en")
            service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 150.0,
                    "result": "conversation_route",
                    "handled": True,
                    "route_kind": "conversation",
                    "route_confidence": 0.9,
                    "primary_intent": "greeting",
                    "topics": [],
                    "language": "en",
                    "input_source": "voice",
                    "user_text": "hello",
                },
                llm_snapshot={},
                response_report=None,
            )

            updated = service.annotate_last_completed_turn(
                interrupt_snapshot={
                    "requested": True,
                    "generation": 3,
                    "reason": "wake_barge_in",
                    "source": "wake_gate",
                    "kind": "barge_in",
                    "metadata": {"backend": "runtime.wake_gate"},
                }
            )

            self.assertTrue(updated)
            sample = service.latest_sample()
            self.assertTrue(sample["interrupt_requested"])
            self.assertEqual(sample["interrupt_generation"], 3)
            self.assertEqual(sample["interrupt_kind"], "barge_in")
            self.assertEqual(sample["interrupt_metadata"]["backend"], "runtime.wake_gate")

            payload = service._store.read()
            persisted = payload["samples"][-1]
            self.assertEqual(persisted["interrupt_reason"], "wake_barge_in")
            self.assertEqual(persisted["interrupt_source"], "wake_gate")


if __name__ == "__main__":
    unittest.main()