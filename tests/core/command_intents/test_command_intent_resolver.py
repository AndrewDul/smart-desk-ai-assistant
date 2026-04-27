from modules.core.command_intents.command_intent_resolver import (
    CommandIntentResolver,
)
from modules.core.command_intents.confidence_policy import (
    ConfidencePolicy,
    ConfidencePolicyConfig,
)
from modules.core.command_intents.intent import CommandIntentDomain
from modules.core.command_intents.intent_result import (
    CommandIntentResolutionStatus,
)
from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)


def test_resolver_resolves_visual_shell_show_desktop_intent() -> None:
    grammar = build_default_command_grammar()
    recognition = grammar.match("pokaż pulpit")

    result = CommandIntentResolver().resolve(recognition)

    assert result.status == CommandIntentResolutionStatus.RESOLVED
    assert result.intent is not None
    assert result.intent.key == "visual_shell.show_desktop"
    assert result.intent.domain == CommandIntentDomain.VISUAL_SHELL
    assert result.intent.action == "show_desktop"
    assert result.intent.language == CommandLanguage.POLISH


def test_resolver_resolves_system_battery_intent() -> None:
    grammar = build_default_command_grammar()
    recognition = grammar.match("battery")

    result = CommandIntentResolver().resolve(recognition)

    assert result.status == CommandIntentResolutionStatus.RESOLVED
    assert result.intent is not None
    assert result.intent.key == "system.battery"
    assert result.intent.domain == CommandIntentDomain.SYSTEM
    assert result.intent.action == "report_battery"
    assert result.intent.language == CommandLanguage.ENGLISH


def test_resolver_returns_no_intent_for_no_match() -> None:
    grammar = build_default_command_grammar()
    recognition = grammar.match("czym jest czarna dziura")

    result = CommandIntentResolver().resolve(recognition)

    assert result.status == CommandIntentResolutionStatus.NO_INTENT
    assert result.intent is None
    assert result.reason == "no_match"


def test_resolver_rejects_low_confidence_match() -> None:
    recognition = CommandRecognitionResult.matched(
        transcript="show desktop",
        normalized_transcript="show desktop",
        language=CommandLanguage.ENGLISH,
        confidence=0.5,
        intent_key="visual_shell.show_desktop",
        matched_phrase="show desktop",
    )
    resolver = CommandIntentResolver(
        ConfidencePolicy(ConfidencePolicyConfig(min_confidence=0.8))
    )

    result = resolver.resolve(recognition)

    assert result.status == CommandIntentResolutionStatus.REJECTED_LOW_CONFIDENCE
    assert result.reason == "confidence_below_threshold"


def test_resolver_returns_ambiguous_result() -> None:
    recognition = CommandRecognitionResult(
        status=CommandRecognitionStatus.AMBIGUOUS,
        transcript="shell",
        normalized_transcript="shell",
        language=CommandLanguage.UNKNOWN,
        confidence=0.0,
        alternatives=("visual_shell.show_desktop", "visual_shell.show_shell"),
    )

    result = CommandIntentResolver().resolve(recognition)

    assert result.status == CommandIntentResolutionStatus.AMBIGUOUS
    assert result.alternatives == (
        "visual_shell.show_desktop",
        "visual_shell.show_shell",
    )


def test_resolver_returns_unknown_intent_for_missing_definition() -> None:
    recognition = CommandRecognitionResult.matched(
        transcript="unknown command",
        normalized_transcript="unknown command",
        language=CommandLanguage.ENGLISH,
        confidence=1.0,
        intent_key="unknown.intent",
        matched_phrase="unknown command",
    )

    result = CommandIntentResolver().resolve(recognition)

    assert result.status == CommandIntentResolutionStatus.UNKNOWN_INTENT
    assert result.intent is None
    assert result.reason == "unknown_intent:unknown.intent"