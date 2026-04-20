from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.runtime.validation.sample_diagnostics_service import (
    TurnBenchmarkSampleDiagnosticsService,
)


class TurnBenchmarkSampleDiagnosticsTests(unittest.TestCase):
    def test_describe_sample_marks_llm_when_reply_source_is_local_llm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": [
                            {
                                "turn_id": "bench_1",
                                "input_source": "voice",
                                "voice_benchmark_ready": True,
                                "stt_backend_label": "faster_whisper",
                                "stt_mode": "conversation",
                                "capture_profile": "conversation",
                                "stt_latency_ms": 640.0,
                                "response_reply_source": "local_llm",
                                "response_source": "response_streamer",
                                "dialogue_source": "local_llm",
                                "llm_source": "local_llm",
                                "llm_first_chunk_ms": 420.0,
                                "skill_handled": False,
                            }
                        ],
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = TurnBenchmarkSampleDiagnosticsService(
                settings={
                    "benchmarks": {"path": str(path)},
                    "benchmark_validation": {},
                }
            )

            description = service.describe_sample(service.read_samples()[0])

        self.assertTrue(description["voice"])
        self.assertTrue(description["llm"])
        self.assertFalse(description["skill"])
        self.assertIn("response_reply_source=local_llm", description["llm_reasons"])
        self.assertIn("llm_source=local_llm", description["llm_reasons"])

    def test_describe_sample_marks_skill_when_skill_handled_is_true(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": [
                            {
                                "turn_id": "bench_2",
                                "input_source": "voice",
                                "voice_benchmark_ready": True,
                                "stt_backend_label": "faster_whisper",
                                "stt_mode": "command",
                                "capture_profile": "command",
                                "stt_latency_ms": 510.0,
                                "response_reply_source": "builtin",
                                "response_source": "action_response",
                                "skill_handled": True,
                                "skill_source": "timer_skill",
                            }
                        ],
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = TurnBenchmarkSampleDiagnosticsService(
                settings={
                    "benchmarks": {"path": str(path)},
                    "benchmark_validation": {},
                }
            )

            description = service.describe_sample(service.read_samples()[0])

        self.assertTrue(description["voice"])
        self.assertFalse(description["llm"])
        self.assertTrue(description["skill"])
        self.assertIn("skill_handled=true", description["skill_reasons"])
        self.assertIn("response_source=action_response", description["skill_reasons"])
        self.assertIn("response_reply_source=builtin", description["skill_reasons"])


if __name__ == "__main__":
    unittest.main()