from benchmarks.voice.benchmark_command_latency import (
    BenchmarkCommandPrompt,
    CommandLatencyAcceptanceTargets,
    evaluate_command_latency_gates,
    run_command_latency_benchmark,
)
from modules.devices.audio.command_asr import CommandLanguage


def test_command_latency_benchmark_accepts_default_builtin_commands() -> None:
    result = run_command_latency_benchmark()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.summary.sample_count >= 8
    assert result.summary.command_success_rate == 1.0
    assert result.summary.fallback_count == 0
    assert result.summary.p95_speech_end_to_action_ms is not None
    assert result.summary.p95_speech_end_to_action_ms <= 2_000.0


def test_command_latency_benchmark_rejects_when_success_rate_is_too_low() -> None:
    result = run_command_latency_benchmark(
        prompts=(
            BenchmarkCommandPrompt(
                text="czym jest czarna dziura",
                expected_intent_key="system.battery",
                expected_language=CommandLanguage.POLISH,
            ),
        ),
        targets=CommandLatencyAcceptanceTargets(
            min_command_success_rate=1.0,
            max_fallback_count_for_builtins=0,
        ),
    )

    assert result.accepted is False
    assert any(
        reason.startswith("command_success_rate_below_target")
        for reason in result.rejection_reasons
    )
    assert "fallback_count_above_target:1" in result.rejection_reasons


def test_command_latency_gate_evaluator_accepts_default_summary() -> None:
    result = run_command_latency_benchmark()
    accepted, reasons = evaluate_command_latency_gates(result.summary)

    assert accepted is True
    assert reasons == ()