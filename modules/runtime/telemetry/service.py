from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from cbor2 import value

from modules.runtime.contracts import create_turn_id
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import resolve_optional_path

from .models import TurnBenchmarkSummary, TurnBenchmarkTrace


class TurnBenchmarkService:
    """
    Persistent end-to-end benchmark recorder for NeXa turns.

    The service keeps one active trace in memory and writes completed
    turn samples to a rolling JSON store.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        persist_turns: bool = True,
        path: str = "var/data/turn_benchmarks.json",
        max_samples: int = 300,
        summary_window: int = 30,
    ) -> None:
        self.enabled = bool(enabled)
        self.persist_turns = bool(persist_turns)
        self.max_samples = max(20, int(max_samples))
        self.summary_window = max(5, int(summary_window))
        self._lock = threading.RLock()
        self._active_trace = TurnBenchmarkTrace()

        resolved_path = resolve_optional_path(path)
        if resolved_path is None:
            raise ValueError("Benchmark path cannot be None.")

        self._store = JsonStore(
            path=resolved_path,
            default_factory=self._default_payload,
        )

        if self.enabled and self.persist_turns:
            self._store.ensure_exists()

    def begin_turn(
        self,
        *,
        user_text: str,
        language: str,
        input_source: str = "voice",
    ) -> str:
        if not self.enabled:
            return ""

        with self._lock:
            trace = self._ensure_active_trace_locked()
            trace.user_text = self._preview_text(user_text)
            trace.language = str(language or trace.language or "").strip().lower()
            trace.input_source = str(input_source or trace.input_source or "voice").strip() or "voice"

            if trace.turn_started_at_monotonic <= 0.0:
                trace.turn_started_at_monotonic = (
                    trace.wake_detected_at_monotonic or time.perf_counter()
                )

            return trace.turn_id

    def note_wake_detected(
        self,
        *,
        source: str,
        input_source: str = "voice",
        latency_ms: float | None = None,
        backend_label: str = "",
    ) -> None:
        if not self.enabled:
            return

        with self._lock:
            self._active_trace = self._new_trace_locked()
            self._active_trace.wake_detected_at_monotonic = time.perf_counter()
            self._active_trace.wake_source = str(source or "wake_gate").strip() or "wake_gate"
            self._active_trace.input_source = (
                str(input_source or "voice").strip().lower() or "voice"
            )
            self._active_trace.wake_backend = str(
                backend_label or self._active_trace.wake_source
            ).strip()
            self._active_trace.wake_latency_ms = self._optional_float(latency_ms)

    def note_listening_started(self, *, phase: str) -> None:
        if not self.enabled:
            return

        with self._lock:
            trace = self._ensure_active_trace_locked()
            if trace.listening_started_at_monotonic <= 0.0:
                trace.listening_started_at_monotonic = time.perf_counter()
            trace.active_phase = str(phase or trace.active_phase or "command").strip() or "command"

    def note_speech_finalized(
        self,
        *,
        text: str,
        phase: str,
        language: str = "",
        input_source: str = "",
        latency_ms: float | None = None,
        audio_duration_ms: float | None = None,
        backend_label: str = "",
        mode: str = "",
        confidence: float | None = None,
    ) -> None:
        if not self.enabled:
            return

        with self._lock:
            trace = self._ensure_active_trace_locked()
            if trace.speech_finalized_at_monotonic <= 0.0:
                trace.speech_finalized_at_monotonic = time.perf_counter()

            if not trace.user_text:
                trace.user_text = self._preview_text(text)

            if phase:
                trace.active_phase = str(phase).strip() or trace.active_phase

            if language:
                trace.language = str(language).strip().lower()

            if input_source:
                trace.input_source = str(input_source).strip().lower() or trace.input_source

            if backend_label:
                trace.stt_backend = str(backend_label).strip()

            if mode:
                trace.stt_mode = str(mode).strip()

            trace.stt_latency_ms = self._optional_float(latency_ms)
            trace.speech_duration_ms = self._optional_float(audio_duration_ms)
            trace.stt_confidence = self._optional_float(confidence)

    def note_route_resolved(
        self,
        *,
        route_kind: str,
        primary_intent: str,
        confidence: float,
    ) -> None:
        if not self.enabled:
            return

        with self._lock:
            trace = self._ensure_active_trace_locked()
            trace.route_resolved_at_monotonic = time.perf_counter()
            trace.route_kind = str(route_kind or trace.route_kind or "").strip()
            trace.primary_intent = str(primary_intent or trace.primary_intent or "").strip()
            trace.route_confidence = float(confidence or 0.0)

    def finish_turn(
        self,
        *,
        telemetry: dict[str, Any],
        llm_snapshot: dict[str, Any] | None,
        response_report: Any | None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}

        with self._lock:
            trace = self._ensure_active_trace_locked()
            finished_at_monotonic = time.perf_counter()

            total_turn_ms = self._safe_float(telemetry.get("total_ms", 0.0))
            if total_turn_ms <= 0.0 and trace.turn_started_at_monotonic > 0.0:
                total_turn_ms = max(
                    0.0,
                    (finished_at_monotonic - trace.turn_started_at_monotonic) * 1000.0,
                )

            report_started = self._safe_attr_float(response_report, "started_at_monotonic")
            report_first_audio = self._safe_attr_float(response_report, "first_audio_started_at_monotonic")
            report_finished = self._safe_attr_float(response_report, "finished_at_monotonic")
            response_first_audio_ms = self._safe_attr_float(response_report, "first_audio_latency_ms")
            response_total_ms = self._safe_attr_float(response_report, "total_elapsed_ms")

            if report_finished <= 0.0:
                report_finished = finished_at_monotonic

            if response_total_ms <= 0.0 and report_started > 0.0:
                response_total_ms = max(0.0, (report_finished - report_started) * 1000.0)

            if report_first_audio <= 0.0 and report_started > 0.0 and response_first_audio_ms > 0.0:
                report_first_audio = report_started + (response_first_audio_ms / 1000.0)

            safe_llm = dict(llm_snapshot or {})

            sample = {
                "turn_id": str(telemetry.get("benchmark_turn_id") or trace.turn_id or "").strip(),
                "created_at_iso": self._now_iso(),
                "input_source": str(
                    telemetry.get("input_source") or trace.input_source or "voice"
                ).strip() or "voice",
                "language": str(
                    telemetry.get("language") or trace.language or ""
                ).strip().lower(),
                "user_text_preview": trace.user_text or self._preview_text(str(telemetry.get("user_text", "") or "")),
                "result": str(telemetry.get("result", "") or "").strip(),
                "handled": bool(telemetry.get("handled", False)),
                "route_kind": str(
                    telemetry.get("route_kind") or trace.route_kind or ""
                ).strip(),
                "route_confidence": self._safe_float(
                    telemetry.get("route_confidence", trace.route_confidence)
                ),
                "primary_intent": str(
                    telemetry.get("primary_intent") or trace.primary_intent or ""
                ).strip(),
                "topics": list(telemetry.get("topics", []) or []),
                "route_notes": list(telemetry.get("route_notes", []) or []),
                "route_metadata": dict(telemetry.get("route_metadata", {}) or {}),
                "wake_source": str(trace.wake_source or "").strip(),
                "active_phase": str(trace.active_phase or "").strip(),
                "capture_phase": str(
                    telemetry.get("capture_phase") or trace.active_phase or ""
                ).strip(),
                "capture_mode": str(
                    telemetry.get("stt_mode") or telemetry.get("capture_mode") or ""
                ).strip(),
                "capture_backend": str(
                    telemetry.get("stt_backend") or telemetry.get("capture_backend") or ""
                ).strip(),
                "wake_latency_ms": self._optional_float(trace.wake_latency_ms),
                "active_phase": str(trace.active_phase or "").strip(),
                "stt_backend": str(
                    telemetry.get("stt_backend") or trace.stt_backend or ""
                ).strip(),
                "stt_mode": str(
                    telemetry.get("stt_mode") or trace.stt_mode or ""
                ).strip(),
                "stt_phase": str(
                    telemetry.get("stt_phase") or trace.active_phase or ""
                ).strip(),
                "stt_latency_ms": self._optional_float(
                    telemetry.get("stt_latency_ms", trace.stt_latency_ms)
                ),
                "stt_audio_duration_ms": self._optional_float(
                    telemetry.get("stt_audio_duration_ms", trace.speech_duration_ms)
                ),
                "stt_confidence": self._optional_float(
                    telemetry.get("stt_confidence", trace.stt_confidence)
                ) or None,
                "wake_to_listen_ms": self._delta_ms(
                    trace.wake_detected_at_monotonic,
                    trace.listening_started_at_monotonic,
                ),
                "listen_to_speech_ms": self._delta_ms(
                    trace.listening_started_at_monotonic,
                    trace.speech_finalized_at_monotonic,
                ),
                "speech_to_route_ms": self._delta_ms(
                    trace.speech_finalized_at_monotonic,
                    trace.route_resolved_at_monotonic,
                ),
                "route_to_response_start_ms": self._delta_ms(
                    trace.route_resolved_at_monotonic,
                    report_started,
                ),
                "route_to_first_audio_ms": self._delta_ms(
                    trace.route_resolved_at_monotonic,
                    report_first_audio,
                ),
                "response_first_audio_ms": response_first_audio_ms or None,
                "response_total_ms": response_total_ms or None,
                "llm_first_chunk_ms": self._optional_float(
                    safe_llm.get("first_chunk_latency_ms")
                    or getattr(response_report, "first_chunk_latency_ms", 0.0)
                ),
                "llm_total_ms": self._safe_float(
                    safe_llm.get("latency_ms", 0.0)
                ) or None,
                "llm_source": str(safe_llm.get("source", "") or "").strip(),
                "llm_ok": bool(safe_llm.get("ok", False)),
                "llm_error": str(safe_llm.get("error", "") or "").strip(),
                "response_chunks_spoken": int(self._safe_attr_float(response_report, "chunks_spoken")),
                "response_chars": len(str(getattr(response_report, "full_text", "") or "")),
                "response_live_streaming": bool(getattr(response_report, "live_streaming", False)),
                "response_first_chunk_ms": self._optional_float(
                    getattr(response_report, "first_chunk_latency_ms", 0.0)
                ),
                "response_first_sentence_ms": self._optional_float(
                    getattr(response_report, "first_sentence_latency_ms", 0.0)
                ),
                "response_chunk_kinds": list(getattr(response_report, "chunk_kinds", []) or []),
                "response_source": str(telemetry.get("response_source", "") or "").strip(),
                "response_reply_source": str(telemetry.get("response_reply_source", "") or "").strip(),
                "response_display_title": str(telemetry.get("response_display_title", "") or "").strip(),
                "response_stream_mode": str(telemetry.get("response_stream_mode", "") or "").strip(),
                "response_memory_metadata": dict(
                    telemetry.get("response_memory_metadata", {}) or {}
                ),
                "action_name": str(telemetry.get("action_name", "") or "").strip(),
                "action_source": str(telemetry.get("action_source", "") or "").strip(),
                "action_confidence": self._optional_float(
                    telemetry.get("action_confidence", None)
                ),
                "total_turn_ms": total_turn_ms or None,
            }

            if self.persist_turns:
                self._store.update(lambda payload: self._append_sample(payload, sample))

            self._active_trace = TurnBenchmarkTrace()
            return sample

    def latest_summary(self) -> dict[str, Any]:
        if not self.enabled or not self.persist_turns:
            return {}

        result = self._store.read_result()
        if not isinstance(result.value, dict):
            return {}

        return dict(result.value.get("summary", {}) or {})

    def _append_sample(self, payload: dict[str, Any] | None, sample: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload or {})
        samples = list(data.get("samples", []) or [])
        samples.append(dict(sample))

        if len(samples) > self.max_samples:
            samples = samples[-self.max_samples :]

        data.update(
            {
                "version": 1,
                "updated_at_iso": self._now_iso(),
                "samples": samples,
                "summary": self._build_summary(samples),
            }
        )
        return data

    def _build_summary(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        window = samples[-self.summary_window :] if samples else []
        latest = samples[-1] if samples else {}

        summary = TurnBenchmarkSummary(
            sample_count=len(samples),
            window_size=len(window),
            avg_total_turn_ms=self._average_metric(window, "total_turn_ms"),
            avg_response_first_audio_ms=self._average_metric(window, "response_first_audio_ms"),
            avg_response_first_chunk_ms=self._average_metric(window, "response_first_chunk_ms"),
            avg_response_first_sentence_ms=self._average_metric(window, "response_first_sentence_ms"),
            avg_route_to_first_audio_ms=self._average_metric(window, "route_to_first_audio_ms"),
            avg_llm_first_chunk_ms=self._average_metric(window, "llm_first_chunk_ms"),
            avg_llm_total_ms=self._average_metric(window, "llm_total_ms"),
            last_turn_id=str(latest.get("turn_id", "") or "").strip(),
            last_result=str(latest.get("result", "") or "").strip(),
            last_total_turn_ms=self._safe_float(latest.get("total_turn_ms", 0.0)) or None,
        )
        return summary.to_dict()

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at_iso": "",
            "samples": [],
            "summary": {},
        }

    def _ensure_active_trace_locked(self) -> TurnBenchmarkTrace:
        if not self._active_trace.turn_id:
            self._active_trace = self._new_trace_locked()
        return self._active_trace

    def _new_trace_locked(self) -> TurnBenchmarkTrace:
        return TurnBenchmarkTrace(turn_id=create_turn_id("bench"))

    @staticmethod
    def _preview_text(text: str, *, max_chars: int = 140) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return f"{cleaned[: max_chars - 3].rstrip()}..."



    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _safe_attr_float(cls, value: Any, name: str) -> float:
        try:
            return cls._safe_float(getattr(value, name, 0.0))
        except Exception:
            return 0.0

    @classmethod
    def _delta_ms(cls, started_at: float, ended_at: float) -> float | None:
        if cls._safe_float(started_at) <= 0.0 or cls._safe_float(ended_at) <= 0.0:
            return None

        delta_ms = (float(ended_at) - float(started_at)) * 1000.0
        if delta_ms < 0.0:
            return None
        return delta_ms

    @classmethod
    def _average_metric(cls, samples: list[dict[str, Any]], key: str) -> float | None:
        values = [cls._safe_float(item.get(key, 0.0)) for item in samples]
        filtered = [value for value in values if value > 0.0]
        if not filtered:
            return None
        return sum(filtered) / float(len(filtered))

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = ["TurnBenchmarkService"]