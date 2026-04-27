from benchmarks.voice.benchmark_endpointing_latency import (
    EndpointingLatencyAcceptanceTargets,
    run_endpointing_latency_benchmark,
)


def test_endpointing_latency_benchmark_accepts_default_policy() -> None:
    result = run_endpointing_latency_benchmark()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.speech_started is True
    assert result.speech_ended is True
    assert result.speech_start_delay_ms is not None
    assert result.endpoint_delay_ms is not None
    assert result.endpoint_delay_ms <= 300.0


def test_endpointing_latency_benchmark_rejects_too_strict_target() -> None:
    result = run_endpointing_latency_benchmark(
        targets=EndpointingLatencyAcceptanceTargets(
            max_endpoint_delay_ms=1.0,
            max_speech_start_delay_ms=1.0,
        )
    )

    assert result.accepted is False
    assert result.rejection_reasons