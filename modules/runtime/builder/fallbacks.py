from __future__ import annotations

from typing import Any


class SilentVoiceOutput:
    """
    Safe no-audio fallback.

    This backend reports success so the higher presentation layer can keep
    running normally even when TTS is disabled or unavailable.
    """

    def __init__(self) -> None:
        self.audio_coordinator = None
        self.messages: list[dict[str, Any]] = []

    def set_audio_coordinator(self, audio_coordinator: Any | None) -> None:
        self.audio_coordinator = audio_coordinator

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
        output_hold_seconds: float | None = None,
        latency_profile: str | None = None,
    ) -> bool:
        del prepare_next
        self.messages.append(
            {
                "text": str(text),
                "language": language,
                "output_hold_seconds": output_hold_seconds,
                "latency_profile": latency_profile,
            }
        )
        return True

    def prepare_speech(self, text: str, language: str | None = None) -> None:
        self.messages.append(
            {
                "prefetch_text": str(text),
                "language": language,
            }
        )

    def stop_playback(self) -> None:
        return None

    def clear_stop_request(self) -> None:
        return None


class NullDisplay:
    """
    Safe display fallback used when the physical display is disabled or fails.
    """

    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.developer_overlays: list[dict[str, Any]] = []
        self.closed = False

    def show_block(self, title: str, lines: list[str], duration: float = 10.0) -> None:
        self.blocks.append(
            {
                "title": str(title),
                "lines": [str(line) for line in lines],
                "duration": float(duration),
            }
        )

    def show_status(
        self,
        state: dict[str, Any],
        timer_status: dict[str, Any],
        duration: float = 10.0,
    ) -> None:
        self.blocks.append(
            {
                "title": "STATUS",
                "lines": [
                    f"focus: {'ON' if state.get('focus_mode') else 'OFF'}",
                    f"break: {'ON' if state.get('break_mode') else 'OFF'}",
                    f"timer: {state.get('current_timer') or 'none'}",
                    f"run: {'ON' if timer_status.get('running') else 'OFF'}",
                ],
                "duration": float(duration),
            }
        )

    def set_developer_overlay(self, title: str, lines: list[str]) -> None:
        self.developer_overlays.append(
            {
                "title": str(title),
                "lines": [str(line) for line in lines],
            }
        )

    def clear_overlay(self) -> None:
        return None

    def clear_developer_overlay(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class NullWakeGate:
    """
    No-op wake gate used only when wake-word listening is intentionally disabled.
    """

    def __init__(self) -> None:
        self.audio_coordinator = None

    def set_audio_coordinator(self, audio_coordinator: Any | None) -> None:
        self.audio_coordinator = audio_coordinator

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        del timeout, debug, ignore_audio_block
        return None

    def close(self) -> None:
        return None



class NullAiBroker:
    """
    Safe broker fallback used when AI broker initialization is disabled or fails.
    """

    def _payload(self) -> dict[str, object]:
        return {
            "mode": "idle_baseline",
            "owner": "balanced",
            "profile": {
                "heavy_lane_cadence_hz": 0.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "normal",
                "notes": [],
            },
            "recovery_window_active": False,
            "recovery_until_monotonic": None,
            "last_reason": "null_ai_broker",
            "last_error": None,
            "vision_control_available": False,
            "metadata": {
                "vision_profile_applied": False,
                "supported_modes": [],
            },
        }

    def enter_idle_baseline(self, *, reason: str = "") -> dict[str, object]:
        del reason
        return self._payload()

    def enter_conversation_answer_mode(self, *, reason: str = "") -> dict[str, object]:
        del reason
        return self._payload()

    def enter_vision_action_mode(self, *, reason: str = "") -> dict[str, object]:
        del reason
        return self._payload()

    def enter_focus_sentinel_mode(self, *, reason: str = "") -> dict[str, object]:
        del reason
        return self._payload()

    def enter_recovery_window(
        self,
        *,
        reason: str = "",
        return_to_mode=None,
        seconds: float | None = None,
    ) -> dict[str, object]:
        del reason, return_to_mode, seconds
        return self._payload()

    def tick(self) -> dict[str, object]:
        return self._payload()

    def snapshot(self) -> dict[str, object]:
        return self._payload()

    def status(self) -> dict[str, object]:
        return self._payload()

    def close(self) -> None:
        return None


class NullVisionBackend:
    """
    Placeholder backend until the camera stack is fully enabled.
    """

    def start(self) -> None:
        return None

    def latest_observation(self, *, force_refresh: bool = True) -> Any:
        del force_refresh
        return None

    def status(self) -> dict[str, object]:
        return {
            "ok": False,
            "enabled": False,
            "backend": "null_vision",
            "detail": "Vision backend disabled or unavailable.",
            "last_capture_available": False,
            "last_error": None,
        }

    def object_detector_status(self) -> dict[str, object] | None:
        return None

    def set_object_detection_cadence_hz(self, hz: float) -> bool:
        del hz
        return False

    def pause_object_detection(self) -> bool:
        return False

    def resume_object_detection(self, hz: float | None = None) -> bool:
        del hz
        return False

    def close(self) -> None:
        return None


class NullPanTiltBackend:
    """Placeholder backend until the pan/tilt stack is enabled."""

    def move_direction(self, direction: str) -> dict[str, object]:
        return {"ok": False, "error": f"Pan/tilt disabled. Direction={direction}"}

    def status(self) -> dict[str, object]:
        return {"ok": False, "error": "Pan/tilt disabled."}

    def close(self) -> None:
        return None


class NullMobilityBackend:
    """
    Placeholder backend until the mobile base stack is fully enabled.
    """

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None


__all__ = [
    "NullAiBroker",
    "NullDisplay",
    "NullMobilityBackend",
    "NullPanTiltBackend",
    "NullVisionBackend",
    "NullWakeGate",
    "SilentVoiceOutput",
]