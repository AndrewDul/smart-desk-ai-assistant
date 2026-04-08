from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)


ThinkingAckCallback = Callable[["ThinkingAckHandle"], None]
InterruptProbe = Callable[[], bool]


@dataclass(slots=True)
class ThinkingAckSnapshot:
    active: bool
    started: bool
    spoken: bool
    cancelled: bool
    finished: bool
    language: str
    detail: str


class ThinkingAckHandle:
    """
    Deferred spoken acknowledgement used when NeXa needs a moment before the
    full answer is ready.

    Behaviour goals:
    - do not speak if the operation finishes quickly
    - do not overlap existing assistant output
    - allow safe cancellation from any thread
    - keep state queryable for orchestration and tests
    """

    def __init__(
        self,
        *,
        voice_output: Any,
        phrase_builder: Callable[[str], str | None],
        delay_seconds: float,
        language: str,
        detail: str,
        on_finished: ThinkingAckCallback | None = None,
        on_started: Callable[[str], None] | None = None,
        interrupt_requested: InterruptProbe | None = None,
    ) -> None:
        self.voice_output = voice_output
        self.phrase_builder = phrase_builder
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.language = self._normalize_language(language)
        self.detail = str(detail or "thinking_ack").strip() or "thinking_ack"
        self.on_finished = on_finished
        self.on_started = on_started
        self.interrupt_requested = interrupt_requested

        self._cancel_event = threading.Event()
        self._started_event = threading.Event()
        self._spoken_event = threading.Event()
        self._finished_event = threading.Event()

        self._thread = threading.Thread(
            target=self._run,
            name=f"thinking-ack-{self.detail}",
            daemon=True,
        )
        self._thread.start()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        return normalized if normalized in {"pl", "en"} else "en"

    def _run(self) -> None:
        try:
            if self._cancel_event.wait(self.delay_seconds):
                return

            if self._cancelled() or self._interrupted():
                return

            if self._assistant_output_already_active():
                LOGGER.info(
                    "Thinking acknowledgement skipped because assistant output is already active: detail=%s",
                    self.detail,
                )
                return

            phrase = str(self.phrase_builder(self.language) or "").strip()
            if not phrase:
                LOGGER.debug(
                    "Thinking acknowledgement skipped because phrase builder returned empty text: detail=%s",
                    self.detail,
                )
                return

            if self._cancelled() or self._interrupted():
                return

            self._started_event.set()

            if callable(self.on_started):
                try:
                    self.on_started(self.detail)
                except Exception as error:
                    LOGGER.warning("Thinking acknowledgement on_started callback failed: %s", error)

            spoken_ok = self._speak_phrase(phrase)
            if spoken_ok:
                self._spoken_event.set()
                LOGGER.info(
                    "Thinking acknowledgement spoken: lang=%s, detail=%s, text=%s",
                    self.language,
                    self.detail,
                    phrase,
                )
            else:
                if not self._cancelled() and not self._interrupted():
                    LOGGER.info(
                        "Thinking acknowledgement attempted but not spoken successfully: "
                        "lang=%s, detail=%s, text=%s",
                        self.language,
                        self.detail,
                        phrase,
                    )
        except Exception as error:
            LOGGER.exception("Thinking acknowledgement failed: %s", error)
        finally:
            self._finished_event.set()
            if callable(self.on_finished):
                try:
                    self.on_finished(self)
                except Exception as error:
                    LOGGER.warning("Thinking acknowledgement cleanup failed: %s", error)

    def _assistant_output_already_active(self) -> bool:
        coordinator = getattr(self.voice_output, "audio_coordinator", None)
        if coordinator is None:
            return False

        active_method = getattr(coordinator, "assistant_output_active", None)
        if callable(active_method):
            try:
                return bool(active_method())
            except Exception:
                pass

        blocked_method = getattr(coordinator, "input_blocked", None)
        if callable(blocked_method):
            try:
                return bool(blocked_method())
            except Exception:
                return False

        return False

    def _speak_phrase(self, phrase: str) -> bool:
        speak_method = getattr(self.voice_output, "speak", None)
        if not callable(speak_method):
            return False

        try:
            return bool(speak_method(phrase, language=self.language))
        except TypeError:
            return bool(speak_method(phrase))

    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _interrupted(self) -> bool:
        if not callable(self.interrupt_requested):
            return False
        try:
            return bool(self.interrupt_requested())
        except Exception:
            return False

    def cancel(self, join_timeout_seconds: float = 0.2) -> None:
        self._cancel_event.set()
        if self._thread.is_alive():
            self._thread.join(max(0.0, float(join_timeout_seconds)))

    def has_started(self) -> bool:
        return self._started_event.is_set()

    def was_spoken(self) -> bool:
        return self._spoken_event.is_set()

    def is_finished(self) -> bool:
        return self._finished_event.is_set()

    def snapshot(self) -> ThinkingAckSnapshot:
        return ThinkingAckSnapshot(
            active=not self._finished_event.is_set(),
            started=self._started_event.is_set(),
            spoken=self._spoken_event.is_set(),
            cancelled=self._cancel_event.is_set(),
            finished=self._finished_event.is_set(),
            language=self.language,
            detail=self.detail,
        )

    def wait_until_finished(self, timeout_seconds: float | None = None) -> bool:
        return self._finished_event.wait(timeout_seconds)


