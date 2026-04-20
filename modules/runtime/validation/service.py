from __future__ import annotations

import math
from typing import Any

from modules.shared.config.settings import load_settings
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import resolve_optional_path

from .models import (
    BenchmarkThresholdCheck,
    BenchmarkValidationSegment,
    TurnBenchmarkValidationResult,
)


class TurnBenchmarkValidationService:
    """Validate persisted turn benchmarks against product thresholds."""

    _LLM_SOURCES = {"llm", "local_llm", "remote_llm", "ollama", "hailo_ollama"}

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()
        self.benchmark_cfg = self._cfg("benchmarks")
        self.validation_cfg = self._cfg("benchmark_validation")

        path = self._cfg_text(
            "path",
            default=str(self.benchmark_cfg.get("path", "var/data/turn_benchmarks.json")),
        )
        resolved_path = resolve_optional_path(path)
        if resolved_path is None:
            raise ValueError("Benchmark validation path cannot be None.")

        self._store = JsonStore(
            path=resolved_path,
            default_factory=self._default_payload,
        )

    def run(self) -> TurnBenchmarkValidationResult:
        read_result = self._store.read_result()
        payload = read_result.value if isinstance(read_result.value, dict) else {}
        samples = [
            dict(item)
            for item in list(payload.get("samples", []) or [])
            if isinstance(item, dict)
        ]

        window_size = self._cfg_int(
            "window_size",
            default=int(
                self.validation_cfg.get(
                    "window_size",
                    self.benchmark_cfg.get("summary_window", 30),
                )
            ),
        )
        window_size = max(1, window_size)
        window = samples[-window_size:] if samples else []
        latest = window[-1] if window else {}

        segments = self._build_segments(window)
        metrics = {
            "overall": self._build_overall_metrics(window),
            **{segment.key: dict(segment.metrics) for segment in segments},
        }
        checks: list[BenchmarkThresholdCheck] = []

        checks.append(
            BenchmarkThresholdCheck(
                key="benchmark-file-valid",
                ok=bool(read_result.exists and read_result.valid),
                actual=f"exists={read_result.exists}, valid={read_result.valid}",
                expected="exists=True, valid=True",
                comparator="==",
                details=f"Benchmark file path: {read_result.path}",
            )
        )
        self._add_min_check(
            checks,
            key="window.minimum-completed-turns",
            actual=len(window),
            expected=self._cfg_int("min_completed_turns", default=5),
            details="Window must include enough completed turns to make the benchmark meaningful.",
        )
        self._add_max_check(
            checks,
            key="overall.error-rate",
            actual=metrics["overall"].get("error_rate"),
            expected=self._cfg_float("max_error_rate", default=0.15),
            details="Failure rate must stay low across the validation window.",
        )

        for segment in segments:
            segment.checks.extend(self._build_segment_checks(segment))
            checks.extend(segment.checks)

        ok = all(check.ok for check in checks)
        return TurnBenchmarkValidationResult(
            ok=ok,
            path=str(read_result.path),
            sample_count=len(samples),
            window_sample_count=len(window),
            latest_turn_id=str(latest.get("turn_id", "") or "").strip(),
            metrics=metrics,
            checks=checks,
            segments=segments,
        )

    def _build_segments(self, samples: list[dict[str, Any]]) -> list[BenchmarkValidationSegment]:
        voice_samples = [sample for sample in samples if self._is_voice_turn(sample)]
        llm_samples = [sample for sample in samples if self._is_llm_turn(sample)]
        skill_samples = [sample for sample in samples if self._is_skill_turn(sample)]

        return [
            BenchmarkValidationSegment(
                key="voice",
                label="Wake and voice input",
                sample_count=len(voice_samples),
                metrics=self._build_voice_metrics(voice_samples),
            ),
            BenchmarkValidationSegment(
                key="skill",
                label="Built-in skills",
                sample_count=len(skill_samples),
                metrics=self._build_skill_metrics(skill_samples),
            ),
            BenchmarkValidationSegment(
                key="llm",
                label="LLM dialogue",
                sample_count=len(llm_samples),
                metrics=self._build_llm_metrics(llm_samples),
            ),
        ]

    def _build_segment_checks(self, segment: BenchmarkValidationSegment) -> list[BenchmarkThresholdCheck]:
        checks: list[BenchmarkThresholdCheck] = []
        metrics = segment.metrics

        if segment.key == "voice":
            self._add_min_check(
                checks,
                key="voice.minimum-samples",
                actual=segment.sample_count,
                expected=self._cfg_int(
                    "min_voice_samples",
                    default=self._cfg_int("min_completed_turns", default=5),
                ),
                details="Voice validation requires enough wake and speech turns.",
            )
            self._add_max_check(
                checks,
                key="voice.avg-wake-latency-ms",
                actual=metrics.get("avg_wake_latency_ms"),
                expected=self._cfg_float("max_avg_wake_latency_ms", default=450.0),
                details="Wake path should feel immediate.",
            )
            self._add_max_check(
                checks,
                key="voice.avg-stt-latency-ms",
                actual=metrics.get("avg_stt_latency_ms"),
                expected=self._cfg_float("max_avg_stt_latency_ms", default=1800.0),
                details="Speech recognition should finalize quickly.",
            )
            self._add_max_check(
                checks,
                key="voice.avg-response-first-audio-ms",
                actual=metrics.get("avg_response_first_audio_ms"),
                expected=self._cfg_float("max_avg_response_first_audio_ms", default=1200.0),
                details="First spoken audio should start early for voice turns.",
            )
            self._add_max_check(
                checks,
                key="voice.avg-route-to-first-audio-ms",
                actual=metrics.get("avg_route_to_first_audio_ms"),
                expected=self._cfg_float("max_avg_route_to_first_audio_ms", default=1600.0),
                details="Route to audible reply should stay short for voice turns.",
            )

        if segment.key == "skill":
            self._add_min_check(
                checks,
                key="skill.minimum-samples",
                actual=segment.sample_count,
                expected=self._cfg_int("min_skill_samples", default=3),
                details="Skill path validation needs a few deterministic command turns.",
            )
            self._add_max_check(
                checks,
                key="skill.avg-latency-ms",
                actual=metrics.get("avg_skill_latency_ms"),
                expected=self._cfg_float("max_avg_skill_latency_ms", default=350.0),
                details="Built-in commands should stay deterministic and fast.",
            )
            self._add_max_check(
                checks,
                key="skill.p95-total-turn-ms",
                actual=metrics.get("p95_total_turn_ms"),
                expected=self._cfg_float(
                    "max_p95_skill_turn_ms",
                    default=self._cfg_float("max_p95_total_turn_ms", default=7000.0),
                ),
                details="Skill turns should stay short end-to-end.",
            )

        if segment.key == "llm":
            self._add_min_check(
                checks,
                key="llm.minimum-samples",
                actual=segment.sample_count,
                expected=self._cfg_int("min_llm_samples", default=3),
                details="LLM validation needs a few streamed dialogue turns.",
            )
            self._add_max_check(
                checks,
                key="llm.avg-first-chunk-ms",
                actual=metrics.get("avg_llm_first_chunk_ms"),
                expected=self._cfg_float("max_avg_llm_first_chunk_ms", default=1200.0),
                details="Streaming LLM should produce the first chunk quickly.",
            )
            self._add_max_check(
                checks,
                key="llm.avg-response-first-audio-ms",
                actual=metrics.get("avg_response_first_audio_ms"),
                expected=self._cfg_float(
                    "max_avg_llm_response_first_audio_ms",
                    default=self._cfg_float("max_avg_response_first_audio_ms", default=1200.0),
                ),
                details="LLM dialogue should begin audible playback early.",
            )
            self._add_max_check(
                checks,
                key="llm.p95-total-turn-ms",
                actual=metrics.get("p95_total_turn_ms"),
                expected=self._cfg_float(
                    "max_p95_llm_turn_ms",
                    default=self._cfg_float("max_p95_total_turn_ms", default=7000.0),
                ),
                details="Long-tail LLM turns should stay under the premium gate.",
            )
            self._add_min_check(
                checks,
                key="llm.streaming-ratio",
                actual=metrics.get("streaming_ratio"),
                expected=self._cfg_float("min_llm_streaming_ratio", default=0.80),
                details="Most LLM turns should be delivered through live streaming.",
            )

        return checks

    @staticmethod
    def _build_overall_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
        failure_count = 0
        for sample in samples:
            result = str(sample.get("result", "") or "").strip().lower()
            llm_error = str(sample.get("llm_error", "") or "").strip()
            if result in {"error", "failed", "failure"} or llm_error:
                failure_count += 1

        window_size = len(samples)
        return {
            "error_rate": (failure_count / float(window_size)) if window_size else None,
        }

    def _build_voice_metrics(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "avg_wake_latency_ms": self._average(self._metric_values(samples, "wake_latency_ms")),
            "avg_stt_latency_ms": self._average(self._metric_values(samples, "stt_latency_ms")),
            "avg_response_first_audio_ms": self._average(
                self._metric_values(samples, "response_first_audio_ms")
            ),
            "avg_route_to_first_audio_ms": self._average(
                self._metric_values(samples, "route_to_first_audio_ms")
            ),
        }

    def _build_skill_metrics(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "avg_skill_latency_ms": self._average(self._metric_values(samples, "skill_latency_ms")),
            "p95_total_turn_ms": self._percentile(self._metric_values(samples, "total_turn_ms"), 0.95),
        }

    def _build_llm_metrics(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        streaming_count = 0
        for sample in samples:
            if bool(sample.get("response_live_streaming", False)):
                streaming_count += 1

        sample_count = len(samples)
        return {
            "avg_llm_first_chunk_ms": self._average(self._metric_values(samples, "llm_first_chunk_ms")),
            "avg_response_first_audio_ms": self._average(
                self._metric_values(samples, "response_first_audio_ms")
            ),
            "p95_total_turn_ms": self._percentile(self._metric_values(samples, "total_turn_ms"), 0.95),
            "streaming_ratio": (streaming_count / float(sample_count)) if sample_count else None,
        }

    def _is_voice_turn(self, sample: dict[str, Any]) -> bool:
        explicit_flag = sample.get("voice_benchmark_ready")
        if explicit_flag is not None:
            return bool(explicit_flag)

        candidates = [
            sample.get("input_source"),
            sample.get("stt_input_source"),
            sample.get("wake_input_source"),
        ]
        has_voice_source = any(str(value or "").strip().lower() == "voice" for value in candidates)
        if not has_voice_source:
            return False

        has_voice_evidence = any(
            (
                self._safe_float(sample.get("wake_latency_ms", 0.0)) > 0.0,
                self._safe_float(sample.get("stt_latency_ms", 0.0)) > 0.0,
                bool(str(sample.get("wake_source", "") or "").strip()),
                bool(str(sample.get("stt_backend_label", "") or "").strip()),
                bool(str(sample.get("stt_mode", "") or "").strip()),
                bool(str(sample.get("active_phase", "") or "").strip()),
                bool(str(sample.get("capture_profile", "") or "").strip()),
                self._safe_float(sample.get("listen_to_speech_ms", 0.0)) > 0.0,
                self._safe_float(sample.get("speech_to_route_ms", 0.0)) > 0.0,
            )
        )
        return has_voice_evidence

    def _is_llm_turn(self, sample: dict[str, Any]) -> bool:
        reply_source = str(sample.get("response_reply_source", "") or "").strip().lower()
        response_source = str(sample.get("response_source", "") or "").strip().lower()
        dialogue_source = str(sample.get("dialogue_source", "") or "").strip().lower()
        llm_source = str(sample.get("llm_source", "") or "").strip().lower()
        llm_first_chunk_ms = sample.get("llm_first_chunk_ms")

        return any(
            (
                reply_source in self._LLM_SOURCES,
                response_source in self._LLM_SOURCES,
                dialogue_source in self._LLM_SOURCES,
                llm_source in self._LLM_SOURCES,
                llm_first_chunk_ms not in (None, 0, 0.0, ""),
            )
        )

    def _is_skill_turn(self, sample: dict[str, Any]) -> bool:
        if self._is_llm_turn(sample):
            return False
        if bool(sample.get("skill_handled", False)):
            return True

        response_source = str(sample.get("response_source", "") or "").strip().lower()
        if response_source.startswith("action") or response_source.startswith("pending_"):
            return True

        reply_source = str(sample.get("response_reply_source", "") or "").strip().lower()
        return reply_source in {"skill", "action", "builtin"}


    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _metric_values(samples: list[dict[str, Any]], key: str) -> list[float]:
        values: list[float] = []
        for sample in samples:
            try:
                value = float(sample.get(key, 0.0))
            except (TypeError, ValueError):
                continue
            if value > 0.0:
                values.append(value)
        return values

    @staticmethod
    def _average(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / float(len(values))

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None

        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]

        position = max(0.0, min(1.0, float(percentile))) * (len(ordered) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]

        weight = position - lower
        return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at_iso": "",
            "samples": [],
            "summary": {},
        }

    @staticmethod
    def _has_value(value: float | int | str | None) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def _add_max_check(
        self,
        checks: list[BenchmarkThresholdCheck],
        key: str,
        actual: float | None,
        expected: float,
        details: str,
    ) -> None:
        checks.append(
            BenchmarkThresholdCheck(
                key=key,
                ok=self._has_value(actual) and float(actual) <= float(expected),
                actual=round(float(actual), 3) if self._has_value(actual) else None,
                expected=float(expected),
                comparator="<=",
                details=details,
            )
        )

    def _add_min_check(
        self,
        checks: list[BenchmarkThresholdCheck],
        key: str,
        actual: float | int | None,
        expected: float | int,
        details: str,
    ) -> None:
        checks.append(
            BenchmarkThresholdCheck(
                key=key,
                ok=self._has_value(actual) and float(actual) >= float(expected),
                actual=round(float(actual), 3) if self._has_value(actual) else None,
                expected=float(expected),
                comparator=">=",
                details=details,
            )
        )

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {}) if isinstance(self.settings, dict) else {}
        return value if isinstance(value, dict) else {}

    def _cfg_text(self, key: str, default: str) -> str:
        value = self.validation_cfg.get(key, default)
        text = str(value if value is not None else default).strip()
        return text or default

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.validation_cfg.get(key, default))
        except (TypeError, ValueError):
            return int(default)

    def _cfg_float(self, key: str, default: float) -> float:
        try:
            return float(self.validation_cfg.get(key, default))
        except (TypeError, ValueError):
            return float(default)