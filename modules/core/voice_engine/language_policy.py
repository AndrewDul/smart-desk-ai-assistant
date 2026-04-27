from __future__ import annotations

from modules.devices.audio.command_asr.command_language import (
    CommandLanguage,
    detect_command_language,
)


class VoiceLanguagePolicy:
    """Per-turn language policy for Voice Engine v2."""

    def choose_language(
        self,
        *,
        transcript: str,
        recognition_language: CommandLanguage = CommandLanguage.UNKNOWN,
        hint: CommandLanguage = CommandLanguage.UNKNOWN,
    ) -> CommandLanguage:
        if recognition_language is not CommandLanguage.UNKNOWN:
            return recognition_language

        detected = detect_command_language(transcript)
        if detected is not CommandLanguage.UNKNOWN:
            return detected

        if hint is not CommandLanguage.UNKNOWN:
            return hint

        return CommandLanguage.UNKNOWN