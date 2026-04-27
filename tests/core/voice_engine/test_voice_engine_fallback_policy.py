from modules.core.command_intents.command_intent_resolver import (
    CommandIntentResolver,
)
from modules.core.voice_engine.command_first_pipeline import CommandFirstPipeline
from modules.core.voice_engine.voice_engine import VoiceEngine
from modules.core.voice_engine.voice_engine_settings import VoiceEngineSettings
from modules.core.voice_engine.voice_turn import VoiceTurnInput, VoiceTurnRoute
from modules.core.voice_engine.voice_turn_state import VoiceTurnState
from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_recognizer import (
    GrammarCommandRecognizer,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage


def _pipeline() -> CommandFirstPipeline:
    return CommandFirstPipeline(
        command_recognizer=GrammarCommandRecognizer(
            build_default_command_grammar()
        ),
        intent_resolver=CommandIntentResolver(),
        clock=lambda: 1.0,
    )


def test_voice_engine_uses_fallback_when_v2_is_disabled() -> None:
    engine = VoiceEngine(
        settings=VoiceEngineSettings(enabled=False),
        command_first_pipeline=_pipeline(),
    )

    result = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-1",
            transcript="show desktop",
            started_monotonic=1.0,
            speech_end_monotonic=1.1,
            language_hint=CommandLanguage.ENGLISH,
        )
    )

    assert result.route == VoiceTurnRoute.FALLBACK
    assert result.state == VoiceTurnState.FALLBACK_REQUIRED
    assert result.fallback is not None
    assert result.fallback.reason == "voice_engine_v2_disabled"
    assert result.metrics.fallback_used is True