from __future__ import annotations

from pathlib import Path

import pytest

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    DEFAULT_VOSK_SAMPLE_RATE,
    LocalVoskPcmTranscriptProvider,
    VoskCommandRecognizer,
    _coerce_command_language,
    _resolve_vosk_model_path,
)


def test_resolve_vosk_model_path_accepts_direct_model_dir(tmp_path: Path) -> None:
    model_dir = tmp_path / "vosk-model-small-en-us"
    (model_dir / "conf").mkdir(parents=True)

    assert _resolve_vosk_model_path(model_dir) == model_dir


def test_resolve_vosk_model_path_accepts_parent_with_single_model(tmp_path: Path) -> None:
    model_dir = tmp_path / "vosk-model-small-en-us"
    (model_dir / "am").mkdir(parents=True)

    assert _resolve_vosk_model_path(tmp_path) == model_dir


def test_resolve_vosk_model_path_fails_for_missing_path(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="vosk_model_path_missing"):
        _resolve_vosk_model_path(tmp_path / "missing")


def test_local_vosk_provider_rejects_invalid_sample_rate() -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        LocalVoskPcmTranscriptProvider(sample_rate=0)


def test_vosk_command_recognizer_keeps_injected_provider_path() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: "show desktop",
    )

    result = recognizer.recognize_pcm(b"\x00\x00" * 1600)

    assert result.is_match
    assert result.transcript == "show desktop"
    assert result.normalized_transcript == "show desktop"
    assert result.intent_key == "visual_shell.show_desktop"


def test_vosk_command_recognizer_can_be_constructed_with_model_path_without_loading(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "vosk-model-small-en-us"
    (model_dir / "conf").mkdir(parents=True)

    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        model_path=model_dir,
        sample_rate=DEFAULT_VOSK_SAMPLE_RATE,
        grammar_language=CommandLanguage.ENGLISH,
    )

    assert recognizer.grammar.intent_keys


def test_command_grammar_can_filter_vosk_vocabulary_per_language() -> None:
    grammar = build_default_command_grammar()

    english_phrases = grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)
    polish_phrases = grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)

    assert "show desktop" in english_phrases
    assert "pokaż pulpit" not in english_phrases

    assert "pokaż pulpit" in polish_phrases
    assert "show desktop" not in polish_phrases


def test_local_vosk_provider_stores_language_filtered_phrases() -> None:
    grammar = build_default_command_grammar()
    polish_phrases = grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)

    provider = LocalVoskPcmTranscriptProvider(
        grammar_phrases=polish_phrases,
    )

    assert "pokaż pulpit" in provider.grammar_phrases
    assert "show desktop" not in provider.grammar_phrases


def test_coerce_command_language_accepts_supported_values() -> None:
    assert _coerce_command_language(CommandLanguage.ENGLISH) is CommandLanguage.ENGLISH
    assert _coerce_command_language(CommandLanguage.POLISH) is CommandLanguage.POLISH
    assert _coerce_command_language("en") is CommandLanguage.ENGLISH
    assert _coerce_command_language("pl") is CommandLanguage.POLISH
    assert _coerce_command_language("all") is None
    assert _coerce_command_language(None) is None


def test_coerce_command_language_rejects_unknown_string() -> None:
    with pytest.raises(ValueError, match="unsupported grammar language"):
        _coerce_command_language("de")
