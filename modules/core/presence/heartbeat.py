from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)


def _presence_log(message: str) -> None:
    LOGGER.info(message)
    try:
        from modules.system.utils import append_log

        append_log(message)
    except Exception:
        pass


@dataclass(frozen=True, slots=True)
class PresenceHeartbeatMetrics:
    heartbeat_count: int = 0
    first_heartbeat_ms: float = 0.0
    cancelled: bool = False
    cancelled_reason: str = ""
    skipped_reason_count: int = 0


class PresenceHeartbeatManager:
    """
    Non-blocking presence heartbeat for NeXa.

    Speaks short cached status phrases on its own daemon thread while a long
    operation (LLM/TTS/ASR) is running.  Cancels immediately when the real
    response becomes ready.

    Design invariants:
    - start() is non-blocking; caller returns instantly.
    - cancel() sets _answer_ready; if a phrase is mid-playback it asks the
      voice output to stop playback so the real response can acquire TTS quickly.
    - cancel() is idempotent: safe to call more than once.
    - All fields accessed from outside are read-only after start().
    """

    HEARTBEAT_PHRASES_EN: tuple[str, ...] = (
        "I'm still working on that.",
        "I'm checking it locally now.",
        "This is taking a moment, but I'm still here.",
        "I'm putting the answer together.",
        "Good question, still thinking locally.",
    )
    HEARTBEAT_PHRASES_PL: tuple[str, ...] = (
        "Daj mi chwilę, pracuję nad tym.",
        "Dalej to sprawdzam.",
        "Składam odpowiedź lokalnie.",
        "To chwilę trwa, ale jestem przy tym.",
        "Już przygotowuję odpowiedź.",
    )

    def __init__(
        self,
        *,
        voice_output: Any,
        language: str = "en",
        first_delay_s: float = 1.0,
        repeat_interval_s: float = 2.5,
        max_heartbeats: int = 8,
        join_timeout_s: float = 0.12,
    ) -> None:
        self._voice_output = voice_output
        lang = str(language or "en").strip().lower()
        self._language = lang if lang in {"pl", "en"} else "en"
        self._first_delay_s = max(0.0, float(first_delay_s))
        self._repeat_interval_s = max(0.01, float(repeat_interval_s))
        self._max_heartbeats = max(1, int(max_heartbeats))
        self._join_timeout_s = max(0.0, float(join_timeout_s))

        self._answer_ready = threading.Event()
        self._currently_speaking = threading.Event()
        self._start_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._thread: threading.Thread | None = None

        self._started_at: float = 0.0
        self._heartbeat_count: int = 0
        self._first_heartbeat_ms: float = 0.0
        self._cancelled_reason: str = ""
        self._skipped_reason_count: int = 0
        self._phrase_index: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None:
                return
            self._started_at = time.monotonic()
            _presence_log(
                "[presence-heartbeat] started "
                f"first_delay_ms={self._first_delay_s * 1000.0:.1f} "
                f"repeat_ms={self._repeat_interval_s * 1000.0:.1f} "
                f"lang={self._language}"
            )
            thread = threading.Thread(
                target=self._run,
                name="nexa-presence-heartbeat",
                daemon=True,
            )
            self._thread = thread
            thread.start()

    def cancel(self, *, reason: str = "cancelled") -> None:
        first_cancel = not self._answer_ready.is_set()
        self._answer_ready.set()
        safe_reason = str(reason or "cancelled").strip() or "cancelled"
        with self._metrics_lock:
            if not self._cancelled_reason:
                self._cancelled_reason = safe_reason

        if first_cancel:
            _presence_log(f"[presence-heartbeat] cancelled reason={safe_reason}")
            metrics = self.metrics()
            _presence_log(
                "[presence-heartbeat] metrics "
                f"count={metrics.heartbeat_count} "
                f"first_ms={metrics.first_heartbeat_ms:.1f} "
                f"cancelled={metrics.cancelled} "
                f"skipped={metrics.skipped_reason_count} "
                f"reason={metrics.cancelled_reason or '-'}"
            )

        if self._currently_speaking.is_set():
            stop = getattr(self._voice_output, "stop_presence_playback", None)
            if not callable(stop):
                stop = getattr(self._voice_output, "stop_playback", None)
            if callable(stop):
                try:
                    stop()
                except Exception as error:
                    LOGGER.debug("[heartbeat] stop_playback error: %s", error)

            thread = self._thread
            if thread is not None and thread.is_alive() and self._join_timeout_s > 0.0:
                thread.join(timeout=self._join_timeout_s)

    @property
    def heartbeat_count(self) -> int:
        with self._metrics_lock:
            return self._heartbeat_count

    @property
    def first_heartbeat_ms(self) -> float:
        with self._metrics_lock:
            return self._first_heartbeat_ms

    @property
    def was_cancelled(self) -> bool:
        return self._answer_ready.is_set()

    def metrics(self) -> PresenceHeartbeatMetrics:
        with self._metrics_lock:
            return PresenceHeartbeatMetrics(
                heartbeat_count=self._heartbeat_count,
                first_heartbeat_ms=self._first_heartbeat_ms,
                cancelled=self._answer_ready.is_set(),
                cancelled_reason=self._cancelled_reason,
                skipped_reason_count=self._skipped_reason_count,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_phrase(self) -> str:
        pool = (
            self.HEARTBEAT_PHRASES_PL
            if self._language == "pl"
            else self.HEARTBEAT_PHRASES_EN
        )
        phrase = pool[self._phrase_index % len(pool)]
        self._phrase_index += 1
        return phrase

    def _mark_first_heartbeat(self) -> None:
        with self._metrics_lock:
            if self._first_heartbeat_ms > 0.0:
                return
            self._first_heartbeat_ms = max(
                0.0, (time.monotonic() - self._started_at) * 1000.0
            )
            first_heartbeat_ms = self._first_heartbeat_ms

        _presence_log(
            "[presence-heartbeat] first "
            f"first_ms={first_heartbeat_ms:.1f} lang={self._language}"
        )

    def _record_spoken(self) -> int:
        with self._metrics_lock:
            self._heartbeat_count += 1
            return self._heartbeat_count

    def _record_skipped(self) -> int:
        with self._metrics_lock:
            self._skipped_reason_count += 1
            return self._skipped_reason_count

    def _speak_phrase(self, phrase: str) -> tuple[bool, str]:
        speak_presence = getattr(self._voice_output, "speak_presence", None)
        speak = speak_presence if callable(speak_presence) else getattr(self._voice_output, "speak", None)
        if not callable(speak) or self._answer_ready.is_set():
            return False, "unavailable"

        self._currently_speaking.set()
        try:
            try:
                result = speak(phrase, self._language)
            except TypeError:
                result = speak(phrase, language=self._language)
            if isinstance(result, tuple):
                ok = bool(result[0])
                reason = str(result[1] if len(result) > 1 else "" or "").strip()
                return ok, reason or ("spoken" if ok else "skipped")
            return bool(result), "spoken" if result else "skipped"
        except Exception as error:
            LOGGER.debug("[heartbeat] speak error: %s", error)
            return False, "error"
        finally:
            self._currently_speaking.clear()

    def _run(self) -> None:
        if self._answer_ready.wait(timeout=self._first_delay_s):
            return

        for _ in range(self._max_heartbeats):
            if self._answer_ready.is_set():
                return

            phrase = self._next_phrase()
            self._mark_first_heartbeat()

            if self._answer_ready.is_set():
                return

            spoken, skip_reason = self._speak_phrase(phrase)
            if spoken:
                count = self._record_spoken()
                _presence_log(
                    "[presence-heartbeat] spoken "
                    f"index={count} text={phrase!r} lang={self._language}"
                )
            else:
                self._record_skipped()
                _presence_log(f"[presence-heartbeat] skipped reason={skip_reason}")

            if self._answer_ready.wait(timeout=self._repeat_interval_s):
                return

        metrics = self.metrics()
        _presence_log(
            "[presence-heartbeat] metrics "
            f"count={metrics.heartbeat_count} "
            f"first_ms={metrics.first_heartbeat_ms:.1f} "
            f"cancelled={metrics.cancelled} "
            f"skipped={metrics.skipped_reason_count} "
            f"reason={metrics.cancelled_reason or '-'}"
        )


__all__ = ["PresenceHeartbeatManager", "PresenceHeartbeatMetrics"]
