from collections import deque

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
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_recognizer import (
    GrammarCommandRecognizer,
)


def _clock() -> callable:
    timestamps = deque([1.01, 1.02, 1.03, 1.04, 1.05])

    def tick() -> float:
        return timestamps.popleft()

    return tick


def _engine() -> VoiceEngine:
    pipeline = CommandFirstPipeline(
        command_recognizer=GrammarCommandRecognizer(
            build_default_command_grammar()
        ),
        intent_resolver=CommandIntentResolver(),
        clock=_clock(),
    )

    return VoiceEngine(
        settings=VoiceEngineSettings(
            enabled=True,
            mode="v2",
            command_first_enabled=True,
        ),
        command_first_pipeline=pipeline,
    )


def test_voice_engine_resolves_polish_visual_shell_command_first() -> None:
    engine = _engine()

    result = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-1",
            transcript="pokaż pulpit",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
            language_hint=CommandLanguage.UNKNOWN,
        )
    )

    assert result.route == VoiceTurnRoute.COMMAND
    assert result.state == VoiceTurnState.COMPLETED
    assert result.intent is not None
    assert result.intent.key == "visual_shell.show_desktop"
    assert result.intent.action == "show_desktop"
    assert result.language == CommandLanguage.POLISH
    assert result.metrics.fallback_used is False
    assert result.metrics.command_recognition_ms == 10.0
    assert result.metrics.intent_resolution_ms == 10.0


def test_voice_engine_resolves_english_system_command_first() -> None:
    engine = _engine()

    result = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-2",
            transcript="battery",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
        )
    )

    assert result.route == VoiceTurnRoute.COMMAND
    assert result.intent is not None
    assert result.intent.key == "system.battery"
    assert result.intent.action == "report_battery"
    assert result.language == CommandLanguage.ENGLISH


def test_voice_engine_sends_open_question_to_fallback() -> None:
    engine = _engine()

    result = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-3",
            transcript="czym jest czarna dziura",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
            language_hint=CommandLanguage.POLISH,
        )
    )

    assert result.route == VoiceTurnRoute.FALLBACK
    assert result.state == VoiceTurnState.FALLBACK_REQUIRED
    assert result.intent is None
    assert result.fallback is not None
    assert result.fallback.reason == "no_match"
    assert result.fallback.language == CommandLanguage.POLISH
    assert result.metrics.fallback_used is True