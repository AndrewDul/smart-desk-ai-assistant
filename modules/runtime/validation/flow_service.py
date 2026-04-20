from __future__ import annotations

from typing import Any

from modules.shared.config.settings import load_settings

from .flow_models import (
    PremiumValidationFlow,
    ValidationCommand,
    ValidationFlowStage,
    ValidationScenario,
)
from .service import TurnBenchmarkValidationService


class PremiumValidationFlowService:
    """Build a repeatable Raspberry Pi premium validation flow."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()
        self.validation_cfg = self._cfg("premium_validation")
        self.benchmark_validation = TurnBenchmarkValidationService(settings=self.settings)

    def build_flow(self) -> PremiumValidationFlow:
        benchmark_result = self.benchmark_validation.run()
        failed_check_keys = [check.key for check in benchmark_result.failed_checks()]
        priority_segments = self._priority_segments(failed_check_keys)

        return PremiumValidationFlow(
            benchmark_ok=benchmark_result.ok,
            benchmark_path=benchmark_result.path,
            benchmark_window_sample_count=benchmark_result.window_sample_count,
            latest_turn_id=benchmark_result.latest_turn_id,
            priority_segments=priority_segments,
            failed_check_keys=failed_check_keys,
            stages=[
                self._build_preflight_stage(priority_segments),
                self._build_voice_skill_stage(priority_segments),
                self._build_llm_short_stage(priority_segments),
                self._build_llm_long_stage(priority_segments),
                self._build_final_gate_stage(priority_segments),
            ],
        )

    def _build_preflight_stage(self, priority_segments: list[str]) -> ValidationFlowStage:
        return ValidationFlowStage(
            key="preflight",
            title="Preflight and clean benchmark window",
            goal="Start from a known-good runtime state before collecting premium validation evidence.",
            commands=[
                ValidationCommand(
                    label="Regression suite",
                    command="pytest -q",
                ),
                ValidationCommand(
                    label="Strict boot acceptance",
                    command="sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --show-journal",
                    requires_sudo=True,
                ),
                ValidationCommand(
                    label="Backup benchmark file",
                    command="cp var/data/turn_benchmarks.json var/data/turn_benchmarks.backup.json",
                ),
                ValidationCommand(
                    label="Reset benchmark file",
                    command=(
                        "python - <<'PY'\n"
                        "import json\n"
                        "from pathlib import Path\n"
                        "path = Path('var/data/turn_benchmarks.json')\n"
                        "payload = {'version': 1, 'updated_at_iso': '', 'samples': [], 'summary': {}}\n"
                        "path.write_text(json.dumps(payload, indent=2), encoding='utf-8')\n"
                        "print(f'reset: {path}')\n"
                        "PY"
                    ),
                ),
            ],
            notes=[
                "Run the validation flow on Raspberry Pi, not on a laptop or synthetic shell-only session.",
                "If strict boot acceptance fails, fix runtime readiness before collecting new benchmark evidence.",
                (
                    "Priority focus for the next capture window: "
                    + (", ".join(priority_segments) if priority_segments else "maintain balanced coverage")
                ),
            ],
        )

    def _build_voice_skill_stage(self, priority_segments: list[str]) -> ValidationFlowStage:
        min_turns = self._cfg_int("voice_skill_turn_target", default=8)
        return ValidationFlowStage(
            key="voice_skill",
            title="Voice and built-in skill validation",
            goal="Measure wake, STT, response start, and deterministic skill latency under normal desk use.",
            scenarios=[
                ValidationScenario(
                    key="voice-short-skills",
                    title="Short voice skills",
                    objective="Drive the wake path and fast built-in commands with short spoken requests.",
                    target_segments=["voice", "skill"],
                    min_turns=min_turns,
                    prompts=[
                        "NeXa, what time is it",
                        "NeXa, what is today's date",
                        "NeXa, introduce yourself",
                        "NeXa, help me",
                        "NeXa, set timer for two minutes",
                        "NeXa, stop timer",
                        "NeXa, start focus mode for five minutes",
                        "NeXa, stop focus mode",
                    ],
                    expected_signals=[
                        "Wake acknowledgement should feel immediate.",
                        "Speech should not be cut off before the final word.",
                        "Built-in command reply should start fast and stay deterministic.",
                    ],
                )
            ],
            notes=[
                "Use real voice turns through the microphone. Text-only testing will not populate wake/STT metrics.",
                "Record this stage in a quiet room first; noisy-room validation comes later.",
                "If voice is the top failing segment, repeat this stage twice before moving on.",
            ],
        )

    def _build_llm_short_stage(self, priority_segments: list[str]) -> ValidationFlowStage:
        min_turns = self._cfg_int("llm_short_turn_target", default=5)
        return ValidationFlowStage(
            key="llm_short",
            title="Short LLM streaming validation",
            goal="Check first chunk latency, first audio latency, and live streaming quality for short open questions.",
            scenarios=[
                ValidationScenario(
                    key="llm-short-streaming",
                    title="Short open dialogue",
                    objective="Collect short LLM turns that should start speaking quickly with streaming enabled.",
                    target_segments=["voice", "llm"],
                    min_turns=min_turns,
                    prompts=[
                        "NeXa, explain what a black hole is in simple terms",
                        "NeXa, compare Python and JavaScript in a few sentences",
                        "NeXa, explain overfitting in machine learning",
                        "NeXa, what is event-driven architecture",
                        "NeXa, explain the difference between RAM and storage",
                    ],
                    expected_signals=[
                        "The assistant should emit a short acknowledgement only when needed.",
                        "The first meaningful spoken phrase should start early.",
                        "Streaming ratio should stay high across repeated LLM turns.",
                    ],
                )
            ],
            notes=[
                "Keep the prompts open-ended so they route to the LLM instead of the deterministic skill path.",
                "If llm.streaming-ratio fails, inspect whether response_live_streaming is being set consistently.",
                "If llm.avg-response-first-audio-ms fails while llm.avg-first-chunk-ms passes, the bottleneck is after the model starts generating.",
            ],
        )

    def _build_llm_long_stage(self, priority_segments: list[str]) -> ValidationFlowStage:
        min_turns = self._cfg_int("llm_long_turn_target", default=3)
        return ValidationFlowStage(
            key="llm_long",
            title="Long-answer, interruption, and reminder validation",
            goal="Stress the response path, long-turn completion, interruption behavior, and reminder correctness under realistic use.",
            scenarios=[
                ValidationScenario(
                    key="llm-long-answer-stress",
                    title="Long LLM answers",
                    objective="Measure long-tail latency separately from short command responsiveness.",
                    target_segments=["llm"],
                    min_turns=min_turns,
                    prompts=[
                        "NeXa, tell me a short story about Mars colonization",
                        "NeXa, explain how neural networks learn, step by step",
                        "NeXa, give me a detailed comparison of Python, Rust, and Go for backend systems",
                    ],
                    expected_signals=[
                        "The assistant should begin speaking before the full answer is generated.",
                        "Long turns may be longer, but they should not block the next session forever.",
                    ],
                ),
                ValidationScenario(
                    key="barge-in-and-follow-up",
                    title="Interruption and follow-up",
                    objective="Verify barge-in, stop/restart audio coordination, and short follow-up continuity.",
                    target_segments=["voice", "llm"],
                    min_turns=self._cfg_int("barge_in_turn_target", default=3),
                    prompts=[
                        "Interrupt NeXa while it is speaking and ask: 'NeXa, stop and tell me the time'",
                        "Ask a follow-up right after a reply without waiting too long.",
                        "Trigger an exit confirmation and answer yes or no.",
                    ],
                    expected_signals=[
                        "Playback should stop cleanly when the user barges in.",
                        "The next voice turn should be captured without long dead air.",
                        "The assistant should keep short follow-up state correctly.",
                    ],
                ),
                ValidationScenario(
                    key="reminder-reliability",
                    title="Reminder reliability",
                    objective="Verify that reminders survive runtime activity and still trigger correctly.",
                    target_segments=["skill"],
                    min_turns=self._cfg_int("reminder_turn_target", default=2),
                    prompts=[
                        "Set a reminder for one minute.",
                        "Wait for the reminder to trigger and confirm the spoken output.",
                    ],
                    expected_signals=[
                        "Reminder state should persist correctly.",
                        "Reminder playback should not corrupt the next wake cycle.",
                    ],
                ),
            ],
            notes=[
                "This stage is where long LLM total-turn latency is allowed to be higher than the skill path.",
                "If llm.p95-total-turn-ms fails but llm.avg-first-chunk-ms passes, prioritize response chunking and TTS handoff, not model startup.",
                "Use this stage to capture barge-in failures before any final release decision.",
            ],
        )

    def _build_final_gate_stage(self, priority_segments: list[str]) -> ValidationFlowStage:
        return ValidationFlowStage(
            key="final_gate",
            title="Final premium validation gate",
            goal="Re-run the validation checks and collect the evidence needed for a release decision.",
            commands=[
                ValidationCommand(
                    label="Benchmark threshold report",
                    command="python scripts/check_turn_benchmark_thresholds.py",
                ),
                ValidationCommand(
                    label="Strict boot acceptance re-check",
                    command="sudo .venv/bin/python scripts/check_systemd_boot_acceptance.py --show-journal",
                    requires_sudo=True,
                ),
            ],
            notes=[
                "Do not declare premium-ready if voice or llm response-start checks still fail.",
                (
                    "If the benchmark report still fails, optimize these segments first: "
                    + (", ".join(priority_segments) if priority_segments else "voice, skill, llm")
                ),
                "Save the final benchmark report together with the boot acceptance output as release evidence.",
            ],
        )

    def _priority_segments(self, failed_check_keys: list[str]) -> list[str]:
        counts = {"voice": 0, "skill": 0, "llm": 0}
        for key in failed_check_keys:
            for segment in counts:
                if key.startswith(f"{segment}."):
                    counts[segment] += 1
        ordered = [
            segment
            for segment, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if count > 0
        ]
        return ordered

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {}) if isinstance(self.settings, dict) else {}
        return value if isinstance(value, dict) else {}

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.validation_cfg.get(key, default))
        except (TypeError, ValueError):
            return int(default)