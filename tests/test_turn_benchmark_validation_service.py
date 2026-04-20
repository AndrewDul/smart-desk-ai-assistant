from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.runtime.validation import TurnBenchmarkValidationService


class TestTurnBenchmarkValidationService(unittest.TestCase):
    def _settings(self, path: str) -> dict:
        return {
            "benchmarks": {
                "path": path,
                "summary_window": 30,
            },
            "benchmark_validation": {
                "path": path,
                "window_size": 10,
                "min_completed_turns": 5,
                "min_voice_samples": 5,
                "min_skill_samples": 3,
                "min_llm_samples": 3,
                "max_avg_wake_latency_ms": 450.0,
                "max_avg_stt_latency_ms": 1800.0,
                "max_avg_skill_latency_ms": 350.0,
                "max_avg_response_first_audio_ms": 1200.0,
                "max_avg_route_to_first_audio_ms": 1600.0,
                "max_avg_llm_first_chunk_ms": 1200.0,
                "max_avg_llm_response_first_audio_ms": 1800.0,
                "max_p95_skill_turn_ms": 3500.0,
                "max_p95_llm_turn_ms": 20000.0,
                "max_error_rate": 0.15,
                "min_llm_streaming_ratio": 0.8,
            },
        }

    @staticmethod
    def _sample(
        index: int,
        *,
        skill: bool,
        llm: bool,
        total_ms: float = 3200.0,
        failure: bool = False,
        streaming: bool = True,
        voice: bool = True,
    ) -> dict[str, object]:
        return {
            "turn_id": f"turn-{index}",
            "result": "error" if failure else "ok",
            "input_source": "voice" if voice else "text",
            "wake_input_source": "voice" if voice else "text",
            "stt_input_source": "voice" if voice else "text",
            "wake_latency_ms": 120.0 if voice else None,
            "stt_latency_ms": 900.0 if voice else None,
            "skill_handled": skill,
            "skill_latency_ms": 180.0 if skill else None,
            "response_first_audio_ms": 700.0,
            "route_to_first_audio_ms": 1000.0,
            "llm_first_chunk_ms": 850.0 if llm else None,
            "response_reply_source": "local_llm" if llm else "skill",
            "response_source": "llm" if llm else "action_flow:time",
            "dialogue_source": "local_llm" if llm else "",
            "response_live_streaming": streaming if llm else False,
            "llm_error": "backend timeout" if failure and llm else "",
            "total_turn_ms": total_ms,
        }

    def test_validation_passes_for_healthy_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            samples = [
                self._sample(1, skill=True, llm=False, total_ms=1800.0),
                self._sample(2, skill=True, llm=False, total_ms=1900.0),
                self._sample(3, skill=True, llm=False, total_ms=2000.0),
                self._sample(4, skill=False, llm=True, total_ms=6200.0),
                self._sample(5, skill=False, llm=True, total_ms=6500.0),
                self._sample(6, skill=False, llm=True, total_ms=6800.0),
            ]
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": samples,
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = TurnBenchmarkValidationService(settings=self._settings(str(path)))
            result = service.run()

        self.assertTrue(result.ok)
        self.assertEqual(result.failed_checks(), [])
        self.assertEqual(result.window_sample_count, 6)
        segment_keys = {segment.key for segment in result.segments}
        self.assertEqual(segment_keys, {"voice", "skill", "llm"})

    def test_validation_fails_when_sample_window_is_too_small(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            samples = [
                self._sample(1, skill=True, llm=False),
                self._sample(2, skill=False, llm=True),
            ]
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": samples,
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = TurnBenchmarkValidationService(settings=self._settings(str(path)))
            result = service.run()

        self.assertFalse(result.ok)
        failed_keys = [check.key for check in result.failed_checks()]
        self.assertIn("window.minimum-completed-turns", failed_keys)
        self.assertIn("voice.minimum-samples", failed_keys)
        self.assertIn("skill.minimum-samples", failed_keys)
        self.assertIn("llm.minimum-samples", failed_keys)

    def test_validation_fails_when_segment_thresholds_are_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            samples = [
                self._sample(1, skill=True, llm=False, total_ms=4800.0),
                self._sample(2, skill=True, llm=False, total_ms=5000.0),
                self._sample(3, skill=True, llm=False, total_ms=5200.0),
                self._sample(4, skill=False, llm=True, total_ms=26000.0, failure=True, streaming=False),
                self._sample(5, skill=False, llm=True, total_ms=27000.0, streaming=False),
                self._sample(6, skill=False, llm=True, total_ms=28000.0, streaming=False),
            ]

            for sample in samples:
                sample["wake_latency_ms"] = 700.0
                sample["stt_latency_ms"] = 2400.0
                sample["response_first_audio_ms"] = 2200.0
                sample["route_to_first_audio_ms"] = 2600.0
                if sample["skill_handled"] and sample["response_reply_source"] != "local_llm":
                    sample["skill_latency_ms"] = 550.0
                if sample["response_reply_source"] == "local_llm":
                    sample["llm_first_chunk_ms"] = 1700.0

            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": samples,
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = TurnBenchmarkValidationService(settings=self._settings(str(path)))
            result = service.run()

        self.assertFalse(result.ok)
        failed_keys = {check.key for check in result.failed_checks()}
        self.assertIn("voice.avg-wake-latency-ms", failed_keys)
        self.assertIn("voice.avg-stt-latency-ms", failed_keys)
        self.assertIn("voice.avg-response-first-audio-ms", failed_keys)
        self.assertIn("voice.avg-route-to-first-audio-ms", failed_keys)
        self.assertIn("skill.avg-latency-ms", failed_keys)
        self.assertIn("skill.p95-total-turn-ms", failed_keys)
        self.assertIn("llm.avg-first-chunk-ms", failed_keys)
        self.assertIn("llm.avg-response-first-audio-ms", failed_keys)
        self.assertIn("llm.p95-total-turn-ms", failed_keys)
        self.assertIn("llm.streaming-ratio", failed_keys)
        self.assertIn("overall.error-rate", failed_keys)

    def test_llm_turns_do_not_count_as_skill_samples_when_skill_handled_flag_is_true(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            samples = [
                self._sample(1, skill=True, llm=False),
                self._sample(2, skill=True, llm=False),
                self._sample(3, skill=False, llm=True),
                self._sample(4, skill=False, llm=True),
                self._sample(5, skill=False, llm=True),
            ]
            for sample in samples[2:]:
                sample["skill_handled"] = True

            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": samples,
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = TurnBenchmarkValidationService(settings=self._settings(str(path)))
            result = service.run()

        skill_segment = next(segment for segment in result.segments if segment.key == "skill")
        llm_segment = next(segment for segment in result.segments if segment.key == "llm")
        self.assertEqual(skill_segment.sample_count, 2)
        self.assertEqual(llm_segment.sample_count, 3)


if __name__ == "__main__":
    unittest.main()