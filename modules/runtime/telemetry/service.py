from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from modules.runtime.contracts import create_turn_id
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import resolve_optional_path

from .models import TurnBenchmarkSnapshot, TurnBenchmarkSummary, TurnBenchmarkTrace


class TurnBenchmarkService:
    """
    Persistent end-to-end benchmark recorder for NeXa turns.

    The service keeps one active trace in memory, persists completed samples
    to a rolling JSON store, and exposes the latest benchmark snapshot
    directly from memory for fast status/debug access.
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

        self._recent_samples: list[dict[str, Any]] = []
        self._latest_sample_cache: dict[str, Any] = {}
        self._latest_summary_cache: dict[str, Any] = {}

        resolved_path = resolve_optional_path(path)
        if resolved_path is None:
            raise ValueError("Benchmark path cannot be None.")

        self._store = JsonStore(
            path=resolved_path,
            default_factory=self._default_payload,
        )

        if self.enabled and self.persist_turns:
            self._store.ensure_exists()

        if self.enabled:
            self._hydrate_memory_cache()

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
        latency_ms: float = 0.0,
        backend_label: str = "",
    ) -> None:
        if not self.enabled:
            return

        with self._lock:
            self._active_trace = self._new_trace_locked()
            self._active_trace.wake_detected_at_monotonic = time.perf_counter()
            self._active_trace.wake_source = str(source or "wake_gate").strip() or "wake_gate"
            self._active_trace.input_source = str(input_source or "voice").strip() or "voice"
            self._active_trace.wake_input_source = self._active_trace.input_source
            self._active_trace.wake_latency_ms = max(0.0, self._safe_float(latency_ms))
            self._active_trace.wake_backend_label = str(backend_label or source or "").strip()

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
        input_source: str = "voice",
        latency_ms: float = 0.0,
        audio_duration_ms: float = 0.0,
        backend_label: str = "",
        mode: str = "",
        confidence: float = 0.0,
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

            trace.speech_language = str(language or trace.language or "").strip().lower()
            if trace.speech_language and not trace.language:
                trace.language = trace.speech_language
            trace.speech_input_source = str(input_source or trace.input_source or "voice").strip() or "voice"
            trace.speech_latency_ms = max(0.0, self._safe_float(latency_ms))
            trace.speech_audio_duration_ms = max(0.0, self._safe_float(audio_duration_ms))
            trace.speech_backend_label = str(backend_label or "").strip()
            trace.speech_mode = str(mode or phase or trace.speech_mode or "").strip()
            trace.speech_confidence = max(0.0, self._safe_float(confidence))

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
            report_first_audio = self._safe_attr_float(
                response_report,
                "first_audio_started_at_monotonic",
            )
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
                "user_text_preview": trace.user_text
                or self._preview_text(str(telemetry.get("user_text", "") or "")),
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
                "wake_source": str(trace.wake_source or "").strip(),
                "wake_input_source": str(trace.wake_input_source or trace.input_source or "voice").strip() or "voice",
                "wake_latency_ms": self._safe_float(trace.wake_latency_ms) or None,
                "wake_backend_label": str(trace.wake_backend_label or "").strip(),
                "active_phase": str(trace.active_phase or "").strip(),
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
                "llm_first_chunk_ms": self._safe_float(
                    safe_llm.get("first_chunk_latency_ms", 0.0)
                ) or None,
                "llm_total_ms": self._safe_float(
                    safe_llm.get("latency_ms", 0.0)
                ) or None,
                "llm_source": str(safe_llm.get("source", "") or "").strip(),
                "llm_ok": bool(safe_llm.get("ok", False)),
                "llm_error": str(safe_llm.get("error", "") or "").strip(),
                "response_chunks_spoken": int(
                    self._safe_attr_float(response_report, "chunks_spoken")
                ),
                "response_chars": len(str(getattr(response_report, "full_text", "") or "")),
                "response_live_streaming": bool(
                    getattr(response_report, "live_streaming", False)
                ),
                "response_chunk_kinds": list(
                    getattr(response_report, "chunk_kinds", []) or []
                ),
                "response_source": str(telemetry.get("response_source", "") or "").strip(),
                "response_reply_source": str(telemetry.get("response_reply_source", "") or "").strip(),
                "response_display_title": str(telemetry.get("response_display_title", "") or "").strip(),
                "response_stream_mode": str(telemetry.get("response_stream_mode", "") or "").strip(),
                "action_name": str(telemetry.get("action_name", "") or "").strip(),
                "action_source": str(telemetry.get("action_source", "") or "").strip(),
                "action_confidence": self._safe_float(telemetry.get("action_confidence", 0.0)) or None,
                "skill_action": str(telemetry.get("skill_action", "") or "").strip(),
                "skill_status": str(telemetry.get("skill_status", "") or "").strip(),
                "skill_handled": bool(telemetry.get("skill_handled", False)),
                "skill_response_delivered": bool(telemetry.get("skill_response_delivered", False)),
                "skill_source": str(telemetry.get("skill_source", "") or "").strip(),
                "skill_latency_ms": self._safe_float(telemetry.get("skill_latency_ms", 0.0)) or None,
                "skill_response_kind": str(telemetry.get("skill_response_kind", "") or "").strip(),
                "dialogue_status": str(telemetry.get("dialogue_status", "") or "").strip(),
                "dialogue_delivered": bool(telemetry.get("dialogue_delivered", False)),
                "dialogue_source": str(telemetry.get("dialogue_source", "") or "").strip(),
                "dialogue_reply_mode": str(telemetry.get("dialogue_reply_mode", "") or "").strip(),
                "pending_consumed_by": str(telemetry.get("pending_consumed_by", "") or "").strip(),
                "pending_kind": str(telemetry.get("pending_kind", "") or "").strip(),
                "pending_type": str(telemetry.get("pending_type", "") or "").strip(),
                "pending_language": str(telemetry.get("pending_language", "") or "").strip().lower(),
                "pending_keeps_state": bool(telemetry.get("pending_keeps_state", False)),
                "pending_metadata": dict(telemetry.get("pending_metadata", {}) or {}),
                "route_notes": list(telemetry.get("route_notes", []) or []),
                "stt_input_source": str(trace.speech_input_source or trace.input_source or "voice").strip() or "voice",
                "stt_language": str(trace.speech_language or trace.language or "").strip().lower(),
                "stt_latency_ms": self._safe_float(trace.speech_latency_ms) or None,
                "stt_audio_duration_ms": self._safe_float(trace.speech_audio_duration_ms) or None,
                "stt_backend_label": str(trace.speech_backend_label or "").strip(),
                "stt_mode": str(trace.speech_mode or trace.active_phase or "").strip(),
                "stt_confidence": self._safe_float(trace.speech_confidence) or None,
                "resume_policy": {},
                "command_window_policy": {},
                "total_turn_ms": total_turn_ms or None,
            }

            self._append_sample_in_memory_locked(sample)

            if self.persist_turns:
                self._store.update(
                    lambda payload: self._append_sample_payload(payload, sample)
                )

            self._active_trace = TurnBenchmarkTrace()
            return dict(sample)


    def annotate_last_completed_turn(
        self,
        *,
        resume_policy: dict[str, Any] | None = None,
        command_window_policy: dict[str, Any] | None = None,
    ) -> bool:
        if not self.enabled:
            return False

        updated = False
        with self._lock:
            if not self._latest_sample_cache:
                return False

            sample = dict(self._latest_sample_cache)
            if isinstance(resume_policy, dict) and resume_policy:
                sample["resume_policy"] = dict(resume_policy)
                updated = True
            if isinstance(command_window_policy, dict) and command_window_policy:
                sample["command_window_policy"] = dict(command_window_policy)
                updated = True

            if not updated:
                return False

            self._latest_sample_cache = dict(sample)
            if self._recent_samples:
                self._recent_samples[-1] = dict(sample)
            if self.persist_turns:
                self._store.update(
                    lambda payload: self._update_last_sample_payload(payload, sample)
                )
            self._latest_summary_cache = self._build_summary(self._recent_samples)
            return True


    def latest_sample(self) -> dict[str, Any]:
        if not self.enabled:
            return {}

        with self._lock:
            return dict(self._latest_sample_cache)

    def latest_summary(self) -> dict[str, Any]:
        if not self.enabled:
            return {}

        with self._lock:
            return dict(self._latest_summary_cache)

    def latest_snapshot(self) -> dict[str, Any]:
        if not self.enabled:
            return {}

        with self._lock:
            snapshot = TurnBenchmarkSnapshot(
                latest_sample=dict(self._latest_sample_cache),
                summary=dict(self._latest_summary_cache),
                overlay_lines=self._build_overlay_lines(
                    latest_sample=self._latest_sample_cache,
                    summary=self._latest_summary_cache,
                ),
            )
            return snapshot.to_dict()

    def _hydrate_memory_cache(self) -> None:
        with self._lock:
            if not self.persist_turns:
                self._recent_samples = []
                self._latest_sample_cache = {}
                self._latest_summary_cache = {}
                return

            result = self._store.read_result()
            payload = result.value if isinstance(result.value, dict) else {}
            samples = list(payload.get("samples", []) or [])
            if len(samples) > self.max_samples:
                samples = samples[-self.max_samples :]

            self._recent_samples = [dict(item) for item in samples if isinstance(item, dict)]
            self._latest_sample_cache = dict(self._recent_samples[-1]) if self._recent_samples else {}

            summary = payload.get("summary", {})
            if isinstance(summary, dict) and summary:
                self._latest_summary_cache = dict(summary)
            else:
                self._latest_summary_cache = self._build_summary(self._recent_samples)

    def _append_sample_in_memory_locked(self, sample: dict[str, Any]) -> None:
        self._recent_samples.append(dict(sample))
        if len(self._recent_samples) > self.max_samples:
            self._recent_samples = self._recent_samples[-self.max_samples :]

        self._latest_sample_cache = dict(sample)
        self._latest_summary_cache = self._build_summary(self._recent_samples)

    def _append_sample_payload(
        self,
        payload: dict[str, Any] | None,
        sample: dict[str, Any],
    ) -> dict[str, Any]:
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

    def _update_last_sample_payload(
        self,
        payload: dict[str, Any] | None,
        sample: dict[str, Any],
    ) -> dict[str, Any]:
        data = dict(payload or {})
        samples = [dict(item) for item in list(data.get("samples", []) or []) if isinstance(item, dict)]
        if samples:
            samples[-1] = dict(sample)
        else:
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
            avg_route_to_first_audio_ms=self._average_metric(window, "route_to_first_audio_ms"),
            avg_llm_first_chunk_ms=self._average_metric(window, "llm_first_chunk_ms"),
            avg_llm_total_ms=self._average_metric(window, "llm_total_ms"),
            last_turn_id=str(latest.get("turn_id", "") or "").strip(),
            last_result=str(latest.get("result", "") or "").strip(),
            last_total_turn_ms=self._safe_float(latest.get("total_turn_ms", 0.0)) or None,
        )
        return summary.to_dict()

    def _build_overlay_lines(
        self,
        *,
        latest_sample: dict[str, Any],
        summary: dict[str, Any],
    ) -> list[str]:
        if not latest_sample and not summary:
            return []

        last_turn_ms = self._metric_compact(latest_sample.get("total_turn_ms"))
        avg_audio_ms = self._metric_compact(summary.get("avg_response_first_audio_ms"))
        avg_llm_ms = self._metric_compact(summary.get("avg_llm_first_chunk_ms"))

        return [
            f"turn:{last_turn_ms} audio:{avg_audio_ms}",
            f"llm:{avg_llm_ms} result:{str(latest_sample.get('result', '-') or '-')[:6]}",
        ]

    @staticmethod
    def _metric_compact(value: Any) -> str:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return "n/a"

        if parsed <= 0.0:
            return "n/a"
        return f"{int(round(parsed))}ms"

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

    @staticmethod
    def _new_trace_locked() -> TurnBenchmarkTrace:
        return TurnBenchmarkTrace(turn_id=create_turn_id("bench"))

    @staticmethod
    def _preview_text(text: str, *, max_chars: int = 140) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return f"{cleaned[: max_chars - 3].rstrip()}..."

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