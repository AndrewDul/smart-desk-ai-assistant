from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.runtime.validation import PremiumReleaseGateService
from modules.runtime.validation.models import (
    BenchmarkThresholdCheck,
    BenchmarkValidationSegment,
    TurnBenchmarkValidationResult,
)
from modules.system.deployment.acceptance_models import (
    BootAcceptanceCheck,
    SystemdBootAcceptanceResult,
)


class TestPremiumReleaseGateService(unittest.TestCase):
    def _benchmark_result(
        self,
        *,
        ok: bool,
        failed_keys: list[str],
        window_samples: int,
    ) -> TurnBenchmarkValidationResult:
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
        segments = [
            BenchmarkValidationSegment(key="voice", label="Wake and voice input", sample_count=10),
            BenchmarkValidationSegment(key="skill", label="Built-in skills", sample_count=8),
            BenchmarkValidationSegment(key="llm", label="LLM dialogue", sample_count=6),
        ]
        segment_map = {segment.key: segment for segment in segments}
        for key in failed_keys:
            segment_key = key.split(".", 1)[0]
            if segment_key in segment_map:
                segment_map[segment_key].checks.append(
                    BenchmarkThresholdCheck(
                        key=key,
                        ok=False,
                        actual=None,
                        expected=None,
                        details="failed",
                        comparator="",
                    )
                )
        return TurnBenchmarkValidationResult(
            ok=ok,
            path="/tmp/turn_benchmarks.json",
            sample_count=40,
            window_sample_count=window_samples,
            latest_turn_id="bench_latest",
            metrics={"overall": {"error_rate": 0.0}},
            checks=checks,
            segments=segments,
        )

    def _boot_result(
        self,
        *,
        ok: bool,
        lifecycle_state: str,
        startup_mode: str,
        primary_ready: bool,
        premium_ready: bool,
        failed_keys: list[str],
    ) -> SystemdBootAcceptanceResult:
        checks = [
            BootAcceptanceCheck(
                key=key,
                ok=False,
                details="failed",
                remediation="fix",
            )
            for key in failed_keys
        ]
        return SystemdBootAcceptanceResult(
            ok=ok,
            strict_premium=True,
            system_dir="/etc/systemd/system",
            runtime_status_path="/tmp/runtime_status.json",
            checked_unit_names=["nexa.service"],
            checks=checks,
            runtime_snapshot={
                "lifecycle_state": lifecycle_state,
                "startup_mode": startup_mode,
                "primary_ready": primary_ready,
                "premium_ready": premium_ready,
            },
        )

    def test_release_gate_passes_only_when_benchmark_and_boot_are_both_ready(self) -> None:
        with patch(
            "modules.runtime.validation.release_gate_service.TurnBenchmarkValidationService.run",
            return_value=self._benchmark_result(ok=True, failed_keys=[], window_samples=18),
        ):
            with patch(
                "modules.runtime.validation.release_gate_service.SystemdBootAcceptanceService.run",
                return_value=self._boot_result(
                    ok=True,
                    lifecycle_state="ready",
                    startup_mode="premium",
                    primary_ready=True,
                    premium_ready=True,
                    failed_keys=[],
                ),
            ):
                service = PremiumReleaseGateService(
                    settings={"premium_release": {"min_benchmark_window_samples": 10}}
                )
                result = service.run()

        self.assertTrue(result.ok)
        self.assertEqual(result.verdict, "premium-ready")
        self.assertEqual(result.failed_items(), [])

    def test_release_gate_blocks_when_voice_benchmark_and_runtime_state_fail(self) -> None:
        with patch(
            "modules.runtime.validation.release_gate_service.TurnBenchmarkValidationService.run",
            return_value=self._benchmark_result(
                ok=False,
                failed_keys=["voice.avg-wake-latency-ms", "voice.avg-stt-latency-ms"],
                window_samples=7,
            ),
        ):
            with patch(
                "modules.runtime.validation.release_gate_service.SystemdBootAcceptanceService.run",
                return_value=self._boot_result(
                    ok=False,
                    lifecycle_state="degraded",
                    startup_mode="limited",
                    primary_ready=True,
                    premium_ready=False,
                    failed_keys=["runtime-product-state"],
                ),
            ):
                service = PremiumReleaseGateService(
                    settings={"premium_release": {"min_benchmark_window_samples": 10}}
                )
                result = service.run()

        self.assertFalse(result.ok)
        self.assertEqual(result.verdict, "blocked")
        failed_keys = {item.key for item in result.failed_items()}
        self.assertIn("boot.strict-acceptance", failed_keys)
        self.assertIn("benchmark.validation", failed_keys)
        self.assertIn("benchmark.window-size", failed_keys)
        self.assertIn("segment.voice", failed_keys)
        self.assertIn("runtime.lifecycle-state", failed_keys)
        self.assertIn("runtime.startup-mode", failed_keys)
        self.assertIn("runtime.premium-ready", failed_keys)


if __name__ == "__main__":
    unittest.main()