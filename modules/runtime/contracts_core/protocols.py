from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .understanding import TranscriptRequest, TranscriptResult, WakeDetectionResult


@runtime_checkable
class SpeechInputBackend(Protocol):
    """Contract implemented by voice or text input backends."""

    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        ...

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class RichSpeechInputBackend(SpeechInputBackend, Protocol):
    """Optional richer STT contract used by the final NeXa 2.0 pipeline."""

    def transcribe(self, request: TranscriptRequest) -> TranscriptResult | None:
        ...


@runtime_checkable
class WakeGateBackend(Protocol):
    """Contract implemented by wake-word gates."""

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class RichWakeGateBackend(WakeGateBackend, Protocol):
    """Optional richer wake contract used by the final NeXa 2.0 pipeline."""

    def detect_wake(
        self,
        *,
        timeout_seconds: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> WakeDetectionResult | None:
        ...


@runtime_checkable
class SpeechOutputBackend(Protocol):
    """Contract implemented by TTS backends."""

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
    ) -> bool:
        ...

    def prepare_speech(self, text: str, language: str | None = None) -> None:
        ...

    def stop_playback(self) -> None:
        ...

    def clear_stop_request(self) -> None:
        ...


@runtime_checkable
class DisplayBackend(Protocol):
    """Contract implemented by display backends."""

    def show_block(
        self,
        title: str,
        lines: list[str],
        duration: float = 10.0,
    ) -> None:
        ...

    def show_status(
        self,
        state: dict[str, Any],
        timer_status: dict[str, Any],
        duration: float = 10.0,
    ) -> None:
        ...

    def clear_overlay(self) -> None:
        ...

    def close(self) -> None:
        ...
    
    def set_developer_overlay(self, title: str, lines: list[str]) -> None:
        ...

    def clear_developer_overlay(self) -> None:
        ...

__all__ = [
    "DisplayBackend",
    "RichSpeechInputBackend",
    "RichWakeGateBackend",
    "SpeechInputBackend",
    "SpeechOutputBackend",
    "WakeGateBackend",
]