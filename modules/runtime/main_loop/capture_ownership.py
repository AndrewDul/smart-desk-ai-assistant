from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest import result

from modules.core import assistant
from modules.core.session.voice_session import (
    VOICE_INPUT_OWNER_ASSISTANT_OUTPUT,
    VOICE_INPUT_OWNER_NONE,
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_THINKING,
)
from modules.shared.logging.logger import append_log

from .constants import INPUT_READY_MAX_WAIT_SECONDS

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


@dataclass(slots=True)
class CaptureOwnershipResult:
    target_owner: str
    applied_owner: str
    wake_backend_label: str = ""
    wake_backend_released: bool = False
    wake_backend_release_mode: str = "none"
    voice_input_released: bool = False
    voice_input_release_mode: str = "none"
    blocked_observed: bool = False
    wait_completed: bool = True
    wait_elapsed_ms: float = 0.0
    settle_seconds: float = 0.0


class CaptureOwnershipService:
    """
    Hardened handoff orchestration for wake capture vs active voice capture.

    Responsibilities:
    - release the currently non-owning capture backend when needed
    - wait for output shielding to stop blocking microphone input
    - set the expected input owner in voice session state
    - expose a structured result for diagnostics and tests
    """

    def prepare_for_active_capture(
        self,
        assistant: CoreAssistant,
        *,
        max_wait_seconds: float = INPUT_READY_MAX_WAIT_SECONDS,
    ) -> CaptureOwnershipResult:
        wake_backend_released, wake_release_mode, backend_label = self.ensure_wake_capture_released(assistant)

        wait_result = self._wait_for_input_ready(
            assistant,
            max_wait_seconds=max_wait_seconds,
        )
        applied_owner = self._set_input_owner(
            assistant,
            VOICE_INPUT_OWNER_VOICE_INPUT,
        )

        result = CaptureOwnershipResult(
            target_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
            applied_owner=applied_owner,
            wake_backend_label=backend_label,
            wake_backend_released=wake_backend_released,
            wake_backend_release_mode=wake_release_mode,
            voice_input_released=False,
            voice_input_release_mode="none",
            blocked_observed=wait_result["blocked_observed"],
            wait_completed=wait_result["wait_completed"],
            wait_elapsed_ms=wait_result["wait_elapsed_ms"],
            settle_seconds=wait_result["settle_seconds"],
        )
        self._store_last_result(assistant, result)
        append_log(
            "Capture handoff prepared for active capture: "
            f"owner={result.applied_owner}, wake_backend={backend_label}, "
            f"wake_released={result.wake_backend_released}, "
            f"wake_release_mode={result.wake_backend_release_mode}, "
            f"blocked_observed={result.blocked_observed}, "
            f"wait_completed={result.wait_completed}, "
            f"wait_elapsed_ms={result.wait_elapsed_ms:.1f}"
        )
        return result

    def prepare_for_standby_capture(
        self,
        assistant: CoreAssistant,
    ) -> CaptureOwnershipResult:
        voice_input_released, voice_input_release_mode = self.ensure_voice_capture_released(assistant)
        _, backend_label = self._resolve_wake_backend(assistant)

        applied_owner = self._set_input_owner(
            assistant,
            VOICE_INPUT_OWNER_WAKE_GATE,
        )

        result = CaptureOwnershipResult(
            target_owner=VOICE_INPUT_OWNER_WAKE_GATE,
            applied_owner=applied_owner,
            wake_backend_label=backend_label,
            wake_backend_released=False,
            wake_backend_release_mode="none",
            voice_input_released=voice_input_released,
            voice_input_release_mode=voice_input_release_mode,
            blocked_observed=False,
            wait_completed=True,
            wait_elapsed_ms=0.0,
            settle_seconds=0.0,
        )
        self._store_last_result(assistant, result)
        append_log(
            "Capture handoff prepared for standby capture: "
            f"owner={result.applied_owner}, wake_backend={backend_label}, "
            f"voice_input_released={result.voice_input_released}, "
            f"voice_input_release_mode={result.voice_input_release_mode}"
        )
        return result

    def ensure_wake_capture_released(self, assistant: CoreAssistant) -> tuple[bool, str, str]:
        wake_backend, backend_label = self._resolve_wake_backend(assistant)
        voice_in = getattr(assistant, "voice_in", None)

        if wake_backend is None:
            return False, "none", backend_label
        if wake_backend is voice_in:
            return False, "none", backend_label
        if self._wake_backend_shares_voice_input(assistant, wake_backend):
            return False, "none", backend_label

        released, release_mode = self._safe_release_runtime_component(
            assistant,
            wake_backend,
            backend_label,
        )
        return released, release_mode, backend_label

    def ensure_voice_capture_released(self, assistant: CoreAssistant) -> tuple[bool, str]:
        voice_in = getattr(assistant, "voice_in", None)
        if voice_in is None:
            return False, "none"

        wake_backend, _ = self._resolve_wake_backend(assistant)
        if self._wake_backend_shares_voice_input(assistant, wake_backend):
            return False, "none"

        return self._safe_release_runtime_component(
            assistant,
            voice_in,
            "voice_input",
        )

    def assistant_output_blocks_input(self, assistant: CoreAssistant) -> bool:
        coordinator = getattr(getattr(assistant, "voice_out", None), "audio_coordinator", None)
        if coordinator is None:
            return False

        input_blocked = getattr(coordinator, "input_blocked", None)
        if not callable(input_blocked):
            return False

        try:
            blocked = bool(input_blocked())
        except Exception:
            return False

        self._set_input_owner(
            assistant,
            VOICE_INPUT_OWNER_ASSISTANT_OUTPUT if blocked else VOICE_INPUT_OWNER_NONE,
        )

        voice_session = getattr(assistant, "voice_session", None)
        if blocked and voice_session is not None:
            current_state = getattr(voice_session, "state", "")
            if current_state not in {
                VOICE_STATE_SPEAKING,
                VOICE_STATE_THINKING,
                VOICE_STATE_SHUTDOWN,
            }:
                set_state = getattr(voice_session, "set_state", None)
                if callable(set_state):
                    try:
                        set_state(VOICE_STATE_SPEAKING, detail="assistant_output_shield")
                    except Exception:
                        pass

        return blocked

    def input_resume_poll_seconds(self, assistant: CoreAssistant) -> float:
        cfg = assistant.settings.get("audio_coordination", {})
        configured = cfg.get("listen_resume_poll_seconds")
        if configured is not None:
            try:
                return max(0.01, float(configured))
            except (TypeError, ValueError):
                pass

        coordinator = getattr(getattr(assistant, "voice_out", None), "audio_coordinator", None)
        for attr in ("listen_resume_poll_seconds", "input_poll_interval_seconds"):
            value = getattr(coordinator, attr, None)
            if value is not None:
                try:
                    return max(0.01, float(value))
                except (TypeError, ValueError):
                    continue
        return 0.05

    def wait_for_input_ready(
        self,
        assistant: CoreAssistant,
        *,
        max_wait_seconds: float = INPUT_READY_MAX_WAIT_SECONDS,
    ) -> CaptureOwnershipResult:
        wait_result = self._wait_for_input_ready(
            assistant,
            max_wait_seconds=max_wait_seconds,
        )
        result = CaptureOwnershipResult(
            target_owner="wait_only",
            applied_owner=self._current_input_owner(assistant),
            blocked_observed=wait_result["blocked_observed"],
            wait_completed=wait_result["wait_completed"],
            wait_elapsed_ms=wait_result["wait_elapsed_ms"],
            settle_seconds=wait_result["settle_seconds"],
        )
        self._store_last_result(assistant, result)
        return result

    def _wait_for_input_ready(
        self,
        assistant: CoreAssistant,
        *,
        max_wait_seconds: float,
    ) -> dict[str, float | bool]:
        deadline = time.monotonic() + max(0.1, float(max_wait_seconds))
        blocked_observed = False
        started_at = time.monotonic()

        while time.monotonic() < deadline:
            if not self.assistant_output_blocks_input(assistant):
                break
            blocked_observed = True
            time.sleep(self.input_resume_poll_seconds(assistant))

        wait_completed = not self.assistant_output_blocks_input(assistant)
        settle_seconds = 0.0
        if blocked_observed:
            settle_seconds = self._input_settle_seconds(assistant)
            if settle_seconds > 0.0:
                time.sleep(settle_seconds)

        return {
            "blocked_observed": blocked_observed,
            "wait_completed": wait_completed,
            "wait_elapsed_ms": max(0.0, (time.monotonic() - started_at) * 1000.0),
            "settle_seconds": settle_seconds,
        }

    def _input_settle_seconds(self, assistant: CoreAssistant) -> float:
        settle_candidates: list[float] = []
        for component_name in ("voice_in", "wake_gate"):
            component = getattr(assistant, component_name, None)
            if component is None:
                continue
            for attr in ("input_unblock_settle_seconds", "block_release_settle_seconds"):
                value = getattr(component, attr, None)
                if value is None:
                    continue
                try:
                    settle_candidates.append(max(0.0, float(value)))
                except (TypeError, ValueError):
                    continue
        return max(settle_candidates) if settle_candidates else 0.0

    def _set_input_owner(self, assistant: CoreAssistant, owner: str) -> str:
        voice_session = getattr(assistant, "voice_session", None)
        set_input_owner = getattr(voice_session, "set_input_owner", None)
        if callable(set_input_owner):
            try:
                set_input_owner(owner)
            except Exception:
                pass
        return self._current_input_owner(assistant)

    def _current_input_owner(self, assistant: CoreAssistant) -> str:
        voice_session = getattr(assistant, "voice_session", None)
        owner_method = getattr(voice_session, "input_owner", None)
        if callable(owner_method):
            try:
                value = owner_method()
                normalized = str(value or "").strip().lower()
                if normalized:
                    return normalized
            except Exception:
                pass
        return "unknown"

    def _capture_handoff_force_close_enabled(self, assistant: CoreAssistant) -> bool:
        voice_input_cfg = assistant.settings.get("voice_input", {})
        configured = voice_input_cfg.get("capture_handoff_force_close")
        if configured is None:
            return False
        return bool(configured)

    def _safe_release_runtime_component(
        self,
        assistant: CoreAssistant,
        component: Any | None,
        label: str,
    ) -> tuple[bool, str]:
        if component is None:
            return False, "none"

        release_method = getattr(component, "release_capture_ownership", None)
        if callable(release_method):
            try:
                release_result = release_method()
                released = True if release_result is None else bool(release_result)
                if released:
                    append_log(f"Soft-released runtime input component for capture handoff: {label}")
                    return True, "soft"
            except Exception as error:
                append_log(f"Failed to soft-release runtime input component {label}: {error}")

        if not self._capture_handoff_force_close_enabled(assistant):
            return False, "none"

        closed = self._safe_close_runtime_component(component, label)
        return closed, "close" if closed else "none"







    def _safe_close_runtime_component(self, component: Any | None, label: str) -> bool:
        if component is None:
            return False

        close_method = getattr(component, "close", None)
        if not callable(close_method):
            return False

        stream_before = getattr(component, "_stream", None)

        try:
            close_method()
            if stream_before is not None:
                append_log(f"Closed runtime input component for capture handoff: {label}")
            return True
        except Exception as error:
            append_log(f"Failed to close runtime input component {label}: {error}")
            return False

    def _backend_status_for(self, assistant: CoreAssistant, component: str) -> Any | None:
        return getattr(assistant, "backend_statuses", {}).get(component)

    def _wake_backend_shares_voice_input(
        self,
        assistant: CoreAssistant,
        wake_backend: Any | None = None,
    ) -> bool:
        voice_in = getattr(assistant, "voice_in", None)
        if voice_in is None:
            return False

        backend = wake_backend
        if backend is None:
            backend, _ = self._resolve_wake_backend(assistant)

        if backend is None:
            return False
        if backend is voice_in:
            return True

        wrapped_voice_input = getattr(backend, "voice_input", None)
        if wrapped_voice_input is voice_in:
            return True

        wake_status = self._backend_status_for(assistant, "wake_gate")
        selected_backend = str(getattr(wake_status, "selected_backend", "") or "").strip().lower()
        return selected_backend == "compatibility_voice_input"

    def _wake_backend_is_usable(
        self,
        assistant: CoreAssistant,
        wake_backend: Any | None,
    ) -> bool:
        if wake_backend is None:
            return False

        wake_status = self._backend_status_for(assistant, "wake_gate")
        if wake_status is not None and not bool(getattr(wake_status, "ok", False)):
            return False

        class_name = wake_backend.__class__.__name__.lower()
        if class_name == "nullwakegate":
            return False

        listen_method = getattr(wake_backend, "listen_for_wake_phrase", None)
        return callable(listen_method)

    def _resolve_wake_backend(self, assistant: CoreAssistant) -> tuple[Any | None, str]:
        wake_gate = getattr(assistant, "wake_gate", None)
        if wake_gate is None:
            runtime = getattr(assistant, "runtime", None)
            wake_gate = getattr(runtime, "wake_gate", None)

        if self._wake_backend_is_usable(assistant, wake_gate):
            return wake_gate, "runtime.wake_gate"

        voice_in = getattr(assistant, "voice_in", None)
        if voice_in is not None and callable(getattr(voice_in, "listen_for_wake_phrase", None)):
            return voice_in, "voice_input.listen_for_wake_phrase"

        if voice_in is not None and any(
            callable(getattr(voice_in, method_name, None))
            for method_name in ("listen", "listen_once", "listen_for_command")
        ):
            return voice_in, "voice_input.listen"

        return None, "voice_input.listen"

    def _store_last_result(
        self,
        assistant: CoreAssistant,
        result: CaptureOwnershipResult,
    ) -> None:
        assistant._last_capture_handoff = {
            "target_owner": result.target_owner,
            "applied_owner": result.applied_owner,
            "wake_backend_label": result.wake_backend_label,
            "wake_backend_released": result.wake_backend_released,
            "wake_backend_release_mode": result.wake_backend_release_mode,
            "voice_input_released": result.voice_input_released,
            "voice_input_release_mode": result.voice_input_release_mode,
            "blocked_observed": result.blocked_observed,
            "wait_completed": result.wait_completed,
            "wait_elapsed_ms": result.wait_elapsed_ms,
            "settle_seconds": result.settle_seconds,
        }


__all__ = ["CaptureOwnershipResult", "CaptureOwnershipService"]