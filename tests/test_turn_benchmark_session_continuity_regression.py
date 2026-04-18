from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.runtime.telemetry import TurnBenchmarkService


class TurnBenchmarkSessionContinuityRegressionTests(unittest.TestCase):
    def test_annotate_last_completed_turn_persists_session_continuity_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session_continuity_benchmarks.json"
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
                    "total_ms": 180.0,
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
                continuity_snapshot={
                    "action": "grace",
                    "phase": "grace",
                    "reason": "response_delivered",
                    "detail": "grace_after_response",
                    "window_seconds": 2.5,
                    "pending_kind": "",
                    "pending_type": "",
                    "pending_language": "",
                }
            )

            self.assertTrue(updated)
            sample = service.latest_sample()
            self.assertEqual(sample["session_continuity_action"], "grace")
            self.assertEqual(sample["session_continuity_phase"], "grace")
            self.assertEqual(sample["session_continuity_reason"], "response_delivered")
            self.assertEqual(sample["session_continuity_detail"], "grace_after_response")
            self.assertAlmostEqual(sample["session_continuity_window_seconds"], 2.5)
            self.assertEqual(sample["session_continuity"]["action"], "grace")

            payload = service._store.read()
            persisted = payload["samples"][-1]
            self.assertEqual(persisted["session_continuity_phase"], "grace")
            self.assertAlmostEqual(persisted["session_continuity_window_seconds"], 2.5)


if __name__ == "__main__":
    unittest.main()