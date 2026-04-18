from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.runtime.telemetry import TurnBenchmarkService


class TurnBenchmarkPendingFlowRegressionTests(unittest.TestCase):
    def test_finish_turn_persists_pending_flow_snapshot_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pending_flow_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            service.note_wake_detected(source="wake_gate", input_source="wake_word")
            turn_id = service.begin_turn(user_text="Andrew", language="en")
            service.note_listening_started(phase="follow_up")
            service.note_speech_finalized(
                text="Andrew",
                phase="follow_up",
                language="en",
                input_source="voice",
                latency_ms=80.0,
                audio_duration_ms=400.0,
                backend_label="faster-whisper",
                mode="follow_up",
                confidence=0.96,
            )

            sample = service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 220.0,
                    "result": "pending_flow",
                    "handled": True,
                    "route_kind": "",
                    "route_confidence": 0.0,
                    "primary_intent": "",
                    "topics": [],
                    "language": "en",
                    "input_source": "voice",
                    "user_text": "Andrew",
                    "pending_consumed_by": "follow_up:capture_name",
                    "pending_kind": "follow_up",
                    "pending_type": "capture_name",
                    "pending_language": "en",
                    "pending_keeps_state": False,
                    "pending_metadata": {
                        "pending_confirmation_active": False,
                        "pending_follow_up_active": False,
                    },
                },
                llm_snapshot={},
                response_report=None,
            )

            self.assertEqual(sample["pending_consumed_by"], "follow_up:capture_name")
            self.assertEqual(sample["pending_kind"], "follow_up")
            self.assertEqual(sample["pending_type"], "capture_name")
            self.assertEqual(sample["pending_language"], "en")
            self.assertFalse(sample["pending_keeps_state"])
            self.assertFalse(sample["pending_metadata"]["pending_follow_up_active"])

            payload = service._store.read()
            persisted = payload["samples"][-1]
            self.assertEqual(persisted["pending_type"], "capture_name")
            self.assertFalse(persisted["pending_keeps_state"])


if __name__ == "__main__":
    unittest.main()