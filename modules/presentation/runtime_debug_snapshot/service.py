from __future__ import annotations

import logging
from typing import Any, Callable

from .models import RuntimeDebugSnapshotPayload

LOGGER = logging.getLogger(__name__)


class RuntimeDebugSnapshotService:
    """
    Compose one compact runtime/debug snapshot shared by status, debug status,
    and developer overlay flows.

    This service is presentation-facing only. It reads already-existing runtime,
    benchmark, and audio telemetry providers and normalizes them into a single
    stable payload for downstream consumers.
    """

    def __init__(
        self,
        *,
        runtime_snapshot_provider: Callable[[], dict[str, Any]] | None,
        benchmark_snapshot_provider: Callable[[], dict[str, Any]] | None,
        audio_snapshot_provider: Callable[[], dict[str, Any]] | None,
        ai_broker_snapshot_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.runtime_snapshot_provider = runtime_snapshot_provider
        self.benchmark_snapshot_provider = benchmark_snapshot_provider
        self.audio_snapshot_provider = audio_snapshot_provider
        self.ai_broker_snapshot_provider = ai_broker_snapshot_provider
        self._last_payload = RuntimeDebugSnapshotPayload()

    def snapshot(self) -> dict[str, Any]:
        payload = self._build_payload(
            runtime_snapshot=self._safe_snapshot(self.runtime_snapshot_provider),
            benchmark_snapshot=self._safe_snapshot(self.benchmark_snapshot_provider),
            audio_snapshot=self._safe_snapshot(self.audio_snapshot_provider),
            ai_broker_snapshot=self._safe_snapshot(self.ai_broker_snapshot_provider),
        )
        self._last_payload = payload
        return payload.to_dict()

    def _build_payload(
        self,
        *,
        runtime_snapshot: dict[str, Any],
        benchmark_snapshot: dict[str, Any],
        audio_snapshot: dict[str, Any],
        ai_broker_snapshot: dict[str, Any],
    ) -> RuntimeDebugSnapshotPayload:
        latest_sample = dict(benchmark_snapshot.get("latest_sample", {}) or {})
        summary = dict(benchmark_snapshot.get("summary", {}) or {})

        completed_turn_trace = self._completed_turn_trace(latest_sample)
        completed_turn_lines = self._completed_turn_lines(completed_turn_trace)
        audio_lines = self._audio_lines(audio_snapshot)
        audio_overlay_line = self._build_audio_overlay_line(audio_snapshot)
        ai_broker_line = self._build_ai_broker_line(ai_broker_snapshot)

        runtime_label = self._runtime_label(runtime_snapshot)
        llm_label = self._llm_label(runtime_snapshot)

        wake_backend = self._backend_token(runtime_snapshot, "wake_gate")
        stt_backend = self._backend_token(runtime_snapshot, "voice_input")
        llm_backend = self._backend_token(runtime_snapshot, "llm")

        last_turn_ms = self._safe_float(latest_sample.get("total_turn_ms"))
        avg_audio_ms = self._safe_float(summary.get("avg_response_first_audio_ms"))
        avg_llm_first_chunk_ms = self._safe_float(summary.get("avg_llm_first_chunk_ms"))

        developer_overlay_lines = self._build_developer_overlay_lines(
            runtime_label=runtime_label,
            llm_label=llm_label,
            benchmark_snapshot=benchmark_snapshot,
            audio_overlay_line=audio_overlay_line,
            ai_broker_line=ai_broker_line,
            completed_turn_trace=completed_turn_trace,
            last_turn_ms=last_turn_ms,
            avg_audio_ms=avg_audio_ms,
        )

        return RuntimeDebugSnapshotPayload(
            runtime_snapshot=runtime_snapshot,
            benchmark_snapshot=benchmark_snapshot,
            audio_runtime_snapshot=audio_snapshot,
            ai_broker_snapshot=ai_broker_snapshot,
            runtime_label=runtime_label,
            llm_label=llm_label,
            wake_backend=wake_backend,
            stt_backend=stt_backend,
            llm_backend=llm_backend,
            last_turn_ms=last_turn_ms,
            avg_response_first_audio_ms=avg_audio_ms,
            avg_llm_first_chunk_ms=avg_llm_first_chunk_ms,
            completed_turn_trace=completed_turn_trace,
            completed_turn_lines=completed_turn_lines,
            audio_lines=audio_lines,
            audio_overlay_line=audio_overlay_line,
            ai_broker_line=ai_broker_line,
            developer_overlay_lines=developer_overlay_lines,
        )

    @staticmethod
    def _safe_snapshot(provider: Callable[[], dict[str, Any]] | None) -> dict[str, Any]:
        if not callable(provider):
            return {}

        try:
            payload = provider()
        except Exception as error:
            LOGGER.warning("Runtime debug snapshot provider failed: %s", error)
            return {}

        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _runtime_service_payload(snapshot: dict[str, Any], component: str) -> dict[str, Any]:
        services = snapshot.get("services", {})
        if not isinstance(services, dict):
            return {}

        payload = services.get(component, {})
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _backend_token(self, snapshot: dict[str, Any], component: str) -> str:
        payload = self._runtime_service_payload(snapshot, component)
        raw = str(
            payload.get("backend")
            or payload.get("selected_backend")
            or payload.get("requested_backend")
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
    def _safe_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0.0:
            return None
        return parsed

    @staticmethod
    def _compact_text(value: Any, *, max_chars: int) -> str:
        compact = " ".join(str(value or "").split()).strip()
        if not compact:
            return ""
        if len(compact) <= max_chars:
            return compact
        return f"{compact[: max_chars - 3].rstrip()}..."

    @staticmethod
    def _compact_token(value: Any, *, fallback: str, max_chars: int) -> str:
        compact = " ".join(str(value or fallback).split()).strip().lower() or fallback
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars]

    @staticmethod
    def _metric_display(value_ms: float | None) -> str:
        if value_ms is None:
            return "n/a"
        return f"{int(round(float(value_ms)))}ms"

    @staticmethod
    def _runtime_label(snapshot: dict[str, Any]) -> str:
        if bool(snapshot.get("premium_ready", False)):
            return "premium"
        if str(snapshot.get("startup_mode", "") or "").strip().lower() == "limited":
            return "limited"
        if bool(snapshot.get("primary_ready", False)):
            compatibility = list(snapshot.get("compatibility_components", []) or [])
            return "compat" if compatibility else "ready"

        lifecycle_state = str(snapshot.get("lifecycle_state", "") or "").strip().lower()
        if lifecycle_state in {"degraded", "failed"}:
            return "degraded"
        if lifecycle_state == "shutting_down":
            return "stopping"
        if lifecycle_state in {"ready", "standby"}:
            return "ready"
        return "booting"

    @staticmethod
    def _llm_label(snapshot: dict[str, Any]) -> str:
        if not snapshot:
            return "n/a"
        if not bool(snapshot.get("llm_enabled", False)):
            return "off"
        if bool(snapshot.get("llm_warmup_ready", False)):
            return "ready"
        if bool(snapshot.get("llm_available", False)):
            state = str(snapshot.get("llm_state", "") or "").strip().lower()
            if state in {"warming", "warmup", "starting"}:
                return "warm"
            return "up"

        state = str(snapshot.get("llm_state", "") or "").strip().lower()
        if state in {"warming", "warmup", "starting"}:
            return "warm"
        return "down"

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
            "stt_latency_ms": self._safe_float(sample.get("stt_latency_ms")),
            "wake_latency_ms": self._safe_float(sample.get("wake_latency_ms")),
        }

    def _completed_turn_lines(self, trace: dict[str, Any]) -> list[str]:
        route_kind = str(trace.get("route_kind", "") or "n/a")[:12]
        result = str(trace.get("result", "") or "n/a")[:16]
        resume_action = str(trace.get("resume_action", "") or "n/a")[:12]
        command_action = str(trace.get("command_action", "") or "n/a")[:12]
        command_phase = str(trace.get("command_phase", "") or "n/a")[:12]

        return [
            f"trace: {route_kind}",
            f"result: {result}",
            f"resume: {resume_action}",
            f"cmd: {command_action}",
            f"phase: {command_phase}",
        ]

    def _audio_lines(self, snapshot: dict[str, Any]) -> list[str]:
        phase = self._compact_token(snapshot.get("interaction_phase"), fallback="n/a", max_chars=14)
        owner = self._compact_token(snapshot.get("input_owner"), fallback="n/a", max_chars=14)
        resume_action = self._compact_token(
            dict(snapshot.get("last_resume_policy", {}) or {}).get("action"),
            fallback="n/a",
            max_chars=10,
        )
        command_action = self._compact_token(
            dict(snapshot.get("last_command_window_policy", {}) or {}).get("action"),
            fallback="n/a",
            max_chars=10,
        )
        handoff_owner = self._compact_token(
            dict(snapshot.get("last_capture_handoff", {}) or {}).get("applied_owner"),
            fallback="n/a",
            max_chars=14,
        )

        return [
            f"phase: {phase}",
            f"owner: {owner}",
            f"resume: {resume_action}",
            f"cmd: {command_action}",
            f"handoff: {handoff_owner}",
        ]

    def _build_audio_overlay_line(self, snapshot: dict[str, Any]) -> str:
        if not snapshot:
            return ""

        phase = self._compact_token(snapshot.get("interaction_phase"), fallback="n/a", max_chars=8)
        owner = self._compact_token(snapshot.get("input_owner"), fallback="n/a", max_chars=8)

        resume_snapshot = dict(snapshot.get("last_resume_policy", {}) or {})
        resume = self._compact_token(resume_snapshot.get("action"), fallback="n/a", max_chars=6)

        command_snapshot = dict(snapshot.get("last_command_window_policy", {}) or {})
        command = self._compact_token(command_snapshot.get("action"), fallback="n/a", max_chars=6)

        remaining = snapshot.get("active_window_remaining_seconds", 0.0)
        try:
            remaining_value = max(0.0, float(remaining or 0.0))
        except (TypeError, ValueError):
            remaining_value = 0.0

        return self._compact_text(
            f"ph:{phase} own:{owner} rs:{resume} cw:{command} w:{remaining_value:.1f}s",
            max_chars=34,
        )

    def _build_ai_broker_line(self, snapshot: dict[str, Any]) -> str:
        if not snapshot:
            return ""

        mode = self._compact_token(snapshot.get("mode"), fallback="n/a", max_chars=10)
        owner = self._compact_token(snapshot.get("owner"), fallback="n/a", max_chars=8)
        profile = dict(snapshot.get("profile", {}) or {})
        heavy_lane = self._safe_float(profile.get("heavy_lane_cadence_hz"))
        heavy_text = "n/a" if heavy_lane is None else f"{heavy_lane:.1f}"
        recovery = "on" if bool(snapshot.get("recovery_window_active", False)) else "off"

        return self._compact_text(
            f"ai:{mode} own:{owner} hv:{heavy_text} rw:{recovery}",
            max_chars=34,
        )

    def _completed_turn_overlay_line(self, trace: dict[str, Any]) -> str:
        route_kind = self._compact_token(trace.get("route_kind"), fallback="n/a", max_chars=8)
        result = self._compact_token(trace.get("result"), fallback="n/a", max_chars=10)
        resume = self._compact_token(trace.get("resume_action"), fallback="n/a", max_chars=6)
        command = self._compact_token(trace.get("command_action"), fallback="n/a", max_chars=6)

        return self._compact_text(
            f"tr:{route_kind} res:{result} rs:{resume} cw:{command}",
            max_chars=34,
        )

    def _build_developer_overlay_lines(
        self,
        *,
        runtime_label: str,
        llm_label: str,
        benchmark_snapshot: dict[str, Any],
        audio_overlay_line: str,
        ai_broker_line: str,
        completed_turn_trace: dict[str, Any],
        last_turn_ms: float | None,
        avg_audio_ms: float | None,
    ) -> list[str]:
        runtime_line = f"rt:{runtime_label} llm:{llm_label}"

        benchmark_lines = [
            self._compact_text(item, max_chars=34)
            for item in list(benchmark_snapshot.get("overlay_lines", []) or [])
            if self._compact_text(item, max_chars=34)
        ]

        if ai_broker_line:
            second_line = ai_broker_line
        elif benchmark_lines:
            second_line = benchmark_lines[0]
        else:
            second_line = self._compact_text(
                f"turn:{self._metric_display(last_turn_ms)} audio:{self._metric_display(avg_audio_ms)}",
                max_chars=34,
            )

        third_line = audio_overlay_line or self._completed_turn_overlay_line(completed_turn_trace)
        if not third_line and len(benchmark_lines) > 1:
            third_line = benchmark_lines[1]

        lines = [runtime_line]
        if second_line:
            lines.append(second_line)
        if third_line:
            lines.append(third_line)
        return lines[:3]


__all__ = ["RuntimeDebugSnapshotService"]