from __future__ import annotations

from modules.devices.audio.command_asr.bilingual_vosk_command_recognizer import (
    BilingualVoskCommandRecognizer,
)
from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_result import CommandRecognitionStatus
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    VoskCommandRecognizer,
)


def _recognizer_for_text(text: str | None) -> VoskCommandRecognizer:
    return VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: text,
    )


def test_bilingual_vosk_recognizer_returns_english_command_match() -> None:
    recognizer = BilingualVoskCommandRecognizer(
        english_recognizer=_recognizer_for_text("show desktop"),
        polish_recognizer=_recognizer_for_text(None),
    )

    result = recognizer.recognize_pcm(b"\x00\x00" * 1600)

    assert result.status is CommandRecognitionStatus.MATCHED
    assert result.language is CommandLanguage.ENGLISH
    assert result.intent_key == "visual_shell.show_desktop"
    assert result.matched_phrase == "show desktop"


def test_bilingual_vosk_recognizer_returns_polish_command_match() -> None:
    recognizer = BilingualVoskCommandRecognizer(
        english_recognizer=_recognizer_for_text(None),
        polish_recognizer=_recognizer_for_text("pokaż pulpit"),
    )

    result = recognizer.recognize_pcm(b"\x00\x00" * 1600)

    assert result.status is CommandRecognitionStatus.MATCHED
    assert result.language is CommandLanguage.POLISH
    assert result.intent_key == "visual_shell.show_desktop"
    assert result.matched_phrase == "pokaż pulpit"


def test_bilingual_vosk_recognizer_returns_no_match_when_both_languages_miss() -> None:
    recognizer = BilingualVoskCommandRecognizer(
        english_recognizer=_recognizer_for_text("random English words"),
        polish_recognizer=_recognizer_for_text("losowe polskie słowa"),
    )

    result = recognizer.recognize_pcm(b"\x00\x00" * 1600)

    assert result.status is CommandRecognitionStatus.NO_MATCH
    assert result.language is CommandLanguage.UNKNOWN
    assert result.intent_key is None


def test_bilingual_vosk_recognizer_returns_ambiguous_when_both_match_equally() -> None:
    recognizer = BilingualVoskCommandRecognizer(
        english_recognizer=_recognizer_for_text("show desktop"),
        polish_recognizer=_recognizer_for_text("pokaż pulpit"),
    )

    result = recognizer.recognize_pcm(b"\x00\x00" * 1600)

    assert result.status is CommandRecognitionStatus.AMBIGUOUS
    assert result.language is CommandLanguage.UNKNOWN
    assert result.intent_key is None
    assert result.alternatives == ("visual_shell.show_desktop",)


def test_bilingual_vosk_recognizer_reset_resets_both_language_recognizers() -> None:
    class ResettableRecognizer(VoskCommandRecognizer):
        def __init__(self) -> None:
            super().__init__(
                grammar=build_default_command_grammar(),
                pcm_transcript_provider=lambda pcm: None,
            )
            self.reset_count = 0

        def reset(self) -> None:
            self.reset_count += 1

    english = ResettableRecognizer()
    polish = ResettableRecognizer()
    recognizer = BilingualVoskCommandRecognizer(
        english_recognizer=english,
        polish_recognizer=polish,
    )

    recognizer.reset()

    assert english.reset_count == 1
    assert polish.reset_count == 1