class ThinkingAckService:
    """
    Single-active thinking acknowledgement orchestrator.

    It keeps only one active handle at a time and is safe to use from routing,
    tool execution, and dialogue orchestration code.
    """

    def __init__(
        self,
        *,
        voice_output: Any,
        voice_session: Any | None = None,
        delay_seconds: float = 1.5,
        interrupt_requested: InterruptProbe | None = None,
    ) -> None:
        self.voice_output = voice_output
        self.voice_session = voice_session
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.interrupt_requested = interrupt_requested

        self._lock = threading.RLock()
        self._active_handle: ThinkingAckHandle | None = None

    def arm(self, *, language: str, detail: str) -> ThinkingAckHandle:
        with self._lock:
            if self._active_handle is not None:
                self._active_handle.cancel(join_timeout_seconds=0.05)
                self._active_handle = None

            handle = ThinkingAckHandle(
                voice_output=self.voice_output,
                phrase_builder=self._build_phrase,
                delay_seconds=self.delay_seconds,
                language=language,
                detail=detail,
                on_finished=self._handle_finished,
                on_started=self._handle_started,
                interrupt_requested=self.interrupt_requested,
            )
            self._active_handle = handle
            return handle

    def cancel_active(self) -> None:
        with self._lock:
            handle = self._active_handle
            self._active_handle = None

        if handle is not None:
            handle.cancel()

    def active_handle(self) -> ThinkingAckHandle | None:
        with self._lock:
            return self._active_handle

    def _handle_started(self, detail: str) -> None:
        if self.voice_session is None:
            return

        set_state = getattr(self.voice_session, "set_state", None)
        if callable(set_state):
            try:
                set_state("thinking", detail=detail)
            except Exception as error:
                LOGGER.warning("Thinking acknowledgement could not update voice session state: %s", error)

    def _handle_finished(self, handle: ThinkingAckHandle) -> None:
        with self._lock:
            if self._active_handle is handle:
                self._active_handle = None

    def _build_phrase(self, language: str) -> str | None:
        if self.voice_session is not None:
            builder = getattr(self.voice_session, "build_thinking_acknowledgement", None)
            if callable(builder):
                try:
                    phrase = str(builder(language) or "").strip()
                    if phrase:
                        return phrase
                except Exception as error:
                    LOGGER.warning("Thinking acknowledgement phrase builder failed: %s", error)

        if language == "pl":
            return "Już sprawdzam."
        return "Let me check."

    def snapshot(self) -> ThinkingAckSnapshot | None:
        with self._lock:
            if self._active_handle is None:
                return None
            return self._active_handle.snapshot()


__all__ = [
    "ThinkingAckHandle",
    "ThinkingAckService",
    "ThinkingAckSnapshot",
]