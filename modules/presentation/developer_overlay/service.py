from __future__ import annotations

import logging
from typing import Any, Callable

from .models import DeveloperOverlayPayload

LOGGER = logging.getLogger(__name__)


class DeveloperOverlayService:
    """
    Compose a compact developer HUD from runtime, audio, and benchmark snapshots.

    The service is presentation-only. It does not own telemetry collection and it
    does not know how the physical display renders the overlay. Its role is to
    build a compact payload and push it into the display backend through the
    dedicated developer overlay channel.
    """

    def __init__(
        self,
        *,
        display: Any,
        runtime_snapshot_provider: Callable[[], dict[str, Any]] | None,
        benchmark_snapshot_provider: Callable[[], dict[str, Any]] | None,
        audio_snapshot_provider: Callable[[], dict[str, Any]] | None = None,
        debug_snapshot_provider: Callable[[], dict[str, Any]] | None = None,
        enabled: bool = True,
        title: str = "DEV",
        refresh_on_boot: bool = True,
        refresh_on_turn_finish: bool = True,
    ) -> None:
        self.display = display
        self.runtime_snapshot_provider = runtime_snapshot_provider
        self.benchmark_snapshot_provider = benchmark_snapshot_provider
        self.audio_snapshot_provider = audio_snapshot_provider
        self.debug_snapshot_provider = debug_snapshot_provider
        self.enabled = bool(enabled)
        self.title = str(title or "DEV").strip() or "DEV"
        self.refresh_on_boot = bool(refresh_on_boot)
        self.refresh_on_turn_finish = bool(refresh_on_turn_finish)
        self._last_payload = DeveloperOverlayPayload(title=self.title)

    def refresh(self, *, reason: str = "manual") -> bool:
        reason_key = str(reason or "manual").strip().lower() or "manual"
        if not self.enabled:
            self.clear()
            return False

        if reason_key == "boot" and not self.refresh_on_boot:
            return False
        if reason_key == "turn_finished" and not self.refresh_on_turn_finish:
            return False

        payload = self._build_payload_from_debug_snapshot(
            self._safe_snapshot(self.debug_snapshot_provider)
        )
        if payload is None:
            payload = self._build_payload(
                runtime_snapshot=self._safe_snapshot(self.runtime_snapshot_provider),
                benchmark_snapshot=self._safe_snapshot(self.benchmark_snapshot_provider),
                audio_snapshot=self._safe_snapshot(self.audio_snapshot_provider),
            )

        self._last_payload = payload

        setter = getattr(self.display, "set_developer_overlay", None)
        if not callable(setter):
            return False

        if not payload.lines:
            self.clear()
            return False

        try:
            setter(payload.title, payload.lines)
            return True
        except Exception as error:
            LOGGER.warning("Developer overlay refresh failed: %s", error)
            return False

    def clear(self) -> None:
        clear_method = getattr(self.display, "clear_developer_overlay", None)
        if not callable(clear_method):
            return

        try:
            clear_method()
        except Exception as error:
            LOGGER.warning("Developer overlay clear failed: %s", error)

    def snapshot(self) -> dict[str, Any]:
        return self._last_payload.to_dict()

    def _build_payload_from_debug_snapshot(
        self,
        debug_snapshot: dict[str, Any],
    ) -> DeveloperOverlayPayload | None:
        if not debug_snapshot:
            return None

        lines = [
            self._compact_line(item, max_chars=34)
            for item in list(debug_snapshot.get("developer_overlay_lines", []) or [])
            if self._compact_line(item, max_chars=34)
        ]
        if not lines:
            return None

        audio_line = self._compact_line(
            debug_snapshot.get("audio_overlay_line", ""),
            max_chars=34,
        )

        return DeveloperOverlayPayload(
            title=self.title,
            lines=lines[:3],
            runtime_label=str(debug_snapshot.get("runtime_label", "") or "").strip(),
            llm_label=str(debug_snapshot.get("llm_label", "") or "").strip(),
            benchmark_available=bool(debug_snapshot.get("benchmark_snapshot", {})),
            audio_available=bool(audio_line),
            audio_line=audio_line,
        )

    def _build_payload(
        self,
        *,
        runtime_snapshot: dict[str, Any],
        benchmark_snapshot: dict[str, Any],
        audio_snapshot: dict[str, Any],
    ) -> DeveloperOverlayPayload:
        runtime_label = self._runtime_label(runtime_snapshot)
        llm_label = self._llm_label(runtime_snapshot)
        runtime_line = f"rt:{runtime_label} llm:{llm_label}"

        benchmark_lines = [
            self._compact_line(item)
            for item in list(benchmark_snapshot.get("overlay_lines", []) or [])
            if self._compact_line(item)
        ]
        audio_line = self._build_audio_line(audio_snapshot)

        lines = [runtime_line]
        if benchmark_lines:
            lines.append(benchmark_lines[0])
        if audio_line:
            lines.append(audio_line)
        elif len(benchmark_lines) > 1:
            lines.append(benchmark_lines[1])

        return DeveloperOverlayPayload(
            title=self.title,
            lines=lines,
            runtime_label=runtime_label,
            llm_label=llm_label,
            benchmark_available=bool(benchmark_lines),
            audio_available=bool(audio_line),
            audio_line=audio_line,
        )

    @staticmethod
    def _safe_snapshot(provider: Callable[[], dict[str, Any]] | None) -> dict[str, Any]:
        if not callable(provider):
            return {}

        try:
            payload = provider()
        except Exception as error:
            LOGGER.warning("Developer overlay snapshot provider failed: %s", error)
            return {}

        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _compact_line(value: Any, *, max_chars: int = 32) -> str:
        compact = " ".join(str(value or "").split()).strip()
        if not compact:
            return ""
        if len(compact) <= max_chars:
            return compact
        return f"{compact[: max_chars - 3].rstrip()}..."

    def _build_audio_line(self, snapshot: dict[str, Any]) -> str:
        if not snapshot:
            return ""

        phase = self._audio_token(snapshot.get("interaction_phase"), fallback="n/a", max_chars=8)
        owner = self._audio_token(snapshot.get("input_owner"), fallback="n/a", max_chars=8)

        resume_snapshot = dict(snapshot.get("last_resume_policy", {}) or {})
        resume = self._audio_token(resume_snapshot.get("action"), fallback="n/a", max_chars=6)

        command_snapshot = dict(snapshot.get("last_command_window_policy", {}) or {})
        command = self._audio_token(command_snapshot.get("action"), fallback="n/a", max_chars=6)

        remaining = snapshot.get("active_window_remaining_seconds", 0.0)
        try:
            remaining_value = max(0.0, float(remaining or 0.0))
        except (TypeError, ValueError):
            remaining_value = 0.0

        return self._compact_line(
            f"ph:{phase} own:{owner} rs:{resume} cw:{command} w:{remaining_value:.1f}s",
            max_chars=34,
        )

    @staticmethod
    def _audio_token(value: Any, *, fallback: str, max_chars: int) -> str:
        compact = " ".join(str(value or fallback).split()).strip().lower() or fallback
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars]

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


__all__ = ["DeveloperOverlayService"]