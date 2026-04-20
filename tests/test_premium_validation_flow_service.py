from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.runtime.validation import PremiumValidationFlowService
from modules.runtime.validation.models import (
    BenchmarkThresholdCheck,
    BenchmarkValidationSegment,
    TurnBenchmarkValidationResult,
)


class TestPremiumValidationFlowService(unittest.TestCase):
    def _result(self, failed_keys: list[str]) -> TurnBenchmarkValidationResult:
        checks = [
            BenchmarkThresholdCheck(
                key=key,
                ok=False,
                actual=None,
                expected=None,
                details="failed",
                comparator="",
            )
            for key in failed_keys
        ]
        return TurnBenchmarkValidationResult(
            ok=not failed_keys,
            path="/tmp/turn_benchmarks.json",
            sample_count=20,
            window_sample_count=10,
            latest_turn_id="bench_latest",
            metrics={"overall": {"error_rate": 0.0}},
            checks=checks,
            segments=[
                BenchmarkValidationSegment(key="voice", label="Wake and voice input", sample_count=10),
                BenchmarkValidationSegment(key="skill", label="Built-in skills", sample_count=6),
                BenchmarkValidationSegment(key="llm", label="LLM dialogue", sample_count=4),
            ],
        )

    def test_flow_prioritizes_segments_by_failed_checks(self) -> None:
        with patch(
            "modules.runtime.validation.flow_service.TurnBenchmarkValidationService.run",
            return_value=self._result(
                [
                    "voice.avg-wake-latency-ms",
                    "voice.avg-stt-latency-ms",
                    "llm.streaming-ratio",
                    "skill.avg-latency-ms",
                ]
            ),
        ):
            service = PremiumValidationFlowService(
                settings={"premium_validation": {"voice_skill_turn_target": 8}}
            )
            flow = service.build_flow()

        self.assertEqual(flow.priority_segments, ["voice", "llm", "skill"])
        self.assertEqual(flow.stages[0].key, "preflight")
        self.assertEqual(flow.stages[-1].key, "final_gate")

    def test_flow_contains_repeatable_raspberry_pi_scenarios(self) -> None:
        with patch(
            "modules.runtime.validation.flow_service.TurnBenchmarkValidationService.run",
            return_value=self._result([]),
        ):
            service = PremiumValidationFlowService(
                settings={
                    "premium_validation": {
                        "voice_skill_turn_target": 8,
                        "llm_short_turn_target": 5,
                        "llm_long_turn_target": 3,
                        "barge_in_turn_target": 3,
                        "reminder_turn_target": 2,
                    }
                }
            )
            flow = service.build_flow()

        scenario_keys = [
            scenario.key
            for stage in flow.stages
            for scenario in stage.scenarios
        ]
        self.assertIn("voice-short-skills", scenario_keys)
        self.assertIn("llm-short-streaming", scenario_keys)
        self.assertIn("llm-long-answer-stress", scenario_keys)
        self.assertIn("barge-in-and-follow-up", scenario_keys)
        self.assertIn("reminder-reliability", scenario_keys)


if __name__ == "__main__":
    unittest.main()