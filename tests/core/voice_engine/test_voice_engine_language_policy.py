from modules.core.voice_engine.language_policy import VoiceLanguagePolicy
from modules.devices.audio.command_asr.command_language import CommandLanguage


def test_language_policy_prefers_recognition_language() -> None:
    policy = VoiceLanguagePolicy()

    language = policy.choose_language(
        transcript="pokaż pulpit",
        recognition_language=CommandLanguage.POLISH,
        hint=CommandLanguage.ENGLISH,
    )

    assert language == CommandLanguage.POLISH


def test_language_policy_detects_language_from_transcript() -> None:
    policy = VoiceLanguagePolicy()

    language = policy.choose_language(
        transcript="show desktop",
        recognition_language=CommandLanguage.UNKNOWN,
        hint=CommandLanguage.UNKNOWN,
    )

    assert language == CommandLanguage.ENGLISH


def test_language_policy_uses_hint_when_detection_is_unknown() -> None:
    policy = VoiceLanguagePolicy()

    language = policy.choose_language(
        transcript="nexa",
        recognition_language=CommandLanguage.UNKNOWN,
        hint=CommandLanguage.POLISH,
    )

    assert language == CommandLanguage.POLISH