import pytest

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_result import CommandRecognitionStatus
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    VoskCommandRecognizer,
)


def test_vosk_command_recognizer_delegates_text_to_grammar() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
    )

    result = recognizer.recognize_text("show desktop")

    assert result.status == CommandRecognitionStatus.MATCHED
    assert result.intent_key == "visual_shell.show_desktop"


def test_vosk_command_recognizer_uses_injected_pcm_transcript_provider() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: "pokaż pulpit",
    )

    result = recognizer.recognize_pcm(b"\x00\x00" * 1600)

    assert result.status == CommandRecognitionStatus.MATCHED
    assert result.intent_key == "visual_shell.show_desktop"


def test_vosk_command_recognizer_returns_no_match_for_empty_pcm_transcript() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: "",
    )

    result = recognizer.recognize_pcm(b"\x00\x00" * 1600)

    assert result.status == CommandRecognitionStatus.NO_MATCH


def test_vosk_command_recognizer_requires_pcm_provider_for_pcm_recognition() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
    )

    with pytest.raises(RuntimeError, match="pcm_transcript_provider"):
        recognizer.recognize_pcm(b"\x00\x00" * 1600)