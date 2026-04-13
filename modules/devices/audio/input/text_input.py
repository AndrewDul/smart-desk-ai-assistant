from __future__ import annotations

import logging
import os
import re
import sys
import time
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


LOGGER = logging.getLogger(__name__)


class TextInput:
    """
    Developer-facing text input backend.

    This backend is intentionally simple, but still follows the same
    behavioural contract as voice input:
    - optional wake gate prompt
    - assistant-output block awareness
    - normalized wake phrase matching
    - clean command text normalization
    """

    DEFAULT_WAKE_PROMPT = "Wake> "
    DEFAULT_COMMAND_PROMPT = "You> "

    WAKE_PHRASE_VARIANTS = (
        "nexa",
        "hey nexa",
        "ok nexa",
        "okay nexa",
        "nexta",
        "hey nexta",
        "ok nexta",
        "okay nexta",
        "neksa",
        "hey neksa",
        "ok neksa",
        "okay neksa",
    )

    def __init__(
        self,
        *,
        wake_prompt: str = DEFAULT_WAKE_PROMPT,
        command_prompt: str = DEFAULT_COMMAND_PROMPT,
        strip_text: bool = True,
        normalize_internal_whitespace: bool = True,
        enforce_wake_phrase_match: bool = True,
    ) -> None:
        self.wake_prompt = str(wake_prompt)
        self.command_prompt = str(command_prompt)
        self.strip_text = bool(strip_text)
        self.normalize_internal_whitespace = bool(normalize_internal_whitespace)
        self.enforce_wake_phrase_match = bool(enforce_wake_phrase_match)

        self.audio_coordinator: AssistantAudioCoordinator | None = None
        self._non_interactive_logged = False

        LOGGER.info(
            "TextInput prepared: wake_prompt=%r, command_prompt=%r, enforce_wake_phrase_match=%s",
            self.wake_prompt,
            self.command_prompt,
            self.enforce_wake_phrase_match,
        )

    def _stdin_is_interactive(self) -> bool:
        stdin = getattr(sys, "stdin", None)
        if stdin is None:
            return False

        is_tty = getattr(stdin, "isatty", None)
        if not callable(is_tty):
            return False

        try:
            return bool(is_tty())
        except Exception:
            return False

    def _read_line(self, prompt: str, *, timeout: float | None = None) -> str | None:
        if not self._stdin_is_interactive():
            runtime_mode = str(os.getenv("NEXA_RUNTIME_MODE", "") or "").strip().lower()

            if not self._non_interactive_logged:
                LOGGER.warning(
                    "TextInput is running without an interactive stdin. "
                    "Prompts are disabled to avoid Wake>/You> spam. runtime_mode=%s",
                    runtime_mode or "unknown",
                )
                self._non_interactive_logged = True

            if timeout is not None:
                try:
                    time.sleep(max(0.05, float(timeout)))
                except Exception:
                    time.sleep(0.25)
            else:
                time.sleep(0.25)

            return None

        try:
            value = input(prompt)
        except EOFError:
            return None
        except KeyboardInterrupt:
            raise

        normalized = self._normalize_text(value)
        return normalized or None

    def set_audio_coordinator(
        self,
        audio_coordinator: AssistantAudioCoordinator | None,
    ) -> None:
        self.audio_coordinator = audio_coordinator

    def _input_blocked_by_assistant_output(self) -> bool:
        if self.audio_coordinator is None:
            return False

        try:
            return bool(self.audio_coordinator.input_blocked())
        except Exception:
            return False

    def _normalize_text(self, text: str) -> str:
        normalized = str(text)

        if self.strip_text:
            normalized = normalized.strip()

        if self.normalize_internal_whitespace:
            normalized = re.sub(r"\s+", " ", normalized)

        return normalized

    @staticmethod
    def _normalize_ascii(text: str) -> str:
        lowered = str(text or "").lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def _matches_wake_phrase(self, text: str) -> bool:
        normalized = self._normalize_ascii(text)
        if not normalized:
            return False

        if normalized in self.WAKE_PHRASE_VARIANTS:
            return True

        for variant in self.WAKE_PHRASE_VARIANTS:
            if normalized == variant:
                return True

        return False

    def listen(
        self,
        timeout: float = 8.0,
        debug: bool = False,
    ) -> str | None:
        del debug

        if self._input_blocked_by_assistant_output():
            LOGGER.debug("TextInput command listen skipped because assistant output is active.")
            return None

        text = self._read_line(self.command_prompt, timeout=timeout)
        if text:
            LOGGER.info("TextInput command received: %s", text)
        return text

    def listen_once(
        self,
        timeout: float = 8.0,
        debug: bool = False,
    ) -> str | None:
        return self.listen(timeout=timeout, debug=debug)

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.4,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        if not ignore_audio_block and self._input_blocked_by_assistant_output():
            LOGGER.debug("TextInput wake listen skipped because assistant output is active.")
            return None

        text = self._read_line(self.wake_prompt, timeout=timeout)
        if text is None:
            return None

        if not self.enforce_wake_phrase_match:
            if debug:
                print(f"Text wake bypass accepted: {text}")
            LOGGER.info("TextInput wake accepted without strict matching: %s", text)
            return text

        if self._matches_wake_phrase(text):
            if debug:
                print(f"Text wake accepted: {text}")
            LOGGER.info("TextInput wake accepted: %s", text)
            return "nexa"

        if debug:
            print(f"Text wake rejected: {text}")
        LOGGER.debug("TextInput wake rejected: %s", text)
        return None

    def close(self) -> None:
        LOGGER.debug("TextInput close called.")


__all__ = ["TextInput"]