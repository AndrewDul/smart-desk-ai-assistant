from __future__ import annotations

import time

from typing import Any

from modules.core.calculator.simple_arithmetic import evaluate_arithmetic_expression
from modules.presentation.status_debug_presenter.service import StatusDebugPresenterService
from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction, SkillRequest, SkillResult


class ActionSystemActionsMixin:
    def _status_debug_presenter(self) -> StatusDebugPresenterService:
        presenter = getattr(self, "_status_debug_presenter_service", None)
        if presenter is None:
            presenter = StatusDebugPresenterService()
            self._status_debug_presenter_service = presenter
        return presenter

    def _runtime_snapshot(self) -> dict[str, Any]:
        assistant = getattr(self, "assistant", None)

        snapshot_method = getattr(assistant, "_runtime_status_snapshot", None)
        if callable(snapshot_method):
            try:
                snapshot = snapshot_method()
                return dict(snapshot or {}) if isinstance(snapshot, dict) else {}
            except Exception:
                return {}

        runtime_product = getattr(assistant, "runtime_product", None)
        snapshot_method = getattr(runtime_product, "snapshot", None)
        if callable(snapshot_method):
            try:
                snapshot = snapshot_method()
                return dict(snapshot or {}) if isinstance(snapshot, dict) else {}
            except Exception:
                return {}

        return {}

    def _audio_runtime_snapshot(self) -> dict[str, Any]:
        assistant = getattr(self, "assistant", None)

        snapshot_method = getattr(assistant, "_audio_runtime_snapshot", None)
        if callable(snapshot_method):
            try:
                snapshot = snapshot_method()
                return dict(snapshot or {}) if isinstance(snapshot, dict) else {}
            except Exception:
                return {}

        payload = getattr(assistant, "_last_audio_runtime_snapshot", {}) or {}
        return dict(payload or {}) if isinstance(payload, dict) else {}
    def _runtime_debug_snapshot(self) -> dict[str, Any]:
        assistant = getattr(self, "assistant", None)
        service = getattr(assistant, "runtime_debug_snapshot_service", None)

        snapshot_method = getattr(service, "snapshot", None)
        if callable(snapshot_method):
            try:
                payload = snapshot_method()
                return dict(payload or {}) if isinstance(payload, dict) else {}
            except Exception:
                pass

        runtime_snapshot = self._runtime_snapshot()
        benchmark_snapshot = self._benchmark_snapshot()
        audio_snapshot = self._audio_runtime_snapshot()
        latest_sample = dict(benchmark_snapshot.get("latest_sample", {}) or {})
        summary = dict(benchmark_snapshot.get("summary", {}) or {})
        completed_turn_trace = self._completed_turn_trace(latest_sample)

        return {
            "runtime_snapshot": runtime_snapshot,
            "benchmark_snapshot": benchmark_snapshot,
            "audio_runtime_snapshot": audio_snapshot,
            "runtime_label": "",
            "llm_label": "",
            "wake_backend": self._backend_token(runtime_snapshot, "wake_gate"),
            "stt_backend": self._backend_token(runtime_snapshot, "voice_input"),
            "llm_backend": self._backend_token(runtime_snapshot, "llm"),
            "last_turn_ms": self._safe_metric_float(latest_sample.get("total_turn_ms")),
            "avg_response_first_audio_ms": self._safe_metric_float(
                summary.get("avg_response_first_audio_ms")
            ),
            "avg_llm_first_chunk_ms": self._safe_metric_float(
                summary.get("avg_llm_first_chunk_ms")
            ),
            "completed_turn_trace": completed_turn_trace,
            "completed_turn_lines": self._completed_turn_trace_lines("en", completed_turn_trace),
            "audio_lines": self._audio_debug_lines("en", audio_snapshot),
            "audio_overlay_line": "",
            "developer_overlay_lines": [
                str(item).strip()
                for item in benchmark_snapshot.get("overlay_lines", [])
                if str(item).strip()
            ],
        }
    def _benchmark_snapshot(self) -> dict[str, Any]:
        assistant = getattr(self, "assistant", None)
        service = getattr(assistant, "turn_benchmark_service", None)

        latest_snapshot = getattr(service, "latest_snapshot", None)
        if callable(latest_snapshot):
            try:
                payload = latest_snapshot()
                return dict(payload or {}) if isinstance(payload, dict) else {}
            except Exception:
                return {}

        latest_summary = getattr(service, "latest_summary", None)
        if callable(latest_summary):
            try:
                summary = latest_summary()
            except Exception:
                summary = {}
            return {
                "latest_sample": {},
                "summary": dict(summary or {}) if isinstance(summary, dict) else {},
                "overlay_lines": [],
            }

        return {}

    def _benchmark_summary(self) -> dict[str, Any]:
        assistant = getattr(self, "assistant", None)
        service = getattr(assistant, "turn_benchmark_service", None)
        latest_summary = getattr(service, "latest_summary", None)
        if not callable(latest_summary):
            return {}

        try:
            payload = latest_summary()
        except Exception:
            return {}

        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _last_llm_generation_snapshot(self) -> dict[str, Any]:
        assistant = getattr(self, "assistant", None)
        dialogue = getattr(assistant, "dialogue", None)
        local_llm = getattr(dialogue, "local_llm", None)

        snapshot_method = getattr(local_llm, "last_generation_snapshot", None)
        if not callable(snapshot_method):
            return {}

        try:
            payload = snapshot_method()
        except Exception:
            return {}

        return dict(payload or {}) if isinstance(payload, dict) else {}

    @staticmethod
    def _runtime_service_payload(snapshot: dict[str, Any], component: str) -> dict[str, Any]:
        services = snapshot.get("services", {})
        if not isinstance(services, dict):
            return {}

        payload = services.get(component, {})
        return dict(payload or {}) if isinstance(payload, dict) else {}

    @staticmethod
    def _runtime_named_components(
        snapshot: dict[str, Any],
        key: str,
        *,
        fallback_states: tuple[str, ...] = (),
        compatibility_only: bool = False,
    ) -> list[str]:
        direct = [
            str(item).strip()
            for item in snapshot.get(key, [])
            if str(item).strip()
        ]
        if direct:
            return direct

        services = snapshot.get("services", {})
        if not isinstance(services, dict):
            return []

        names: list[str] = []
        for name, payload in services.items():
            if not isinstance(payload, dict):
                continue

            if compatibility_only and bool(payload.get("compatibility_mode", False)):
                names.append(str(name))
                continue

            state = str(payload.get("state", "") or "").strip().lower()
            if fallback_states and state in fallback_states:
                names.append(str(name))

        return names

    def _fallback_backend_name(self, component: str) -> str:
        assistant = getattr(self, "assistant", None)
        backend_statuses = getattr(assistant, "backend_statuses", {}) or {}
        payload = backend_statuses.get(component)
        if payload is None:
            return "n/a"

        selected = str(getattr(payload, "selected_backend", "") or "").strip()
        return selected or "n/a"

    def _backend_token(self, snapshot: dict[str, Any], component: str) -> str:
        payload = self._runtime_service_payload(snapshot, component)

        raw = str(
            payload.get("backend")
            or payload.get("selected_backend")
            or payload.get("requested_backend")
            or self._fallback_backend_name(component)
            or "n/a"
        ).strip().lower()

        aliases = {
            "compatibility_voice_input": "compat",
            "faster_whisper": "faster",
            "whisper_cpp": "whisper",
            "openwakeword": "oww",
            "hailo-ollama": "hailo",
            "llama-cli": "llama-cli",
            "text_input": "text",
            "disabled": "off",
            "unknown": "n/a",
            "waveshare_2inch": "waveshare",
        }

        normalized = aliases.get(raw, raw or "n/a")
        return normalized[:14]

    @staticmethod
    def _safe_metric_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0.0:
            return None
        return parsed

    def _metric_phrase(self, value_ms: float | None, language: str) -> str:
        if value_ms is None:
            return "brak" if language == "pl" else "n/a"

        rounded = int(round(float(value_ms)))
        if language == "pl":
            return f"{rounded} milisekund"
        return f"{rounded} milliseconds"

    def _metric_display(self, value_ms: float | None) -> str:
        if value_ms is None:
            return "n/a"
        return f"{int(round(float(value_ms)))}ms"

    def _runtime_state_phrase(self, snapshot: dict[str, Any], language: str) -> str:
        ready = bool(snapshot.get("ready", False))
        degraded = bool(snapshot.get("degraded", False))
        lifecycle = str(snapshot.get("lifecycle_state", "") or "").strip().lower()

        if language == "pl":
            if ready:
                return "gotowy"
            if degraded or lifecycle == "degraded":
                return "ograniczony"
            if lifecycle == "booting":
                return "uruchamiany"
            return "pośredni"

        if ready:
            return "ready"
        if degraded or lifecycle == "degraded":
            return "limited"
        if lifecycle == "booting":
            return "booting"
        return "intermediate"

    @staticmethod
    def _audio_token(value: Any, max_chars: int = 14) -> str:
        compact = " ".join(str(value or "n/a").split()).strip().lower() or "n/a"
        return compact[:max_chars]

    def _audio_debug_lines(self, language: str, audio_snapshot: dict[str, Any]) -> list[str]:
        return self._status_debug_presenter().audio_debug_lines(language, audio_snapshot)

    def _audio_debug_phrase(self, language: str, audio_snapshot: dict[str, Any]) -> str:
        return self._status_debug_presenter().audio_debug_phrase(language, audio_snapshot)

    def _completed_turn_trace(self, latest_sample: dict[str, Any]) -> dict[str, Any]:
        sample = dict(latest_sample or {})
        resume_policy = dict(sample.get("resume_policy", {}) or {})
        command_window_policy = dict(sample.get("command_window_policy", {}) or {})
        return {
            "route_kind": str(sample.get("route_kind", "") or "").strip(),
            "result": str(sample.get("result", "") or "").strip(),
            "resume_action": str(resume_policy.get("action", "") or "").strip(),
            "resume_reason": str(resume_policy.get("reason", "") or "").strip(),
            "command_action": str(command_window_policy.get("action", "") or "").strip(),
            "command_reason": str(command_window_policy.get("reason", "") or "").strip(),
            "command_phase": str(command_window_policy.get("phase", "") or "").strip(),
            "stt_mode": str(sample.get("stt_mode", "") or "").strip(),
            "stt_latency_ms": self._safe_metric_float(sample.get("stt_latency_ms")),
            "wake_latency_ms": self._safe_metric_float(sample.get("wake_latency_ms")),
        }

    def _completed_turn_trace_phrase(self, language: str, trace: dict[str, Any]) -> str:
        return self._status_debug_presenter().completed_turn_trace_phrase(language, trace)

    def _completed_turn_trace_lines(self, language: str, trace: dict[str, Any]) -> list[str]:
        return self._status_debug_presenter().completed_turn_trace_lines(language, trace)

    def _benchmark_overview_phrase(self, language: str, metadata: dict[str, Any]) -> str:
        benchmark_snapshot = dict(metadata.get("benchmark_snapshot", {}) or {})
        latest_sample = dict(benchmark_snapshot.get("latest_sample", {}) or {})
        summary = dict(benchmark_snapshot.get("summary", {}) or {})

        if not latest_sample and not summary:
            return self._localized(
                language,
                "Nie mam jeszcze benchmarków ostatnich turnów.",
                "I do not have benchmark data for recent turns yet.",
            )

        last_turn_ms = self._safe_metric_float(latest_sample.get("total_turn_ms"))
        avg_audio_ms = self._safe_metric_float(summary.get("avg_response_first_audio_ms"))
        avg_llm_first_chunk_ms = self._safe_metric_float(summary.get("avg_llm_first_chunk_ms"))
        completed_turn_trace = dict(metadata.get("completed_turn_trace", {}) or {})

        trace_available = any(
            str(completed_turn_trace.get(key, "") or "").strip()
            for key in ("route_kind", "result", "resume_action", "command_action")
        )
        trace_phrase = (
            self._completed_turn_trace_phrase(language, completed_turn_trace)
            if trace_available
            else ""
        )

        if language == "pl":
            phrase = (
                f"Ostatni pełny turn trwał {self._metric_phrase(last_turn_ms, language)}. "
                f"Średni start głosu to {self._metric_phrase(avg_audio_ms, language)}, "
                f"a średni pierwszy chunk LLM to {self._metric_phrase(avg_llm_first_chunk_ms, language)}."
            )
        else:
            phrase = (
                f"The latest full turn took {self._metric_phrase(last_turn_ms, language)}. "
                f"Average voice start is {self._metric_phrase(avg_audio_ms, language)}, "
                f"and average LLM first chunk is {self._metric_phrase(avg_llm_first_chunk_ms, language)}."
            )

        if trace_phrase:
            phrase = f"{phrase} {trace_phrase}"
        return phrase.strip()

    def _debug_status_lines(self, language: str, metadata: dict[str, Any]) -> list[str]:
        return self._status_debug_presenter().debug_status_lines(language, metadata)

    def _build_runtime_benchmark_summary(
        self,
        language: str,
    ) -> tuple[str, list[str], dict[str, Any]]:
        debug_snapshot = self._runtime_debug_snapshot()
        runtime_snapshot = dict(debug_snapshot.get("runtime_snapshot", {}) or {})
        benchmark_snapshot = dict(debug_snapshot.get("benchmark_snapshot", {}) or {})
        latest_sample = dict(benchmark_snapshot.get("latest_sample", {}) or {})
        summary = dict(benchmark_snapshot.get("summary", {}) or {})

        runtime_state = self._runtime_state_phrase(runtime_snapshot, language)
        wake_token = str(
            debug_snapshot.get("wake_backend")
            or self._backend_token(runtime_snapshot, "wake_gate")
        )
        stt_token = str(
            debug_snapshot.get("stt_backend")
            or self._backend_token(runtime_snapshot, "voice_input")
        )
        llm_token = str(
            debug_snapshot.get("llm_backend")
            or self._backend_token(runtime_snapshot, "llm")
        )

        last_turn_ms = self._safe_metric_float(debug_snapshot.get("last_turn_ms"))
        if last_turn_ms is None:
            last_turn_ms = self._safe_metric_float(latest_sample.get("total_turn_ms"))

        avg_audio_ms = self._safe_metric_float(
            debug_snapshot.get("avg_response_first_audio_ms")
        )
        if avg_audio_ms is None:
            avg_audio_ms = self._safe_metric_float(summary.get("avg_response_first_audio_ms"))

        avg_llm_first_chunk_ms = self._safe_metric_float(
            debug_snapshot.get("avg_llm_first_chunk_ms")
        )
        if avg_llm_first_chunk_ms is None:
            avg_llm_first_chunk_ms = self._safe_metric_float(
                summary.get("avg_llm_first_chunk_ms")
            )

        completed_turn_trace = dict(
            debug_snapshot.get("completed_turn_trace", {}) or self._completed_turn_trace(latest_sample)
        )
        completed_turn_phrase = self._completed_turn_trace_phrase(language, completed_turn_trace)
        completed_turn_lines = list(
            debug_snapshot.get("completed_turn_lines", [])
            or self._completed_turn_trace_lines(language, completed_turn_trace)
        )

        if language == "pl":
            runtime_part = (
                f"Runtime jest {runtime_state}. "
                f"Wake używa {wake_token}, STT używa {stt_token}, a LLM używa {llm_token}."
            )
            benchmark_part = (
                f" Ostatni pełny turn trwał {self._metric_phrase(last_turn_ms, language)}. "
                f"Średni start głosu to {self._metric_phrase(avg_audio_ms, language)}, "
                f"a średni pierwszy chunk LLM to {self._metric_phrase(avg_llm_first_chunk_ms, language)}. "
                f"{completed_turn_phrase}"
            )
        else:
            runtime_part = (
                f"The runtime is {runtime_state}. "
                f"Wake uses {wake_token}, STT uses {stt_token}, and LLM uses {llm_token}."
            )
            benchmark_part = (
                f" The latest full turn took {self._metric_phrase(last_turn_ms, language)}. "
                f"Average voice start is {self._metric_phrase(avg_audio_ms, language)}, "
                f"and average LLM first chunk is {self._metric_phrase(avg_llm_first_chunk_ms, language)}. "
                f"{completed_turn_phrase}"
            )

        lines = self._localized_lines(
            language,
            [
                f"runtime: {runtime_state}",
                f"wake: {wake_token}",
                f"stt: {stt_token}",
                f"llm: {llm_token}",
                f"turn: {int(round(last_turn_ms))}ms" if last_turn_ms is not None else "turn: n/a",
                f"audio: {int(round(avg_audio_ms))}ms" if avg_audio_ms is not None else "audio: n/a",
            ],
            [
                f"runtime: {runtime_state}",
                f"wake: {wake_token}",
                f"stt: {stt_token}",
                f"llm: {llm_token}",
                f"turn: {int(round(last_turn_ms))}ms" if last_turn_ms is not None else "turn: n/a",
                f"audio: {int(round(avg_audio_ms))}ms" if avg_audio_ms is not None else "audio: n/a",
            ],
        )

        metadata = {
            "runtime_snapshot": runtime_snapshot,
            "benchmark_snapshot": benchmark_snapshot,
            "runtime_state": runtime_state,
            "wake_backend": wake_token,
            "stt_backend": stt_token,
            "llm_backend": llm_token,
            "last_turn_ms": last_turn_ms,
            "avg_response_first_audio_ms": avg_audio_ms,
            "avg_llm_first_chunk_ms": avg_llm_first_chunk_ms,
            "completed_turn_trace": completed_turn_trace,
            "completed_turn_lines": completed_turn_lines,
            "runtime_debug_snapshot": debug_snapshot,
        }

        return f"{runtime_part}{benchmark_part}".strip(), lines, metadata

    def _build_runtime_metrics_summary(
        self,
        language: str,
    ) -> tuple[str, list[str], dict[str, Any]]:
        snapshot = self._runtime_snapshot()
        benchmark = self._benchmark_summary()
        llm_last = self._last_llm_generation_snapshot()

        runtime_state = self._runtime_state_phrase(snapshot, language)
        wake_token = self._backend_token(snapshot, "wake_gate")
        stt_token = self._backend_token(snapshot, "voice_input")
        llm_token = self._backend_token(snapshot, "llm")

        llm_first_chunk_ms = self._safe_metric_float(benchmark.get("avg_llm_first_chunk_ms"))
        response_first_audio_ms = self._safe_metric_float(
            benchmark.get("avg_response_first_audio_ms")
        )
        response_first_sentence_ms = self._safe_metric_float(
            benchmark.get("avg_response_first_sentence_ms")
        )

        status_message = str(snapshot.get("status_message", "") or "").strip()

        if language == "pl":
            runtime_spoken = (
                f"Runtime jest {runtime_state}. "
                f"Wake używa {wake_token}, STT używa {stt_token}, a LLM używa {llm_token}."
            )

            if any(
                value is not None
                for value in (
                    llm_first_chunk_ms,
                    response_first_audio_ms,
                    response_first_sentence_ms,
                )
            ):
                metrics_spoken = (
                    " Średnie metryki odpowiedzi są następujące: "
                    f"pierwszy chunk LLM {self._metric_phrase(llm_first_chunk_ms, language)}, "
                    f"start głosu {self._metric_phrase(response_first_audio_ms, language)}, "
                    f"pierwsze zdanie {self._metric_phrase(response_first_sentence_ms, language)}."
                )
            else:
                metrics_spoken = " Nie mam jeszcze pełnych metryk odpowiedzi."

            if status_message:
                runtime_spoken = f"{runtime_spoken} {status_message}."
        else:
            runtime_spoken = (
                f"The runtime is {runtime_state}. "
                f"Wake uses {wake_token}, STT uses {stt_token}, and LLM uses {llm_token}."
            )

            if any(
                value is not None
                for value in (
                    llm_first_chunk_ms,
                    response_first_audio_ms,
                    response_first_sentence_ms,
                )
            ):
                metrics_spoken = (
                    " Average response metrics are: "
                    f"LLM first chunk {self._metric_phrase(llm_first_chunk_ms, language)}, "
                    f"voice start {self._metric_phrase(response_first_audio_ms, language)}, "
                    f"first sentence {self._metric_phrase(response_first_sentence_ms, language)}."
                )
            else:
                metrics_spoken = " I do not have full response metrics yet."

            if status_message:
                runtime_spoken = f"{runtime_spoken} {status_message}."

        lines = self._localized_lines(
            language,
            [
                f"runtime: {runtime_state}",
                f"wake: {wake_token}",
                f"stt: {stt_token}",
                f"llm: {llm_token}",
                f"ttft: {self._metric_display(llm_first_chunk_ms)}",
                f"voice: {self._metric_display(response_first_audio_ms)}",
            ],
            [
                f"runtime: {runtime_state}",
                f"wake: {wake_token}",
                f"stt: {stt_token}",
                f"llm: {llm_token}",
                f"ttft: {self._metric_display(llm_first_chunk_ms)}",
                f"voice: {self._metric_display(response_first_audio_ms)}",
            ],
        )

        metadata = {
            "runtime_snapshot": snapshot,
            "benchmark_summary": benchmark,
            "llm_last_generation": llm_last,
            "runtime_state": runtime_state,
            "wake_backend": wake_token,
            "stt_backend": stt_token,
            "llm_backend": llm_token,
            "avg_llm_first_chunk_ms": llm_first_chunk_ms,
            "avg_response_first_audio_ms": response_first_audio_ms,
            "avg_response_first_sentence_ms": response_first_sentence_ms,
        }

        return f"{runtime_spoken}{metrics_spoken}".strip(), lines, metadata

    def _build_runtime_status_summary(
        self,
        language: str,
    ) -> tuple[str, list[str], dict[str, Any]]:
        snapshot = self._runtime_snapshot()
        if not snapshot:
            spoken = self._localized(
                language,
                "Nie mam jeszcze pełnego snapshotu runtime, ale podstawowe funkcje asystenta są dostępne.",
                "I do not have a full runtime snapshot yet, but the core assistant features are available.",
            )
            lines = self._localized_lines(
                language,
                ["premium: brak", "core: brak", "wake: n/a", "stt: n/a", "llm: n/a"],
                ["premium: n/a", "core: n/a", "wake: n/a", "stt: n/a", "llm: n/a"],
            )
            return spoken, lines, {"runtime_snapshot_available": False}

        lifecycle_state = str(snapshot.get("lifecycle_state", "unknown") or "unknown").strip().lower()
        premium_ready = bool(snapshot.get("premium_ready", False))
        primary_ready = bool(snapshot.get("primary_ready", snapshot.get("ready", False)))
        status_message = str(snapshot.get("status_message", "") or "").strip()

        compatibility = self._runtime_named_components(
            snapshot,
            "compatibility_components",
            compatibility_only=True,
        )
        degraded_components = self._runtime_named_components(
            snapshot,
            "degraded_components",
            fallback_states=("degraded", "failed"),
        )
        blockers = self._runtime_named_components(
            snapshot,
            "blockers",
            fallback_states=("failed",),
        )

        voice_token = self._backend_token(snapshot, "voice_input")
        wake_token = self._backend_token(snapshot, "wake_gate")
        llm_token = self._backend_token(snapshot, "llm")

        if language == "pl":
            if premium_ready:
                runtime_sentence = "Tryb premium jest gotowy."
            elif primary_ready and compatibility:
                runtime_sentence = (
                    "Rdzeń runtime działa, ale aktywna jest ścieżka kompatybilności dla: "
                    f"{', '.join(compatibility[:2])}."
                )
            elif blockers:
                runtime_sentence = (
                    "Część wymaganych usług wymaga uwagi: "
                    f"{', '.join(blockers[:2])}."
                )
            elif degraded_components:
                runtime_sentence = (
                    "Runtime działa w trybie ograniczonym. "
                    f"Zdegradowane moduły: {', '.join(degraded_components[:2])}."
                )
            else:
                runtime_sentence = "Runtime jest dostępny, ale raportuje stan pośredni."

            backend_sentence = (
                f"Wake używa {wake_token}, STT używa {voice_token}, a LLM używa {llm_token}."
            )
        else:
            if premium_ready:
                runtime_sentence = "Premium mode is ready."
            elif primary_ready and compatibility:
                runtime_sentence = (
                    "The runtime core is ready, but a compatibility path is active for: "
                    f"{', '.join(compatibility[:2])}."
                )
            elif blockers:
                runtime_sentence = (
                    "Some required services need attention: "
                    f"{', '.join(blockers[:2])}."
                )
            elif degraded_components:
                runtime_sentence = (
                    "The runtime is operating in a limited mode. "
                    f"Degraded modules: {', '.join(degraded_components[:2])}."
                )
            else:
                runtime_sentence = "The runtime is available, but it is reporting an intermediate state."

            backend_sentence = (
                f"Wake uses {wake_token}, STT uses {voice_token}, and LLM uses {llm_token}."
            )

        if status_message and lifecycle_state not in {"ready", "degraded"}:
            runtime_sentence = f"{runtime_sentence} {status_message}"

        lines = self._localized_lines(
            language,
            [
                f"premium: {'TAK' if premium_ready else 'NIE'}",
                f"core: {'TAK' if primary_ready else 'NIE'}",
                f"wake: {wake_token}",
                f"stt: {voice_token}",
                f"llm: {llm_token}",
            ],
            [
                f"premium: {'YES' if premium_ready else 'NO'}",
                f"core: {'YES' if primary_ready else 'NO'}",
                f"wake: {wake_token}",
                f"stt: {voice_token}",
                f"llm: {llm_token}",
            ],
        )

        runtime_services = {}
        for component in ("voice_input", "wake_gate", "voice_output", "display", "llm"):
            payload = self._runtime_service_payload(snapshot, component)
            if not payload:
                continue
            runtime_services[component] = {
                "backend": str(payload.get("backend", "") or "").strip(),
                "state": str(payload.get("state", "") or "").strip(),
                "requested_backend": str(payload.get("requested_backend", "") or "").strip(),
                "runtime_mode": str(payload.get("runtime_mode", "") or "").strip(),
                "primary": bool(payload.get("primary", False)),
                "compatibility_mode": bool(payload.get("compatibility_mode", False)),
            }

        metadata = {
            "runtime_snapshot_available": True,
            "runtime_lifecycle_state": lifecycle_state,
            "runtime_status_message": status_message,
            "runtime_primary_ready": primary_ready,
            "runtime_premium_ready": premium_ready,
            "runtime_compatibility_components": compatibility,
            "runtime_degraded_components": degraded_components,
            "runtime_blockers": blockers,
            "runtime_services": runtime_services,
        }

        return f"{runtime_sentence} {backend_sentence}".strip(), lines, metadata

    def _show_visual_help_overlay(self, *, language: str) -> None:
        assistant = getattr(self, "assistant", None)
        if assistant is None:
            return

        fast_command_lane = getattr(assistant, "fast_command_lane", None)
        visual_shell_lane = getattr(fast_command_lane, "visual_shell_lane", None)

        if visual_shell_lane is None:
            visual_shell_lane = getattr(assistant, "visual_shell_lane", None)

        if visual_shell_lane is None:
            return

        show_help_overlay = getattr(visual_shell_lane, "show_help_overlay", None)
        if not callable(show_help_overlay):
            return

        try:
            show_help_overlay(language=language, assistant=assistant)
        except Exception as error:
            self.LOGGER.warning(
                "Visual Shell help overlay dispatch failed safely: %s",
                error,
            )


    def _should_suppress_repeated_system_response(
        self,
        *,
        response_key: str,
        window_seconds: float | None = None,
        cooldown_seconds: float | None = None,
    ) -> bool:
        """
        Prevent deterministic spoken responses from self-triggering immediate loops.

        This guard must stay very short. It is not a normal user cooldown.
        A user should be able to ask the same identity/help question again after
        another wake phrase without being silently blocked.
        """
        now = time.monotonic()
        effective_window = window_seconds if window_seconds is not None else cooldown_seconds
        if effective_window is None:
            effective_window = 0.75

        # Never allow this helper to become a long cooldown again.
        effective_window = max(0.0, min(float(effective_window), 1.25))

        attr_name = f"_last_{response_key}_system_response_at"
        last = float(getattr(self, attr_name, 0.0) or 0.0)

        if last > 0.0 and (now - last) < effective_window:
            return True

        setattr(self, attr_name, now)
        return False

    def _handle_help(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        if self._should_suppress_repeated_system_response(
            response_key="assistant_help",
            window_seconds=0.75,
        ):
            return True

        self._show_visual_help_overlay(language=language)
        del route, payload

        if self._should_suppress_repeated_system_response(
            response_key="assistant.help",
            window_seconds=0.75,
        ):
            return True

        spoken = self._localized(
            language,
            "Mogę pomóc Ci na kilka sposobów. Możesz ze mną po prostu porozmawiać. "
            "Możesz zapytać, która jest godzina, poprosić o datę, godzinę, moją temperaturę albo stan baterii. "
            "Powiedz: jaka masz temperaturę, a pokażę temperaturę procesora. Powiedz: pokaż baterię, a pokażę stan baterii. "
            "Mogę zapamiętać coś dla Ciebie. Powiedz: zapamiętaj to. Mogę też przypomnieć Ci o czymś. Powiedz: ustaw przypomnienie. "
            "Mogę szybko coś obliczyć. Powiedz na przykład: ile to jest dwa plus dwa. "
            "Mogę odsłonić pulpit. Powiedz: pokaż pulpit. Gdy chcesz wrócić do pełnego ekranu asystenta, powiedz: schowaj pulpit. "
            "Mogę pokazać godzinę lub datę na ekranie. Powiedz: pokaż godzinę albo pokaż datę. "
            "Mogę pomóc Ci skupić się na nauce lub pracy. Powiedz: focus mode. "
            "Mogę też kontrolować Twoją przerwę od pracy. Powiedz: break mode. "
            "Mogę spojrzeć na Ciebie i śledzić Twoją twarz. Powiedz: spójrz na mnie, a będę Cię obserwować. "
            "Gdy chcesz zakończyć obserwowanie, powiedz: przestań patrzeć. "
            "Mogę uruchomić tryb jazdy dla bazy jezdnej. Powiedz: drive mode. Aby zatrzymać bazę, powiedz: zatrzymaj bazę. "
            "Mogę też przyjąć feedback. Powiedz: feedback on, a potem powiedz, co mam poprawić. "
            "Jeśli chcesz usłyszeć tę pomoc ponownie, powiedz: pomoc albo jak możesz mi pomóc.",
            "I can help you in several ways. You can simply talk with me. "
            "You can ask what time it is, ask for the date, the current time, my temperature, or the battery status. "
            "Say: show your temperature, and I will show my processor temperature. Say: show battery, and I will show the battery status. "
            "I can remember things for you. Say: remember this. I can also remind you about something. Say: set a reminder. "
            "I can calculate quickly. For example, say: calculate two plus two. "
            "I can reveal the desktop. Say: show desktop. When you want to return to the full assistant screen, say: hide desktop. "
            "I can show the time or date on the screen. Say: show time, or show date. "
            "I can help you focus while studying or working. Say: focus mode. "
            "I can also manage your break from work. Say: break mode. "
            "I can look at you and track your face. Say: look at me, and I will keep watching you. "
            "When you want me to stop, say: stop looking at me. "
            "I can start drive mode for the mobile base. Say: drive mode. To stop the base, say: stop base. "
            "I can also receive feedback. Say: feedback on, then tell me what I should improve. "
            "To hear this guide again, say: help, or: how can you help me.",
        )

        display_title = self._localized(language, "JAK MOGĘ POMÓC", "HOW I CAN HELP")
        display_lines = self._localized_lines(
            language,
            [
                "rozmowa i pytania",
                "godzina, data, temperatura, bateria",
                "pamięć i przypomnienia",
                "kalkulator",
                "pulpit i pełny ekran",
                "focus mode i break mode",
                "spójrz na mnie",
                "drive mode i zatrzymaj bazę",
                "feedback on",
            ],
            [
                "conversation and questions",
                "time, date, temperature, battery",
                "memory and reminders",
                "calculator",
                "desktop and full screen",
                "focus mode and break mode",
                "look at me",
                "drive mode and stop base",
                "feedback on",
            ],
        )

        metadata = self._current_action_response_metadata(
            language=language,
            action="help",
            extra_metadata={
                "resolved_source": resolved.source,
                "display_title": display_title,
                "display_lines": display_lines,
                "help_response_mode": "sentence_streamed_text_response",
            },
        )

        delivered = bool(
            self.assistant.deliver_text_response(
                spoken,
                language=language,
                route_kind=RouteKind.ACTION,
                source="action_flow:help",
                remember=True,
                metadata=metadata,
            )
        )

        self._show_visual_help_overlay(language=language)
        return delivered


    def _handle_status(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        timer_status = self._timer_status()
        memory_count = len(self._memory_items())
        reminder_count = len(self._reminder_items())
        current_timer = self.assistant.state.get("current_timer") or self._localized(language, "brak", "none")
        focus_on = bool(self.assistant.state.get("focus_mode"))
        break_on = bool(self.assistant.state.get("break_mode"))
        timer_running = bool(timer_status.get("running"))

        debug_snapshot = self._runtime_debug_snapshot()
        _, _, runtime_metadata = self._build_runtime_benchmark_summary(language)
        runtime_status_spoken, runtime_status_lines, runtime_status_metadata = self._build_runtime_status_summary(language)
        benchmark_spoken = self._benchmark_overview_phrase(language, runtime_metadata)
        audio_snapshot = dict(
            debug_snapshot.get("audio_runtime_snapshot", {}) or self._audio_runtime_snapshot()
        )

        presentation = self._status_debug_presenter().build_status_presentation(
            language=language,
            runtime_status_spoken=runtime_status_spoken,
            runtime_status_lines=runtime_status_lines,
            benchmark_spoken=benchmark_spoken,
            runtime_metadata=runtime_metadata,
            focus_on=focus_on,
            break_on=break_on,
            current_timer=str(current_timer),
            memory_count=memory_count,
            reminder_count=reminder_count,
            timer_running=timer_running,
        )

        return self._deliver_simple_action_response(
            language=language,
            action="status",
            spoken_text=presentation.spoken_text,
            display_title="STATUS",
            display_lines=presentation.display_lines,
            extra_metadata=self._status_debug_presenter().build_status_metadata(
                resolved_source=resolved.source,
                timer_running=timer_running,
                focus_mode=focus_on,
                break_mode=break_on,
                memory_count=memory_count,
                reminder_count=reminder_count,
                current_timer=str(current_timer),
                audio_runtime_snapshot=audio_snapshot,
                runtime_debug_snapshot=debug_snapshot,
                runtime_status_metadata=runtime_status_metadata,
                runtime_metadata=runtime_metadata,
                presentation_metadata=presentation.metadata,
            ),
        )

    def _handle_debug_status(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        debug_snapshot = self._runtime_debug_snapshot()
        _, _, runtime_metadata = self._build_runtime_benchmark_summary(language)
        runtime_status_spoken, _, runtime_status_metadata = self._build_runtime_status_summary(language)
        benchmark_spoken = self._benchmark_overview_phrase(language, runtime_metadata)
        audio_snapshot = dict(
            debug_snapshot.get("audio_runtime_snapshot", {}) or self._audio_runtime_snapshot()
        )

        presentation = self._status_debug_presenter().build_debug_status_presentation(
            language=language,
            runtime_status_spoken=runtime_status_spoken,
            benchmark_spoken=benchmark_spoken,
            runtime_metadata=runtime_metadata,
            audio_snapshot=audio_snapshot,
        )

        return self._deliver_simple_action_response(
            language=language,
            action="debug_status",
            spoken_text=presentation.spoken_text,
            display_title="DEBUG STATUS",
            display_lines=presentation.display_lines,
            extra_metadata=self._status_debug_presenter().build_debug_status_metadata(
                resolved_source=resolved.source,
                audio_runtime_snapshot=audio_snapshot,
                runtime_debug_snapshot=debug_snapshot,
                runtime_status_metadata=runtime_status_metadata,
                runtime_metadata=runtime_metadata,
                presentation_metadata=presentation.metadata,
            ),
        )

    def _handle_calculate(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        expression = str(payload.get("expression", "") or "").strip()
        result = str(payload.get("result", "") or "").strip()
        source_text = str(payload.get("source_text", "") or route.raw_text or "").strip()

        if not expression or not result:
            outcome = evaluate_arithmetic_expression(source_text)
            if not outcome.ok:
                return self._deliver_simple_action_response(
                    language=language,
                    action="calculate",
                    spoken_text=self._localized(
                        language,
                        "Nie udało mi się policzyć tego działania.",
                        "I could not calculate that expression.",
                    ),
                    display_title="CALCULATOR",
                    display_lines=self._localized_lines(
                        language,
                        ["brak wyniku"],
                        ["no result"],
                    ),
                    extra_metadata={
                        "resolved_source": resolved.source,
                        "source_text": source_text,
                        "calculation_error": outcome.error,
                    },
                )
            expression = outcome.expression
            result = outcome.result

        if language == "pl":
            spoken_expression = self._calculator_spoken_expression(expression, language="pl")
            spoken = f"{spoken_expression} to {result}."
            display_title = "KALKULATOR"
        else:
            spoken_expression = self._calculator_spoken_expression(expression, language="en")
            spoken = f"{spoken_expression} is {result}."
            display_title = "CALCULATOR"

        display_expression = expression.replace("*", "×").replace("/", ":")
        return self._deliver_simple_action_response(
            language=language,
            action="calculate",
            spoken_text=spoken,
            display_title=display_title,
            display_lines=[display_expression, f"= {result}"],
            extra_metadata={
                "resolved_source": resolved.source,
                "source_text": source_text,
                "expression": expression,
                "result": result,
                "response_kind": "calculation",
                "llm_prevented": True,
            },
        )

    @staticmethod
    def _calculator_spoken_expression(expression: str, *, language: str) -> str:
        if language == "pl":
            return (
                expression
                .replace("+", " plus ")
                .replace("-", " minus ")
                .replace("*", " razy ")
                .replace("/", " podzielić przez ")
            )
        return (
            expression
            .replace("+", " plus ")
            .replace("-", " minus ")
            .replace("*", " times ")
            .replace("/", " divided by ")
        )

    def _handle_introduce_self(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        if self._should_suppress_repeated_system_response(
            response_key="assistant_identity",
            window_seconds=0.75,
        ):
            return True

        del route, payload

        if self._should_suppress_repeated_system_response(
            response_key="assistant.identity",
            window_seconds=0.75,
        ):
            return True

        spoken = self._localized(
            language,
            "Jestem asystentem AI stworzonym na Raspberry Pi 5. "
            "Pomagam Ci w pracy przy komputerze i w codziennych zadaniach. "
            "Jeśli chcesz wiedzieć, co potrafię, powiedz: pomoc albo jak możesz mi pomóc.",
            "I am an AI assistant built on a Raspberry Pi 5. "
            "I help you work at your computer and support everyday tasks. "
            "To learn what I can do, say: help, or how can you help me.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="introduce_self",
            spoken_text=spoken,
            display_title="NeXa",
            display_lines=self._localized_lines(
                language,
                ["lokalny", "desk assistant", "raspberry pi"],
                ["local", "desk assistant", "raspberry pi"],
            ),
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_ask_time(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = now.strftime("%H %M")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_time",
            spoken_text=spoken,
            display_title="TIME",
            display_lines=[now.strftime("%H:%M")],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_time(self, **kwargs: Any) -> bool:
        return self._handle_ask_time(**kwargs)

    def _handle_ask_date(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(
            language,
            f"Dzisiaj jest {now.strftime('%d.%m.%Y')}.",
            f"Today is {now.strftime('%d.%m.%Y')}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="ask_date",
            spoken_text=spoken,
            display_title="DATE",
            display_lines=[now.strftime("%d.%m.%Y")],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_date(self, **kwargs: Any) -> bool:
        return self._handle_ask_date(**kwargs)

    def _handle_ask_day(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        day_name = self._localized_day_name(now.weekday(), language)
        spoken = self._localized(language, f"Dzisiaj jest {day_name}.", f"Today is {day_name}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_day",
            spoken_text=spoken,
            display_title="DAY",
            display_lines=[day_name],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_day(self, **kwargs: Any) -> bool:
        return self._handle_ask_day(**kwargs)

    def _handle_ask_month(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        month_name = self._localized_month_name(now.month, language)
        spoken = self._localized(language, f"Jest miesiąc {month_name}.", f"It is {month_name}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_month",
            spoken_text=spoken,
            display_title="MONTH",
            display_lines=[month_name],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_month(self, **kwargs: Any) -> bool:
        return self._handle_ask_month(**kwargs)

    def _handle_ask_year(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(language, f"Mamy rok {now.year}.", f"The year is {now.year}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_year",
            spoken_text=spoken,
            display_title="YEAR",
            display_lines=[str(now.year)],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_year(self, **kwargs: Any) -> bool:
        return self._handle_ask_year(**kwargs)

    def _handle_exit(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        del route, payload, request
        self.assistant.pending_follow_up = None
        self.assistant.pending_confirmation = None

        display = getattr(self.assistant, "display", None)
        if display is not None:
            try:
                display.show_block(
                    self._localized(language, "DO WIDZENIA", "GOODBYE"),
                    [self._localized(language, "zamykam NeXa", "closing NeXa")],
                    duration=0.8,
                )
            except Exception:
                pass

        delivered = self._deliver_simple_action_response(
            language=language,
            action="exit",
            spoken_text=self._localized(
                language,
                "Zamykam NeXa.",
                "Closing NeXa.",
            ),
            display_title="EXIT",
            display_lines=self._localized_lines(
                language,
                ["zamykam", "runtime"],
                ["closing", "runtime"],
            ),
            extra_metadata={
                "resolved_source": resolved.source,
                "exit_requested": True,
                "response_kind": "runtime_exit",
            },
        )
        return SkillResult(
            action="exit",
            handled=False,
            response_delivered=bool(delivered),
            status="runtime_exit_requested",
            metadata={
                "source": "action_flow.exit",
                "response_kind": "runtime_exit",
                "exit_requested": True,
            },
        )

    def _handle_shutdown(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload

        allow_shutdown = bool(self.assistant.settings.get("system", {}).get("allow_shutdown_commands", False))
        if not allow_shutdown:
            return self._deliver_simple_action_response(
                language=language,
                action="shutdown",
                spoken_text=self._localized(
                    language,
                    "Wyłączanie systemu jest teraz wyłączone w ustawieniach.",
                    "System shutdown is currently disabled in settings.",
                ),
                display_title="SHUTDOWN DISABLED",
                display_lines=self._localized_lines(
                    language,
                    ["sprawdz ustawienia"],
                    ["check settings"],
                ),
                extra_metadata={"resolved_source": resolved.source, "phase": "blocked_by_config"},
            )

        self.assistant.pending_follow_up = {"type": "confirm_shutdown", "lang": language}
        spoken = self._localized(
            language,
            "Czy chcesz, żebym wyłączyła system?",
            "Do you want me to shut down the system?",
        )
        return self._deliver_action_follow_up_prompt(
            language=language,
            action=request.action if request is not None else "shutdown",
            spoken_text=spoken,
            source="action_shutdown_confirmation",
            follow_up_type="confirm_shutdown",
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_confirm_yes(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        return self._deliver_simple_action_response(
            language=language,
            action="confirm_yes",
            spoken_text=self._localized(
                language,
                "Nie ma teraz nic do potwierdzenia.",
                "There is nothing to confirm right now.",
            ),
            display_title="CONFIRMATION",
            display_lines=self._localized_lines(
                language,
                ["brak aktywnego", "potwierdzenia"],
                ["nothing active", "to confirm"],
            ),
            extra_metadata={"resolved_source": resolved.source, "phase": "orphan_confirmation"},
        )

    def _handle_confirm_no(self, **kwargs: Any) -> bool:
        return self._handle_confirm_yes(**kwargs)

    def _handle_unknown(
        self,
        *,
        route: RouteDecision,
        language: str,
        resolved: ResolvedAction,
    ) -> bool:
        del route
        return self._deliver_simple_action_response(
            language=language,
            action="unknown",
            spoken_text=self._localized(
                language,
                "Tego jeszcze nie obsługuję.",
                "I cannot do that yet.",
            ),
            display_title="ACTION",
            display_lines=self._localized_lines(
                language,
                ["funkcja", "jeszcze niedostepna"],
                ["feature", "not ready yet"],
            ),
            extra_metadata={"resolved_source": resolved.source, "phase": "unsupported_action"},
        )

    # ----- feedback mode -----------------------------------------------
    def _resolve_feedback_lane(self):
        assistant = getattr(self, "assistant", None)
        if assistant is None:
            return None, None

        existing = getattr(assistant, "_feedback_lane", None)
        if existing is not None:
            return existing, assistant

        try:
            from modules.presentation.visual_shell.feedback.feedback_lane import (
                FeedbackLane,
            )
        except Exception as error:
            self.LOGGER.warning("Feedback lane import failed safely: %s", error)
            return None, assistant

        fast_command_lane = getattr(assistant, "fast_command_lane", None)
        visual_shell_lane = getattr(fast_command_lane, "visual_shell_lane", None) \
            or getattr(assistant, "visual_shell_lane", None)

        if visual_shell_lane is None:
            self.LOGGER.warning("Feedback lane unavailable: visual shell lane missing.")
            return None, assistant

        lane = FeedbackLane(visual_shell_lane=visual_shell_lane, assistant=assistant)
        try:
            assistant._feedback_lane = lane
        except Exception:
            pass

        return lane, assistant

    def _handle_feedback_on(
        self,
        *,
        route,
        language,
        payload,
        resolved,
    ) -> bool:
        del route, payload

        lane, _assistant = self._resolve_feedback_lane()
        ok = False

        if lane is not None:
            try:
                ok = bool(lane.turn_on(language=language))
            except Exception as error:
                self.LOGGER.warning("Feedback turn_on failed safely: %s", error)

        spoken = self._localized(
            language,
            "Włączam tryb feedback.",
            "Feedback mode on.",
        )

        return self._deliver_simple_action_response(
            language=language,
            action="feedback_on",
            spoken_text=spoken,
            display_title=self._localized(language, "FEEDBACK", "FEEDBACK"),
            display_lines=self._localized_lines(
                language,
                ["uruchomiono", "logi i statusy live"],
                ["enabled", "live logs and status"],
            ),
            extra_metadata={
                "resolved_source": getattr(resolved, "source", ""),
                "feedback_started": ok,
            },
        )

    def _handle_feedback_off(
        self,
        *,
        route,
        language,
        payload,
        resolved,
    ) -> bool:
        del route, payload

        lane, _assistant = self._resolve_feedback_lane()
        ok = False

        if lane is not None:
            try:
                ok = bool(lane.turn_off())
            except Exception as error:
                self.LOGGER.warning("Feedback turn_off failed safely: %s", error)

        spoken = self._localized(
            language,
            "Wyłączam tryb feedback.",
            "Feedback mode off.",
        )

        return self._deliver_simple_action_response(
            language=language,
            action="feedback_off",
            spoken_text=spoken,
            display_title=self._localized(language, "FEEDBACK", "FEEDBACK"),
            display_lines=self._localized_lines(
                language,
                ["zamknięto"],
                ["closed"],
            ),
            extra_metadata={
                "resolved_source": getattr(resolved, "source", ""),
                "feedback_stopped": ok,
            },
        )
