from __future__ import annotations

from dataclasses import dataclass

from benchmarks.voice.benchmark_command_latency import (
    CommandLatencyAcceptanceTargets,
    CommandLatencyBenchmarkResult,
    run_command_latency_benchmark,
)
from benchmarks.voice.benchmark_endpointing_latency import (
    EndpointingLatencyAcceptanceTargets,
    EndpointingLatencyBenchmarkResult,
    run_endpointing_latency_benchmark,
)


@dataclass(frozen=True, slots=True)
class FullVoiceTurnBenchmarkResult:
    """Combined benchmark gate for Voice Engine v2 command turns."""

    command_latency: CommandLatencyBenchmarkResult
    endpointing_latency: EndpointingLatencyBenchmarkResult
    accepted: bool
    rejection_reasons: tuple[str, ...]


def run_full_voice_turn_benchmark(
    *,
    command_targets: CommandLatencyAcceptanceTargets | None = None,
    endpointing_targets: EndpointingLatencyAcceptanceTargets | None = None,
) -> FullVoiceTurnBenchmarkResult:
    """Run combined Voice Engine v2 benchmark gates."""

    command_result = run_command_latency_benchmark(targets=command_targets)
    endpointing_result = run_endpointing_latency_benchmark(
        targets=endpointing_targets
    )

    rejection_reasons = tuple(
        f"command_latency:{reason}"
        for reason in command_result.rejection_reasons
    ) + tuple(
        f"endpointing_latency:{reason}"
        for reason in endpointing_result.rejection_reasons
    )

    return FullVoiceTurnBenchmarkResult(
        command_latency=command_result,
        endpointing_latency=endpointing_result,
        accepted=not rejection_reasons,
        rejection_reasons=rejection_reasons,
    )


if __name__ == "__main__":
    result = run_full_voice_turn_benchmark()
    print(
        {
            "accepted": result.accepted,
            "command_success_rate": (
                result.command_latency.summary.command_success_rate
            ),
            "p50_speech_end_to_action_ms": (
                result.command_latency.summary.p50_speech_end_to_action_ms
            ),
            "p95_speech_end_to_action_ms": (
                result.command_latency.summary.p95_speech_end_to_action_ms
            ),
            "endpoint_delay_ms": (
                result.endpointing_latency.endpoint_delay_ms
            ),
            "rejection_reasons": result.rejection_reasons,
        }
    )