from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from modules.shared.config.settings import load_settings
from modules.shared.persistence.paths import APP_ROOT

from .acceptance_models import BootAcceptanceCheck, SystemdBootAcceptanceResult


class SystemdBootAcceptanceService:
    """Verify installed systemd units and runtime product state on Raspberry Pi."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()
        self.project_root = APP_ROOT
        self.deployment_cfg = self._cfg("deployment")
        self.runtime_product_cfg = self._cfg("runtime_product")

    def run(
        self,
        *,
        system_dir: str = "/etc/systemd/system",
        allow_degraded: bool = False,
        include_journal: bool = False,
        journal_lines: int = 40,
    ) -> SystemdBootAcceptanceResult:
        target_dir = Path(system_dir).expanduser().resolve()
        unit_names = self._configured_unit_names()
        runtime_status_path = self._runtime_status_path()

        checks: list[BootAcceptanceCheck] = []
        unit_states: dict[str, dict[str, str]] = {}
        journal_tails: dict[str, str] = {}

        for unit_name in unit_names:
            expected_path = (target_dir / unit_name).resolve()
            unit_installed = expected_path.exists()

            checks.append(
                BootAcceptanceCheck(
                    key=f"{unit_name}:installed",
                    ok=unit_installed,
                    details=f"Expected unit file at {expected_path}",
                    remediation="Install the generated unit files into the systemd directory.",
                    evidence={"expected_path": str(expected_path)},
                )
            )

            if not unit_installed:
                continue

            state = self._systemctl_show(unit_name)
            unit_states[unit_name] = state

            active_ok = (
                state.get("ActiveState") == "active"
                and state.get("SubState") in {"running", "listening"}
            )
            checks.append(
                BootAcceptanceCheck(
                    key=f"{unit_name}:active",
                    ok=active_ok,
                    details=(
                        f"ActiveState={state.get('ActiveState', 'unknown')}, "
                        f"SubState={state.get('SubState', 'unknown')}"
                    ),
                    remediation=f"Inspect 'systemctl status {unit_name}' and journal logs for boot errors.",
                    evidence=dict(state),
                )
            )

            enabled_ok = state.get("UnitFileState") in {"enabled", "enabled-runtime"}
            checks.append(
                BootAcceptanceCheck(
                    key=f"{unit_name}:enabled",
                    ok=enabled_ok,
                    details=f"UnitFileState={state.get('UnitFileState', 'unknown')}",
                    remediation=f"Run 'sudo systemctl enable {unit_name}' and reboot the device.",
                    evidence=dict(state),
                )
            )

            if include_journal:
                journal_tails[unit_name] = self._journal_tail(unit_name, lines=journal_lines)

        runtime_snapshot, runtime_error = self._load_runtime_snapshot(runtime_status_path)
        runtime_status_ok = runtime_error == ""
        checks.append(
            BootAcceptanceCheck(
                key="runtime-status-file",
                ok=runtime_status_ok,
                details=(
                    f"Runtime status path: {runtime_status_path}"
                    if runtime_status_ok
                    else runtime_error
                ),
                remediation=(
                    "Check runtime_product.status_path, file permissions, and whether the assistant completed boot."
                ),
                evidence={"path": str(runtime_status_path)},
            )
        )

        if runtime_status_ok:
            primary_ready = bool(
                runtime_snapshot.get("primary_ready", runtime_snapshot.get("ready", False))
            )
            premium_ready = bool(runtime_snapshot.get("premium_ready", False))
            lifecycle_state = str(
                runtime_snapshot.get("lifecycle_state", "unknown") or "unknown"
            ).strip()
            startup_mode = str(runtime_snapshot.get("startup_mode", "unknown") or "unknown").strip()

            if allow_degraded:
                runtime_ok = (
                    primary_ready
                    and lifecycle_state in {"ready", "degraded"}
                    and startup_mode in {"premium", "limited", "degraded"}
                )
                remediation = (
                    "Resolve primary runtime failures until primary_ready becomes true. "
                    "Then inspect premium blockers separately."
                )
            else:
                runtime_ok = (
                    premium_ready
                    and primary_ready
                    and lifecycle_state == "ready"
                    and startup_mode == "premium"
                )
                remediation = (
                    "Resolve premium blockers until lifecycle_state=ready, "
                    "primary_ready=true and premium_ready=true."
                )

            checks.append(
                BootAcceptanceCheck(
                    key="runtime-product-state",
                    ok=runtime_ok,
                    details=(
                        f"lifecycle_state={lifecycle_state}, "
                        f"startup_mode={startup_mode}, "
                        f"primary_ready={primary_ready}, "
                        f"premium_ready={premium_ready}"
                    ),
                    remediation=remediation,
                    evidence=dict(runtime_snapshot),
                )
            )

        result_ok = all(check.ok for check in checks)
        return SystemdBootAcceptanceResult(
            ok=result_ok,
            strict_premium=not allow_degraded,
            system_dir=str(target_dir),
            runtime_status_path=str(runtime_status_path),
            checked_unit_names=unit_names,
            checks=checks,
            unit_states=unit_states,
            runtime_snapshot=runtime_snapshot,
            journal_tails=journal_tails,
        )

    def _configured_unit_names(self) -> list[str]:
        app_unit_name = self._cfg_text("app_unit_name", default="nexa.service")
        llm_enabled = bool(self.deployment_cfg.get("llm_service_enabled", False))
        llm_unit_name = self._cfg_text("llm_unit_name", default="nexa-llm.service")

        ordered: list[str] = []
        if llm_enabled:
            ordered.append(llm_unit_name)
        ordered.append(app_unit_name)

        deduplicated: list[str] = []
        for item in ordered:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in deduplicated:
                deduplicated.append(cleaned)
        return deduplicated

    def _runtime_status_path(self) -> Path:
        configured = str(
            self.runtime_product_cfg.get("status_path", "var/data/runtime_status.json") or ""
        ).strip()
        return self._resolve_project_path(configured or "var/data/runtime_status.json")

    def _systemctl_show(self, unit_name: str) -> dict[str, str]:
        completed = self._run_command(
            [
                "systemctl",
                "show",
                unit_name,
                "--no-pager",
                "--property",
                "ActiveState,SubState,UnitFileState,FragmentPath,Result,ExecMainStatus",
            ]
        )
        if completed.returncode != 0:
            error_text = (completed.stderr or completed.stdout or "").strip()
            return {"__error__": error_text or f"systemctl show failed for {unit_name}"}

        parsed = self._parse_key_value_lines(completed.stdout)
        if not parsed:
            return {"__error__": f"empty systemctl output for {unit_name}"}
        return parsed

    def _journal_tail(self, unit_name: str, *, lines: int) -> str:
        completed = self._run_command(
            ["journalctl", "-u", unit_name, "-n", str(max(1, int(lines))), "--no-pager"]
        )
        output = (completed.stdout or "").strip()
        if output:
            return output

        error_text = (completed.stderr or "").strip()
        if error_text:
            return error_text

        return "<no journal output>"

    @staticmethod
    def _parse_key_value_lines(text: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip()
        return parsed

    def _load_runtime_snapshot(self, path: Path) -> tuple[dict[str, Any], str]:
        if not path.exists():
            return {}, f"Runtime status file does not exist: {path}"

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            return {}, f"Runtime status file is not valid JSON: {error}"

        if not isinstance(payload, dict):
            return {}, "Runtime status file is not a JSON object"

        return payload, ""

    @staticmethod
    def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
        )

    def _resolve_project_path(self, value: str | Path | None) -> Path:
        candidate = Path(value or "").expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.project_root / candidate).resolve()

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {}) if isinstance(self.settings, dict) else {}
        return value if isinstance(value, dict) else {}

    def _cfg_text(self, key: str, *, default: str) -> str:
        value = self.deployment_cfg.get(key, default)
        text = str(value if value is not None else default).strip()
        return text or default