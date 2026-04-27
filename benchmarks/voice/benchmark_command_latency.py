from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from modules.core.command_intents import CommandIntentResolver
from modules.core.voice_engine import (
    CommandFirstPipeline,
    VoiceEngine,
    VoiceEngineSettings,
    VoiceTurnInput,
    VoiceTurnRoute,
)
from modules.devices.audio.command_asr import (
    CommandLanguage,
    GrammarCommandRecognizer,
    build_default_command_grammar,
)


@dataclass(frozen=True, slots=True)
class BenchmarkCommandPrompt:
    """One deterministic command prompt used by benchmark gates."""

    text: str
    expected_intent_key: str
    expected_language: CommandLanguage
    built_in_command: bool = True


@dataclass(frozen=True, slots=True)
class CommandLatencyBenchmarkSample:
    """Measured command-first benchmark sample."""

    text: str
    expected_intent_key: str
    resolved_intent_key: str | None
    expected_language: CommandLanguage
    resolved_language: CommandLanguage
    route: VoiceTurnRoute
    speech_end_to_action_ms: float | None
    command_recognition_ms: float | None
    intent_resolution_ms: float | None
    fallback_used: bool

    @property
    def success(self) -> bool:
        return (
            self.route is VoiceTurnRoute.COMMAND
            and self.resolved_intent_key == self.expected_intent_key
            and self.resolved_language == self.expected_language
            and not self.fallback_used
        )


