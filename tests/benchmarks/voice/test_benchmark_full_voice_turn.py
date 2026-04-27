from benchmarks.voice.benchmark_full_voice_turn import (
    run_full_voice_turn_benchmark,
)


def test_full_voice_turn_benchmark_accepts_default_gates() -> None:
    result = run_full_voice_turn_benchmark()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.command_latency.accepted is True
    assert result.endpointing_latency.accepted is True
    assert result.command_latency.summary.command_success_rate == 1.0