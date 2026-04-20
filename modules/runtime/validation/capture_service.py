from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.shared.config.settings import load_settings

from .capture_models import (
    PremiumValidationCaptureSnapshot,
    ValidationCaptureScenarioView,
    ValidationCaptureSegmentProgress,
    ValidationCaptureStageView,
)
from .flow_service import PremiumValidationFlowService
from .models import BenchmarkValidationSegment
from .service import TurnBenchmarkValidationService


class PremiumValidationCaptureService:
    """Build a repeatable, watch-friendly capture plan for premium validation sessions."""

    _SEGMENT_MINIMUM_KEYS = {
        "voice": "min_voice_samples",
        "skill": "min_skill_samples",
        "llm": "min_llm_samples",
    }

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()
        self.benchmark_cfg = self._cfg("benchmarks")
        self.validation_cfg = self._cfg("benchmark_validation")
        self.validation_service = TurnBenchmarkValidationService(settings=self.settings)
        self.flow_service = PremiumValidationFlowService(settings=self.settings)

    def build_snapshot(self, *, stage_key: str | None = None) -> PremiumValidationCaptureSnapshot:
        validation_result = self.validation_service.run()
        flow = self.flow_service.build_flow()
        selected_stage = self._select_stage(stage_key=stage_key, flow=flow)

        segment_progress = [
            self._segment_progress(segment)
            for segment in validation_result.segments
        ]

        return PremiumValidationCaptureSnapshot(
            benchmark_ok=validation_result.ok,
            benchmark_path=validation_result.path,
            total_samples=validation_result.sample_count,
            window_samples=validation_result.window_sample_count,
            latest_turn_id=validation_result.latest_turn_id,
            priority_segments=list(flow.priority_segments),
            segment_progress=segment_progress,
            stage=selected_stage,
        )

    def reset_benchmark_store(self, *, backup: bool = True) -> dict[str, str]:
        path = Path(self.validation_service.run().path)
        path.parent.mkdir(parents=True, exist_ok=True)

        result: dict[str, str] = {"path": str(path)}
        if backup and path.exists():
            backup_path = path.with_suffix(".backup.json")
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            result["backup_path"] = str(backup_path)

        payload = {
            "version": 1,
            "updated_at_iso": "",
            "samples": [],
            "summary": {},
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        result["status"] = "reset"
        return result

    def render_snapshot(self, snapshot: PremiumValidationCaptureSnapshot) -> str:
        lines: list[str] = []
        lines.append("NeXa premium validation capture")
        lines.append(f"- benchmark ok: {snapshot.benchmark_ok}")
        lines.append(f"- benchmark path: {snapshot.benchmark_path}")
        lines.append(f"- total samples: {snapshot.total_samples}")
        lines.append(f"- window samples: {snapshot.window_samples}")
        lines.append(f"- latest turn: {snapshot.latest_turn_id or '-'}")
        lines.append(
            "- priority segments: "
            + (", ".join(snapshot.priority_segments) if snapshot.priority_segments else "-")
        )

        lines.append("\nSegment progress:")
        for segment in snapshot.segment_progress:
            failed = ", ".join(segment.failed_check_keys) if segment.failed_check_keys else "-"
            lines.append(
                f"- {segment.label} [{segment.key}] current={segment.current_samples} "
                f"required={segment.required_samples} missing={segment.missing_samples} ok={segment.ok}"
            )
            lines.append(f"  failed: {failed}")

        if snapshot.stage is not None:
            stage = snapshot.stage
            lines.append(f"\nStage: {stage.title} [{stage.key}]")
            lines.append(f"Goal: {stage.goal}")
            if stage.scenarios:
                lines.append("Scenarios:")
                for scenario in stage.scenarios:
                    lines.append(
                        f"- {scenario.title} [{scenario.key}] targets={','.join(scenario.target_segments)} "
                        f"min_turns={scenario.min_turns}"
                    )
                    lines.append(f"  objective: {scenario.objective}")
                    if scenario.prompts:
                        lines.append("  prompts:")
                        for prompt in scenario.prompts:
                            lines.append(f"    - {prompt}")
                    if scenario.expected_signals:
                        lines.append("  expected:")
                        for item in scenario.expected_signals:
                            lines.append(f"    - {item}")
            if stage.notes:
                lines.append("Notes:")
                for note in stage.notes:
                    lines.append(f"- {note}")

        return "\n".join(lines)

    def _segment_progress(self, segment: BenchmarkValidationSegment) -> ValidationCaptureSegmentProgress:
        required_samples = self._required_samples_for_segment(segment.key)
        current_samples = int(segment.sample_count)
        missing_samples = max(0, required_samples - current_samples)
        failed_check_keys = [check.key for check in segment.failed_checks()]
        return ValidationCaptureSegmentProgress(
            key=segment.key,
            label=segment.label,
            current_samples=current_samples,
            required_samples=required_samples,
            missing_samples=missing_samples,
            ok=all(check.ok for check in segment.checks),
            failed_check_keys=failed_check_keys,
        )

    def _required_samples_for_segment(self, segment_key: str) -> int:
        key = self._SEGMENT_MINIMUM_KEYS.get(str(segment_key or "").strip())
        default = 5 if segment_key == "voice" else 3
        if not key:
            return default
        try:
            return int(self.validation_cfg.get(key, default))
        except (TypeError, ValueError):
            return default

    def _select_stage(self, *, stage_key: str | None, flow: Any) -> ValidationCaptureStageView | None:
        if not getattr(flow, "stages", None):
            return None

        normalized_stage_key = str(stage_key or "").strip().lower()
        selected = None
        if normalized_stage_key:
            for stage in flow.stages:
                if str(stage.key or "").strip().lower() == normalized_stage_key:
                    selected = stage
                    break
        if selected is None:
            selected = self._default_stage(flow)
        if selected is None:
            return None

        return ValidationCaptureStageView(
            key=str(selected.key or "").strip(),
            title=str(selected.title or "").strip(),
            goal=str(selected.goal or "").strip(),
            notes=[str(note or "").strip() for note in list(selected.notes or []) if str(note or "").strip()],
            scenarios=[
                ValidationCaptureScenarioView(
                    key=str(scenario.key or "").strip(),
                    title=str(scenario.title or "").strip(),
                    objective=str(scenario.objective or "").strip(),
                    target_segments=[
                        str(item or "").strip()
                        for item in list(scenario.target_segments or [])
                        if str(item or "").strip()
                    ],
                    min_turns=max(0, int(getattr(scenario, "min_turns", 0) or 0)),
                    prompts=[str(prompt or "").strip() for prompt in list(scenario.prompts or []) if str(prompt or "").strip()],
                    expected_signals=[
                        str(item or "").strip()
                        for item in list(scenario.expected_signals or [])
                        if str(item or "").strip()
                    ],
                )
                for scenario in list(selected.scenarios or [])
            ],
        )

    def _default_stage(self, flow: Any) -> Any | None:
        priority_segments = list(getattr(flow, "priority_segments", []) or [])
        stages = list(getattr(flow, "stages", []) or [])
        if not stages:
            return None

        for preferred_key in ("voice_skill", "llm_short", "llm_long", "final_gate"):
            if preferred_key == "voice_skill" and "voice" not in priority_segments and "skill" not in priority_segments:
                continue
            if preferred_key in {"llm_short", "llm_long"} and "llm" not in priority_segments:
                continue
            for stage in stages:
                if str(stage.key or "").strip() == preferred_key:
                    return stage

        for stage in stages:
            if str(stage.key or "").strip() != "preflight":
                return stage
        return stages[0]

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {}) if isinstance(self.settings, dict) else {}
        return value if isinstance(value, dict) else {}


__all__ = ["PremiumValidationCaptureService"]