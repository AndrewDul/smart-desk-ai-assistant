from modules.core.voice_engine.voice_engine_metrics import VoiceEngineMetrics


def test_voice_engine_metrics_calculate_command_and_total_durations() -> None:
    metrics = VoiceEngineMetrics(
        turn_started_monotonic=1.0,
        speech_end_monotonic=1.2,
    )

    metrics.mark_command_started(1.3)
    metrics.mark_command_finished(1.35)
    metrics.mark_resolver_started(1.36)
    metrics.mark_resolver_finished(1.38)
    metrics.mark_finished(1.5)

    assert metrics.command_recognition_ms == 50.0
    assert metrics.intent_resolution_ms == 20.0
    assert metrics.total_turn_ms == 500.0
    assert metrics.speech_end_to_finish_ms == 300.0


def test_voice_engine_metrics_mark_fallback_reason() -> None:
    metrics = VoiceEngineMetrics(turn_started_monotonic=1.0)

    metrics.mark_fallback("no_match")

    assert metrics.fallback_used is True
    assert metrics.fallback_reason == "no_match"