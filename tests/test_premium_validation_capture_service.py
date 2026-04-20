from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.runtime.validation.capture_service import PremiumValidationCaptureService


class TestPremiumValidationCaptureService(unittest.TestCase):
    def _settings(self, benchmark_path: str, runtime_status_path: str) -> dict:
        return {
            "benchmarks": {
                "path": benchmark_path,
                "summary_window": 30,
            },
            "benchmark_validation": {
                "path": benchmark_path,
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
            "runtime_product": {
                "status_path": runtime_status_path,
            },
            "premium_validation": {
                "voice_skill_turn_target": 8,
                "llm_short_turn_target": 5,
                "llm_long_turn_target": 3,
                "barge_in_turn_target": 3,
                "reminder_turn_target": 2,
            },
        }

    def test_snapshot_reports_runtime_not_ready_when_status_exists_but_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "turn_benchmarks.json"
            runtime_status_path = Path(temp_dir) / "runtime_status.json"

            benchmark_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": [],
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            runtime_status_path.write_text(
                json.dumps(
                    {
                        "lifecycle_state": "stopped",
                        "startup_mode": "degraded",
                        "primary_ready": False,
                        "premium_ready": False,
                        "updated_at_iso": "2026-04-20T10:00:00Z",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = PremiumValidationCaptureService(
                settings=self._settings(str(benchmark_path), str(runtime_status_path))
            )
            snapshot = service.build_snapshot(stage_key="llm_short")

        self.assertIsNotNone(snapshot.runtime_status)
        assert snapshot.runtime_status is not None
        self.assertEqual(snapshot.runtime_status.lifecycle_state, "stopped")
        self.assertEqual(snapshot.runtime_status.startup_mode, "degraded")
        self.assertFalse(snapshot.runtime_status.primary_ready)
        self.assertIn("Runtime is not ready yet.", snapshot.activity_hints[0])

    def test_snapshot_reports_ready_runtime_but_no_turns_captured_yet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "turn_benchmarks.json"
            runtime_status_path = Path(temp_dir) / "runtime_status.json"

            benchmark_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": [],
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            runtime_status_path.write_text(
                json.dumps(
                    {
                        "lifecycle_state": "ready",
                        "startup_mode": "premium",
                        "primary_ready": True,
                        "premium_ready": False,
                        "updated_at_iso": "2026-04-20T10:00:00Z",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = PremiumValidationCaptureService(
                settings=self._settings(str(benchmark_path), str(runtime_status_path))
            )
            snapshot = service.build_snapshot(stage_key="voice_skill")

        self.assertIsNotNone(snapshot.runtime_status)
        assert snapshot.runtime_status is not None
        self.assertEqual(snapshot.runtime_status.lifecycle_state, "ready")
        self.assertTrue(snapshot.runtime_status.primary_ready)
        joined_hints = " ".join(snapshot.activity_hints)
        self.assertIn("Runtime looks ready, but no benchmark turns have been captured yet.", joined_hints)

    def test_render_snapshot_includes_runtime_status_and_activity_hints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark_path = Path(temp_dir) / "turn_benchmarks.json"
            runtime_status_path = Path(temp_dir) / "runtime_status.json"

            benchmark_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at_iso": "",
                        "samples": [],
                        "summary": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            runtime_status_path.write_text(
                json.dumps(
                    {
                        "lifecycle_state": "ready",
                        "startup_mode": "premium",
                        "primary_ready": True,
                        "premium_ready": False,
                        "updated_at_iso": "2026-04-20T10:00:00Z",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = PremiumValidationCaptureService(
                settings=self._settings(str(benchmark_path), str(runtime_status_path))
            )
            snapshot = service.build_snapshot(stage_key="llm_short")
            rendered = service.render_snapshot(snapshot)

        self.assertIn("Runtime status:", rendered)
        self.assertIn("lifecycle_state: ready", rendered)
        self.assertIn("startup_mode: premium", rendered)
        self.assertIn("Activity hints:", rendered)


if __name__ == "__main__":
    unittest.main()