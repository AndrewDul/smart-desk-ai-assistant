from __future__ import annotations

import re

from modules.runtime.contracts import SpeechInputBackend


class CompatibilityWakeGate:
    """
    Wake compatibility layer that reuses the main voice input backend.

    This is the stable single-capture mode:
    - there is only one input owner
    - standby wake and active command capture both flow through voice_input
    - dedicated openWakeWord is not required to keep the runtime usable
    """

    _WAKE_ALIASES = (
        "nexa",
        "nexta",
        "neksa",
        "nexaah",
        "nex",
    )

    def __init__(self, voice_input: SpeechInputBackend) -> None:
        self.voice_input = voice_input
        self.audio_coordinator = None

    def set_audio_coordinator(self, audio_coordinator: object | None) -> None:
        self.audio_coordinator = audio_coordinator
        setter = getattr(self.voice_input, "set_audio_coordinator", None)
        if callable(setter):
            try:
                setter(audio_coordinator)
            except Exception:
                pass

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        del ignore_audio_block

        heard_text: str | None = None
        for method_name in (
            "listen_for_wake_phrase",
            "listen",
            "listen_once",
            "listen_for_command",
        ):
            method = getattr(self.voice_input, method_name, None)
            if not callable(method):
                continue

            try:
                heard_text = method(timeout=timeout, debug=debug)
            except TypeError:
                heard_text = method(timeout=timeout)
            break

        if heard_text is None:
            return None

        normalized = self._normalize_text(heard_text)
        if not normalized:
            return None

        tokens = [token for token in normalized.split()[:4] if token]
        if any(token in self._WAKE_ALIASES or token.startswith("nex") for token in tokens):
            return "nexa"

        compact = normalized.replace(" ", "")
        if compact.startswith("nex") and len(compact) <= 12:
            return "nexa"

        return None

    def close(self) -> None:
        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        value = str(text or "").strip().lower()
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value


__all__ = ["CompatibilityWakeGate"]