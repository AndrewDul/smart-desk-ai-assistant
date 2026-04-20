from __future__ import annotations

from typing import Any

from modules.shared.config.settings import load_settings
from modules.system.deployment import SystemdBootAcceptanceService

from .release_gate_models import PremiumReleaseGateResult, ReleaseChecklistItem
from .service import TurnBenchmarkValidationService


class PremiumReleaseGateService:
    """Combine benchmark validation and boot acceptance into one release decision."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()
        self.release_cfg = self._cfg("premium_release")
        self.benchmark_validation = TurnBenchmarkValidationService(settings=self.settings)
        self.boot_acceptance = SystemdBootAcceptanceService(settings=self.settings)

    def run(
        self,
        *,
        system_dir: str = "/etc/systemd/system",
        include_journal: bool = False,
        journal_lines: int = 40,
    ) -> PremiumReleaseGateResult:
        benchmark_result = self.benchmark_validation.run()
        boot_result = self.boot_acceptance.run(
            system_dir=system_dir,
            allow_degraded=False,
            include_journal=include_journal,
            journal_lines=journal_lines,
        )

        required_segments = self._cfg_list(
            "required_segments",
            default=["voice", "skill", "llm"],
        )
        min_window_samples = self._cfg_int("min_benchmark_window_samples", default=10)

        lifecycle_state = str(boot_result.runtime_snapshot.get("lifecycle_state", "") or "").strip()
        startup_mode = str(boot_result.runtime_snapshot.get("startup_mode", "") or "").strip()
        primary_ready = bool(
            boot_result.runtime_snapshot.get(
                "primary_ready",
                boot_result.runtime_snapshot.get("ready", False),
            )
        )
        premium_ready = bool(boot_result.runtime_snapshot.get("premium_ready", False))

        checklist: list[ReleaseChecklistItem] = []
        checklist.append(
            ReleaseChecklistItem(
                key="boot.strict-acceptance",
                ok=boot_result.ok,
                details="Strict Raspberry Pi boot acceptance must pass before release.",
                remediation="Fix failing systemd or runtime readiness checks before declaring premium-ready.",
                source="boot_acceptance",
            )
        )
        checklist.append(
            ReleaseChecklistItem(
                key="benchmark.validation",
                ok=benchmark_result.ok,
                details="Segmented turn benchmark validation must pass.",
                remediation="Resolve failing voice, skill, or llm benchmark checks and collect a fresh benchmark window.",
                source="benchmark_validation",
            )
        )
        checklist.append(
            ReleaseChecklistItem(
                key="benchmark.window-size",
                ok=benchmark_result.window_sample_count >= min_window_samples,
                details=(
                    f"Benchmark window has {benchmark_result.window_sample_count} samples; "
                    f"required minimum is {min_window_samples}."
                ),
                remediation="Collect a larger benchmark window before making a release decision.",
                source="benchmark_validation",
            )
        )

        segments_by_key = {segment.key: segment for segment in benchmark_result.segments}
        for segment_key in required_segments:
            segment = segments_by_key.get(segment_key)
            segment_ok = segment is not None and not segment.failed_checks()
            label = segment.label if segment is not None else segment_key
            checklist.append(
                ReleaseChecklistItem(
                    key=f"segment.{segment_key}",
                    ok=segment_ok,
                    details=(
                        f"{label} segment must pass all checks."
                        if segment is not None
                        else f"Required segment '{segment_key}' is missing from benchmark validation output."
                    ),
                    remediation=f"Collect and validate fresh {segment_key} benchmarks until this segment passes.",
                    source="benchmark_validation",
                )
            )

        checklist.extend(
            [
                ReleaseChecklistItem(
                    key="runtime.lifecycle-state",
                    ok=lifecycle_state == "ready",
                    details=f"Runtime lifecycle state is '{lifecycle_state or 'unknown'}'.",
                    remediation="Bring runtime to READY state before release.",
                    source="boot_acceptance",
                ),
                ReleaseChecklistItem(
                    key="runtime.startup-mode",
                    ok=startup_mode == "premium",
                    details=f"Runtime startup mode is '{startup_mode or 'unknown'}'.",
                    remediation="Resolve degraded or limited startup mode before release.",
                    source="boot_acceptance",
                ),
                ReleaseChecklistItem(
                    key="runtime.primary-ready",
                    ok=primary_ready,
                    details=f"primary_ready={primary_ready}",
                    remediation="Resolve primary runtime blockers before release.",
                    source="boot_acceptance",
                ),
                ReleaseChecklistItem(
                    key="runtime.premium-ready",
                    ok=premium_ready,
                    details=f"premium_ready={premium_ready}",
                    remediation="Resolve premium blockers before release.",
                    source="boot_acceptance",
                ),
            ]
        )

        failed_check_keys: list[str] = []
        failed_check_keys.extend(check.key for check in benchmark_result.failed_checks())
        failed_check_keys.extend(check.key for check in boot_result.failed_checks())
        failed_check_keys.extend(
            item.key
            for item in checklist
            if not item.ok and item.key not in failed_check_keys
        )

        ok = all(item.ok for item in checklist)
        return PremiumReleaseGateResult(
            ok=ok,
            verdict="premium-ready" if ok else "blocked",
            benchmark_path=benchmark_result.path,
            benchmark_window_sample_count=benchmark_result.window_sample_count,
            runtime_status_path=boot_result.runtime_status_path,
            lifecycle_state=lifecycle_state,
            startup_mode=startup_mode,
            primary_ready=primary_ready,
            premium_ready=premium_ready,
            failed_check_keys=failed_check_keys,
            checklist=checklist,
        )

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {}) if isinstance(self.settings, dict) else {}
        return value if isinstance(value, dict) else {}

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.release_cfg.get(key, default))
        except (TypeError, ValueError):
            return int(default)

    def _cfg_list(self, key: str, default: list[str]) -> list[str]:
        value = self.release_cfg.get(key, default)
        if not isinstance(value, list):
            return list(default)

        cleaned: list[str] = []
        for item in value:
            text = str(item or "").strip().lower()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned or list(default)