@dataclass(frozen=True, slots=True)
class CommandLatencyBenchmarkSummary:
    """Aggregate command-first benchmark summary."""

    sample_count: int
    success_count: int
    fallback_count: int
    p50_speech_end_to_action_ms: float | None
    p95_speech_end_to_action_ms: float | None
    average_command_recognition_ms: float | None
    average_intent_resolution_ms: float | None

    @property
    def command_success_rate(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.success_count / float(self.sample_count)


@dataclass(frozen=True, slots=True)
class CommandLatencyAcceptanceTargets:
    """Acceptance targets for built-in command responsiveness."""

    p95_speech_end_to_action_ms: float = 2_000.0
    p50_speech_end_to_action_ms: float = 900.0
    min_command_success_rate: float = 0.95
    max_fallback_count_for_builtins: int = 0


@dataclass(frozen=True, slots=True)
class CommandLatencyBenchmarkResult:
    """Full result returned by command latency benchmark."""

    samples: tuple[CommandLatencyBenchmarkSample, ...]
    summary: CommandLatencyBenchmarkSummary
    accepted: bool
    rejection_reasons: tuple[str, ...]


class _StepClock:
    """Deterministic monotonic clock for stable benchmark contract tests."""

    def __init__(self, *, start: float = 1.0, step_seconds: float = 0.01) -> None:
        self.current = start
        self.step_seconds = step_seconds

    def __call__(self) -> float:
        self.current += self.step_seconds
        return self.current


def default_benchmark_prompts() -> tuple[BenchmarkCommandPrompt, ...]:
    return (
        BenchmarkCommandPrompt(
            text="show desktop",
            expected_intent_key="visual_shell.show_desktop",
            expected_language=CommandLanguage.ENGLISH,
        ),
        BenchmarkCommandPrompt(
            text="pokaż pulpit",
            expected_intent_key="visual_shell.show_desktop",
            expected_language=CommandLanguage.POLISH,
        ),
        BenchmarkCommandPrompt(
            text="battery",
            expected_intent_key="system.battery",
            expected_language=CommandLanguage.ENGLISH,
        ),
        BenchmarkCommandPrompt(
            text="bateria",
            expected_intent_key="system.battery",
            expected_language=CommandLanguage.POLISH,
        ),
        BenchmarkCommandPrompt(
            text="temperature",
            expected_intent_key="system.temperature",
            expected_language=CommandLanguage.ENGLISH,
        ),
        BenchmarkCommandPrompt(
            text="temperatura",
            expected_intent_key="system.temperature",
            expected_language=CommandLanguage.POLISH,
        ),
        BenchmarkCommandPrompt(
            text="what time is it",
            expected_intent_key="system.current_time",
            expected_language=CommandLanguage.ENGLISH,
        ),
        BenchmarkCommandPrompt(
            text="która godzina",
            expected_intent_key="system.current_time",
            expected_language=CommandLanguage.POLISH,
        ),
        BenchmarkCommandPrompt(
            text="help me",
            expected_intent_key="assistant.help",
            expected_language=CommandLanguage.ENGLISH,
        ),
        BenchmarkCommandPrompt(
            text="pomóż mi",
            expected_intent_key="assistant.help",
            expected_language=CommandLanguage.POLISH,
        ),
    )


def build_benchmark_voice_engine(*, clock: _StepClock | None = None) -> VoiceEngine:
    resolved_clock = clock or _StepClock()
    grammar = build_default_command_grammar()
    pipeline = CommandFirstPipeline(
        command_recognizer=GrammarCommandRecognizer(grammar),
        intent_resolver=CommandIntentResolver(),
        clock=resolved_clock,
    )

    return VoiceEngine(
        settings=VoiceEngineSettings(
            enabled=True,
            mode="v2",
            command_first_enabled=True,
            metrics_enabled=True,
        ),
        command_first_pipeline=pipeline,
    )


def run_command_latency_benchmark(
    prompts: Iterable[BenchmarkCommandPrompt] | None = None,
    *,
    targets: CommandLatencyAcceptanceTargets | None = None,
) -> CommandLatencyBenchmarkResult:
    """Run deterministic command-first latency benchmark."""

    resolved_prompts = tuple(prompts or default_benchmark_prompts())
    resolved_targets = targets or CommandLatencyAcceptanceTargets()
    clock = _StepClock()
    engine = build_benchmark_voice_engine(clock=clock)

    samples: list[CommandLatencyBenchmarkSample] = []

    for index, prompt in enumerate(resolved_prompts):
        started = clock.current
        result = engine.process_turn(
            VoiceTurnInput(
                turn_id=f"benchmark-turn-{index + 1}",
                transcript=prompt.text,
                started_monotonic=started,
                speech_end_monotonic=started,
                language_hint=CommandLanguage.UNKNOWN,
                source="command_latency_benchmark",
            )
        )

        samples.append(
            CommandLatencyBenchmarkSample(
                text=prompt.text,
                expected_intent_key=prompt.expected_intent_key,
                resolved_intent_key=(
                    None if result.intent is None else result.intent.key
                ),
                expected_language=prompt.expected_language,
                resolved_language=result.language,
                route=result.route,
                speech_end_to_action_ms=result.metrics.speech_end_to_finish_ms,
                command_recognition_ms=result.metrics.command_recognition_ms,
                intent_resolution_ms=result.metrics.intent_resolution_ms,
                fallback_used=result.metrics.fallback_used,
            )
        )

    summary = summarize_command_latency_samples(samples)
    accepted, rejection_reasons = evaluate_command_latency_gates(
        summary,
        targets=resolved_targets,
    )

    return CommandLatencyBenchmarkResult(
        samples=tuple(samples),
        summary=summary,
        accepted=accepted,
        rejection_reasons=rejection_reasons,
    )


def summarize_command_latency_samples(
    samples: Iterable[CommandLatencyBenchmarkSample],
) -> CommandLatencyBenchmarkSummary:
    sample_tuple = tuple(samples)
    action_times = tuple(
        sample.speech_end_to_action_ms
        for sample in sample_tuple
        if sample.speech_end_to_action_ms is not None
    )
    command_times = tuple(
        sample.command_recognition_ms
        for sample in sample_tuple
        if sample.command_recognition_ms is not None
    )
    resolver_times = tuple(
        sample.intent_resolution_ms
        for sample in sample_tuple
        if sample.intent_resolution_ms is not None
    )

    return CommandLatencyBenchmarkSummary(
        sample_count=len(sample_tuple),
        success_count=sum(1 for sample in sample_tuple if sample.success),
        fallback_count=sum(1 for sample in sample_tuple if sample.fallback_used),
        p50_speech_end_to_action_ms=_percentile(action_times, 50.0),
        p95_speech_end_to_action_ms=_percentile(action_times, 95.0),
        average_command_recognition_ms=_average(command_times),
        average_intent_resolution_ms=_average(resolver_times),
    )


def evaluate_command_latency_gates(
    summary: CommandLatencyBenchmarkSummary,
    *,
    targets: CommandLatencyAcceptanceTargets | None = None,
) -> tuple[bool, tuple[str, ...]]:
    resolved_targets = targets or CommandLatencyAcceptanceTargets()
    rejection_reasons: list[str] = []

    if summary.command_success_rate < resolved_targets.min_command_success_rate:
        rejection_reasons.append(
            "command_success_rate_below_target:"
            f"{summary.command_success_rate:.3f}"
        )

    if summary.fallback_count > resolved_targets.max_fallback_count_for_builtins:
        rejection_reasons.append(
            f"fallback_count_above_target:{summary.fallback_count}"
        )

    if summary.p50_speech_end_to_action_ms is None:
        rejection_reasons.append("missing_p50_speech_end_to_action_ms")
    elif (
        summary.p50_speech_end_to_action_ms
        > resolved_targets.p50_speech_end_to_action_ms
    ):
        rejection_reasons.append(
            "p50_speech_end_to_action_ms_above_target:"
            f"{summary.p50_speech_end_to_action_ms:.3f}"
        )

    if summary.p95_speech_end_to_action_ms is None:
        rejection_reasons.append("missing_p95_speech_end_to_action_ms")
    elif (
        summary.p95_speech_end_to_action_ms
        > resolved_targets.p95_speech_end_to_action_ms
    ):
        rejection_reasons.append(
            "p95_speech_end_to_action_ms_above_target:"
            f"{summary.p95_speech_end_to_action_ms:.3f}"
        )

    return not rejection_reasons, tuple(rejection_reasons)


def _average(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    return round(sum(values) / float(len(values)), 3)


def _percentile(values: tuple[float, ...], percentile: float) -> float | None:
    if not values:
        return None
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("percentile must be between 0.0 and 100.0")

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)

    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index

    interpolated = (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )
    return round(interpolated, 3)


if __name__ == "__main__":
    result = run_command_latency_benchmark()
    print(
        {
            "accepted": result.accepted,
            "sample_count": result.summary.sample_count,
            "command_success_rate": result.summary.command_success_rate,
            "fallback_count": result.summary.fallback_count,
            "p50_speech_end_to_action_ms": (
                result.summary.p50_speech_end_to_action_ms
            ),
            "p95_speech_end_to_action_ms": (
                result.summary.p95_speech_end_to_action_ms
            ),
            "rejection_reasons": result.rejection_reasons,
        }
    )