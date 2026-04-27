from modules.core.command_intents.confidence_policy import (
    ConfidencePolicy,
    ConfidencePolicyConfig,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)


def test_confidence_policy_accepts_matched_result_above_threshold() -> None:
    policy = ConfidencePolicy(ConfidencePolicyConfig(min_confidence=0.8))
    result = CommandRecognitionResult.matched(
        transcript="show desktop",
        normalized_transcript="show desktop",
        language=CommandLanguage.ENGLISH,
        confidence=0.92,
        intent_key="visual_shell.show_desktop",
        matched_phrase="show desktop",
    )

    assert policy.rejection_reason(result) is None


def test_confidence_policy_rejects_no_match() -> None:
    policy = ConfidencePolicy()
    result = CommandRecognitionResult.no_match(
        transcript="czym jest czarna dziura",
        normalized_transcript="czym jest czarna dziura",
        language=CommandLanguage.POLISH,
    )

    assert policy.rejection_reason(result) == "no_match"


def test_confidence_policy_rejects_ambiguous_result() -> None:
    policy = ConfidencePolicy()
    result = CommandRecognitionResult(
        status=CommandRecognitionStatus.AMBIGUOUS,
        transcript="shell",
        normalized_transcript="shell",
        language=CommandLanguage.UNKNOWN,
        confidence=0.0,
        alternatives=("visual_shell.show_desktop", "visual_shell.show_shell"),
    )

    assert policy.rejection_reason(result) == "ambiguous"


def test_confidence_policy_rejects_low_confidence_match() -> None:
    policy = ConfidencePolicy(ConfidencePolicyConfig(min_confidence=0.95))
    result = CommandRecognitionResult.matched(
        transcript="show desktop",
        normalized_transcript="show desktop",
        language=CommandLanguage.ENGLISH,
        confidence=0.92,
        intent_key="visual_shell.show_desktop",
        matched_phrase="show desktop",
    )

    assert policy.rejection_reason(result) == "confidence_below_threshold"