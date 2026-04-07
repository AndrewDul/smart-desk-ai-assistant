from __future__ import annotations

import threading
from typing import Any

from modules.system.utils import append_log


class ThinkingAckHandle:
    def __init__(
        self,
        *,
        voice_output: Any,
        voice_session: Any,
        delay_seconds: float,
        language: str,
        detail: str,
    ) -> None:
        self.voice_output = voice_output
        self.voice_session = voice_session
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.language = str(language or "en").strip().lower() or "en"
        self.detail = str(detail or "thinking_ack").strip()

        self._cancel_event = threading.Event()
        self._started_event = threading.Event()
        self._finished_event = threading.Event()

        self._thread = threading.Thread(
            target=self._run,
            name="thinking-ack",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            if self._cancel_event.wait(self.delay_seconds):
                return

            builder = getattr(self.voice_session, "build_thinking_acknowledgement", None)
            if not callable(builder):
                return

            phrase = str(builder(self.language) or "").strip()
            if not phrase:
                return

            self._started_event.set()
            self.voice_session.set_state("thinking", detail=self.detail)
            self.voice_output.speak(phrase, language=self.language)

            append_log(
                f"Thinking acknowledgement spoken: lang={self.language}, detail={self.detail}, text={phrase}"
            )
        except Exception as error:
            append_log(f"Thinking acknowledgement failed: {error}")
        finally:
            self._finished_event.set()

    def cancel(self, join_timeout_seconds: float = 0.2) -> None:
        self._cancel_event.set()
        if self._thread.is_alive():
            self._thread.join(max(0.0, float(join_timeout_seconds)))

    def has_started(self) -> bool:
        return self._started_event.is_set()

    def wait_until_finished(self, timeout_seconds: float | None = None) -> bool:
        return self._finished_event.wait(timeout_seconds)


class ThinkingAckService:
    def __init__(
        self,
        *,
        voice_output: Any,
        voice_session: Any,
        delay_seconds: float = 1.5,
    ) -> None:
        self.voice_output = voice_output
        self.voice_session = voice_session
        self.delay_seconds = max(0.0, float(delay_seconds))

    def arm(self, *, language: str, detail: str) -> ThinkingAckHandle:
        return ThinkingAckHandle(
            voice_output=self.voice_output,
            voice_session=self.voice_session,
            delay_seconds=self.delay_seconds,
            language=language,
            detail=detail,
        )