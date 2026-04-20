from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


class FakeVoiceOutput:
    def __init__(self, *, supports_prepare_next: bool = True) -> None:
        self.supports_prepare_next = supports_prepare_next
        self.speak_calls: list[dict[str, Any]] = []
        self.prepare_calls: list[tuple[str, str | None]] = []
        self.stop_calls = 0
        self.audio_coordinator: Any | None = None

    def prepare_speech(self, text: str, language: str | None = None) -> None:
        self.prepare_calls.append((str(text), language))

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
        output_hold_seconds: float | None = None,
    ) -> bool:
        if not self.supports_prepare_next and prepare_next is not None:
            raise TypeError("prepare_next not supported")

        self.speak_calls.append(
            {
                "text": str(text),
                "language": language,
                "prepare_next": prepare_next,
                "output_hold_seconds": output_hold_seconds,
            }
        )
        return True

    def stop_playback(self) -> None:
        self.stop_calls += 1


class FakeDisplay:
    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.developer_overlays: list[dict[str, Any]] = []
        self.clear_developer_overlay_calls = 0

    def show_block(self, title: str, lines: list[str], duration: float | None = None) -> None:
        self.blocks.append(
            {
                "title": str(title),
                "lines": list(lines),
                "duration": duration,
            }
        )

    def set_developer_overlay(self, title: str, lines: list[str]) -> None:
        self.developer_overlays.append(
            {
                "title": str(title),
                "lines": list(lines),
            }
        )

    def clear_developer_overlay(self) -> None:
        self.clear_developer_overlay_calls += 1


@dataclass(slots=True)
class FakeCoordinatorSnapshot:
    last_output_started_monotonic: float = 0.0


class FakeAudioCoordinator:
    def __init__(
        self,
        *,
        active_output: bool = False,
        blocked: bool = False,
        output_age_seconds: float = 1.0,
    ) -> None:
        self._active_output = bool(active_output)
        self._blocked = bool(blocked)
        self._last_output_started_monotonic = time.monotonic() - max(
            0.0,
            float(output_age_seconds),
        )
        self.post_speech_hold_seconds = 0.32
        self.listen_resume_poll_seconds = 0.01

    def has_active_output(self) -> bool:
        return self._active_output

    def input_blocked(self) -> bool:
        return self._blocked

    def snapshot(self) -> FakeCoordinatorSnapshot:
        return FakeCoordinatorSnapshot(
            last_output_started_monotonic=self._last_output_started_monotonic,
        )

    def begin_assistant_output(self, *, source: str, text_preview: str) -> str:
        self._active_output = True
        self._blocked = True
        self._last_output_started_monotonic = time.monotonic()
        return f"token:{source}:{text_preview[:8]}"

    def end_assistant_output(self, token: str | None, *, hold_seconds: float = 0.0) -> None:
        del token, hold_seconds
        self._active_output = False
        self._blocked = False


class FakeWakeBackend:
    def __init__(self, result: str | None = "nexa") -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def listen_for_wake_phrase(
        self,
        *,
        timeout: float,
        debug: bool,
        ignore_audio_block: bool,
    ) -> str | None:
        self.calls.append(
            {
                "timeout": timeout,
                "debug": debug,
                "ignore_audio_block": ignore_audio_block,
            }
        )
        return self.result


class FakeBenchmarkRecorder:
    def __init__(self) -> None:
        self.wake_sources: list[str] = []

    def note_wake_detected(self, *, source: str) -> None:
        self.wake_sources.append(str(source))