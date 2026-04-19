from __future__ import annotations

import getpass
import os
import shlex
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modules.shared.config.settings import load_settings
from modules.shared.persistence.paths import APP_ROOT, ensure_runtime_directories

from .models import (
    DeploymentBackupRecord,
    DeploymentInstallResult,
    DeploymentRenderResult,
    DeploymentRollbackResult,
    DeploymentUninstallResult,
    SystemdUnitSpec,
)


class SystemdDeploymentService:
    """Render, install, rollback and remove systemd units for NeXa."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()
        self.project_root = APP_ROOT
        self.deployment_cfg = self._cfg("deployment")

    def render_units(self) -> DeploymentRenderResult:
        ensure_runtime_directories()
        app_spec = self._build_app_unit_spec()
        llm_spec = self._build_llm_unit_spec()

        if llm_spec is not None:
            app_spec.after = self._merge_unit_refs(app_spec.after, [llm_spec.unit_name])
            app_spec.wants = self._merge_unit_refs(app_spec.wants, [llm_spec.unit_name])

        output_dir = self._resolve_output_dir()
        rendered_units: dict[str, str] = {
            app_spec.unit_name: self._render_unit_text(app_spec),
        }
        if llm_spec is not None:
            rendered_units[llm_spec.unit_name] = self._render_unit_text(llm_spec)

        unit_paths = {name: str((output_dir / name).resolve()) for name in rendered_units}
        return DeploymentRenderResult(
            output_dir=str(output_dir),
            rendered_units=rendered_units,
            unit_paths=unit_paths,
            llm_unit_enabled=llm_spec is not None,
        )

    def write_units(self) -> DeploymentRenderResult:
        result = self.render_units()
        output_dir = Path(result.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for unit_name, unit_text in result.rendered_units.items():
            unit_path = output_dir / unit_name
            unit_path.write_text(unit_text, encoding="utf-8")

        return result

    def install_units(
        self,
        *,
        system_dir: str = "/etc/systemd/system",
        enable: bool = True,
        start: bool = False,
        backup_existing: bool = True,
        backup_dir: str | None = None,
    ) -> DeploymentInstallResult:
        result = self.write_units()
        target_dir = Path(system_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        installed_unit_paths: dict[str, str] = {}
        backup_records: list[DeploymentBackupRecord] = []
        backup_session_dir: Path | None = None

        for unit_name in self._ordered_unit_names(result):
            source_path = Path(result.unit_paths[unit_name]).resolve()
            target_path = (target_dir / unit_name).resolve()

            if backup_existing and target_path.exists():
                if backup_session_dir is None:
                    backup_session_dir = self._prepare_backup_dir(backup_dir)
                backup_path = (backup_session_dir / unit_name).resolve()
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, backup_path)
                backup_records.append(
                    DeploymentBackupRecord(
                        unit_name=unit_name,
                        source_path=str(target_path),
                        backup_path=str(backup_path),
                    )
                )

            shutil.copy2(source_path, target_path)
            installed_unit_paths[unit_name] = str(target_path)

        self._systemctl(["daemon-reload"])

        ordered_units = self._ordered_unit_names(result)
        if enable:
            for unit_name in ordered_units:
                self._systemctl(["enable", unit_name])

        if start:
            for unit_name in ordered_units:
                self._systemctl(["restart", unit_name])

        return DeploymentInstallResult(
            output_dir=result.output_dir,
            rendered_units=dict(result.rendered_units),
            unit_paths=dict(result.unit_paths),
            llm_unit_enabled=result.llm_unit_enabled,
            system_dir=str(target_dir),
            installed_unit_paths=installed_unit_paths,
            backup_dir=str(backup_session_dir) if backup_session_dir is not None else "",
            backup_records=backup_records,
        )

    def rollback_units(
        self,
        *,
        system_dir: str = "/etc/systemd/system",
        backup_dir: str,
        enable: bool = True,
        start: bool = False,
        remove_units_not_in_backup: bool = True,
    ) -> DeploymentRollbackResult:
        target_dir = Path(system_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        backup_path = Path(backup_dir).expanduser().resolve()
        if not backup_path.exists() or not backup_path.is_dir():
            raise FileNotFoundError(f"Systemd backup directory not found: {backup_path}")

        configured_units = self._configured_unit_names(include_llm=True)
        restored_unit_paths: dict[str, str] = {}
        removed_unit_paths: list[str] = []

        for unit_name in configured_units:
            source_path = (backup_path / unit_name).resolve()
            target_path = (target_dir / unit_name).resolve()

            if source_path.exists():
                shutil.copy2(source_path, target_path)
                restored_unit_paths[unit_name] = str(target_path)
                continue

            if remove_units_not_in_backup and target_path.exists():
                target_path.unlink()
                removed_unit_paths.append(str(target_path))

        self._systemctl(["daemon-reload"])

        ordered_restored_units = [
            unit_name for unit_name in self._ordered_configured_unit_names() if unit_name in restored_unit_paths
        ]
        if enable:
            for unit_name in ordered_restored_units:
                self._systemctl(["enable", unit_name])

        if start:
            for unit_name in ordered_restored_units:
                self._systemctl(["restart", unit_name])

        return DeploymentRollbackResult(
            system_dir=str(target_dir),
            backup_dir=str(backup_path),
            restored_unit_paths=restored_unit_paths,
            removed_unit_paths=removed_unit_paths,
            restored_unit_names=ordered_restored_units,
        )

    def uninstall_units(
        self,
        *,
        system_dir: str = "/etc/systemd/system",
        disable: bool = True,
        stop: bool = True,
    ) -> DeploymentUninstallResult:
        target_dir = Path(system_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        ordered_units = self._ordered_configured_unit_names()
        stop_disable_order = list(reversed(ordered_units))

        stopped_unit_names: list[str] = []
        if stop:
            for unit_name in stop_disable_order:
                self._systemctl(["stop", unit_name])
                stopped_unit_names.append(unit_name)

        disabled_unit_names: list[str] = []
        if disable:
            for unit_name in stop_disable_order:
                self._systemctl(["disable", unit_name])
                disabled_unit_names.append(unit_name)

        removed_unit_paths: list[str] = []
        missing_unit_names: list[str] = []
        for unit_name in ordered_units:
            target_path = (target_dir / unit_name).resolve()
            if target_path.exists():
                target_path.unlink()
                removed_unit_paths.append(str(target_path))
            else:
                missing_unit_names.append(unit_name)

        self._systemctl(["daemon-reload"])

        return DeploymentUninstallResult(
            system_dir=str(target_dir),
            removed_unit_paths=removed_unit_paths,
            missing_unit_names=missing_unit_names,
            stopped_unit_names=stopped_unit_names,
            disabled_unit_names=disabled_unit_names,
        )

    def describe_remaining_scope(self) -> list[str]:
        return [
            "real Raspberry Pi deployment verification with generated systemd units",
            "acceptance run on hardware and latency tuning based on benchmark data",
            "operational docs: install, update, rollback, logs, recovery",
            "final production checklist for LLM backend, audio devices, and boot behavior",
        ]

    def _build_app_unit_spec(self) -> SystemdUnitSpec:
        python_path = self._resolve_python_path()
        unit_name = self._cfg_text("app_unit_name", default="nexa.service")
        user_name = self._default_service_user()
        group_name = self._default_service_group(user_name)

        environment = {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "NEXA_RUNTIME_MODE": "systemd",
            **self._cfg_environment("app_environment"),
        }

        return SystemdUnitSpec(
            unit_name=unit_name,
            description="NeXa premium local voice assistant",
            exec_start=[python_path, str((self.project_root / "main.py").resolve())],
            working_directory=str(self.project_root),
            after=["network-online.target", "sound.target"],
            wants=["network-online.target", "sound.target"],
            user=user_name,
            group=group_name,
            restart=self._cfg_text("app_restart", default="on-failure"),
            restart_sec=self._cfg_float("app_restart_sec", default=2.0),
            start_limit_interval_sec=self._cfg_int("app_start_limit_interval_sec", default=30),
            start_limit_burst=self._cfg_int("app_start_limit_burst", default=5),
            timeout_stop_sec=self._cfg_float("app_timeout_stop_sec", default=25.0),
            kill_signal=self._cfg_text("app_kill_signal", default="SIGINT"),
            environment=environment,
            environment_file=self._resolve_optional_text_path("environment_file"),
        )

    def _build_llm_unit_spec(self) -> SystemdUnitSpec | None:
        if not bool(self.deployment_cfg.get("llm_service_enabled", False)):
            return None

        command = self._cfg_command("llm_service_command")
        if not command:
            return None

        unit_name = self._cfg_text("llm_unit_name", default="nexa-llm.service")
        user_name = self._default_service_user()
        group_name = self._default_service_group(user_name)
        working_directory = self._resolve_optional_text_path("llm_service_working_directory") or str(self.project_root)

        environment = {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            **self._cfg_environment("llm_environment"),
        }

        return SystemdUnitSpec(
            unit_name=unit_name,
            description="NeXa local LLM backend",
            exec_start=command,
            working_directory=working_directory,
            after=["network-online.target"],
            wants=["network-online.target"],
            user=user_name,
            group=group_name,
            restart=self._cfg_text("llm_restart", default="on-failure"),
            restart_sec=self._cfg_float("llm_restart_sec", default=2.0),
            start_limit_interval_sec=self._cfg_int("llm_start_limit_interval_sec", default=30),
            start_limit_burst=self._cfg_int("llm_start_limit_burst", default=5),
            timeout_stop_sec=self._cfg_float("llm_timeout_stop_sec", default=20.0),
            kill_signal=self._cfg_text("llm_kill_signal", default="SIGTERM"),
            environment=environment,
            environment_file=self._resolve_optional_text_path("environment_file"),
        )

    @staticmethod
    def _render_unit_text(spec: SystemdUnitSpec) -> str:
        lines: list[str] = ["[Unit]"]
        lines.append(f"Description={spec.description}")
        if spec.after:
            lines.append(f"After={' '.join(spec.after)}")
        if spec.wants:
            lines.append(f"Wants={' '.join(spec.wants)}")
        lines.append(f"StartLimitIntervalSec={int(spec.start_limit_interval_sec)}")
        lines.append(f"StartLimitBurst={int(spec.start_limit_burst)}")
        lines.append("")

        lines.append("[Service]")
        lines.append(f"Type={spec.service_type}")
        lines.append(f"WorkingDirectory={spec.working_directory}")
        if spec.user:
            lines.append(f"User={spec.user}")
        if spec.group:
            lines.append(f"Group={spec.group}")
        if spec.environment_file:
            lines.append(f"EnvironmentFile=-{spec.environment_file}")
        for key, value in sorted(spec.environment.items()):
            lines.append(f"Environment={key}={shlex.quote(str(value))}")
        lines.append(f"ExecStart={shlex.join(spec.exec_start)}")
        lines.append(f"Restart={spec.restart}")
        lines.append(f"RestartSec={float(spec.restart_sec):.1f}")
        lines.append(f"TimeoutStopSec={float(spec.timeout_stop_sec):.1f}")
        lines.append(f"KillSignal={spec.kill_signal}")
        lines.append(f"StandardOutput={spec.standard_output}")
        lines.append(f"StandardError={spec.standard_error}")
        lines.append("")

        lines.append("[Install]")
        wanted_by = spec.wanted_by or ["multi-user.target"]
        lines.append(f"WantedBy={' '.join(wanted_by)}")
        lines.append("")

        return "\n".join(lines)

    def _ordered_unit_names(self, result: DeploymentRenderResult) -> list[str]:
        unit_names = list(result.rendered_units.keys())
        if not result.llm_unit_enabled:
            return unit_names

        llm_unit_name = self._cfg_text("llm_unit_name", default="nexa-llm.service")
        app_unit_name = self._cfg_text("app_unit_name", default="nexa.service")
        ordered: list[str] = []

        for item in (llm_unit_name, app_unit_name):
            if item in unit_names and item not in ordered:
                ordered.append(item)

        for item in unit_names:
            if item not in ordered:
                ordered.append(item)

        return ordered

    def _ordered_configured_unit_names(self) -> list[str]:
        unit_names = self._configured_unit_names(include_llm=True)
        llm_unit_name = self._cfg_text("llm_unit_name", default="nexa-llm.service")
        app_unit_name = self._cfg_text("app_unit_name", default="nexa.service")
        ordered: list[str] = []

        for item in (llm_unit_name, app_unit_name):
            if item in unit_names and item not in ordered:
                ordered.append(item)

        for item in unit_names:
            if item not in ordered:
                ordered.append(item)

        return ordered

    def _configured_unit_names(self, *, include_llm: bool) -> list[str]:
        unit_names = [self._cfg_text("app_unit_name", default="nexa.service")]
        if include_llm:
            unit_names.append(self._cfg_text("llm_unit_name", default="nexa-llm.service"))

        ordered: list[str] = []
        for item in unit_names:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in ordered:
                ordered.append(cleaned)
        return ordered

    def _resolve_output_dir(self) -> Path:
        resolved = self._resolve_project_path(self._cfg_text("unit_output_dir", default="deploy/systemd"))
        if resolved is None:
            return (self.project_root / "deploy" / "systemd").resolve()
        return resolved

    def _resolve_python_path(self) -> str:
        configured = self._cfg_text("python_path", default=".venv/bin/python")
        candidate = Path(configured).expanduser()

        if not candidate.is_absolute():
            candidate = self.project_root / candidate

        if candidate.exists():
            return str(candidate)

        return configured

    def _resolve_optional_text_path(self, key: str) -> str:
        configured = self._cfg_text(key, default="")
        if not configured:
            return ""
        resolved = self._resolve_project_path(configured)
        return str(resolved) if resolved is not None else configured

    def _resolve_project_path(self, value: str | Path | None) -> Path | None:
        if value is None:
            return None

        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()

        return (self.project_root / candidate).resolve()

    def _default_backup_root(self) -> Path:
        return (self.project_root / "deploy" / "systemd-backups").resolve()

    def _prepare_backup_dir(self, configured_backup_dir: str | None) -> Path:
        base_dir = self._resolve_project_path(configured_backup_dir) if configured_backup_dir else self._default_backup_root()
        assert base_dir is not None
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = (base_dir / timestamp).resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def _default_service_user(self) -> str:
        explicit = str(self.deployment_cfg.get("user", "") or "").strip()
        if explicit:
            return explicit

        sudo_user = str(os.environ.get("SUDO_USER", "") or "").strip()
        if sudo_user and sudo_user.lower() != "root":
            return sudo_user

        current_user = getpass.getuser()
        if current_user.lower() == "root":
            return ""
        return current_user

    def _default_service_group(self, user_name: str) -> str:
        explicit = str(self.deployment_cfg.get("group", "") or "").strip()
        if explicit:
            return explicit
        return str(user_name or "").strip()

    def _cfg_command(self, key: str) -> list[str]:
        value = self.deployment_cfg.get(key, [])
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return shlex.split(value)
        return []

    def _cfg_environment(self, key: str) -> dict[str, str]:
        value = self.deployment_cfg.get(key, {})
        if not isinstance(value, dict):
            return {}
        return {
            str(env_key): str(env_value)
            for env_key, env_value in value.items()
            if str(env_key).strip()
        }

    def _cfg_text(self, key: str, *, default: str) -> str:
        value = self.deployment_cfg.get(key, default)
        text = str(value if value is not None else default).strip()
        return text or default

    def _cfg_int(self, key: str, *, default: int) -> int:
        try:
            return int(self.deployment_cfg.get(key, default))
        except (TypeError, ValueError):
            return int(default)

    def _cfg_float(self, key: str, *, default: float) -> float:
        try:
            return float(self.deployment_cfg.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {}) if isinstance(self.settings, dict) else {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _merge_unit_refs(existing: list[str], extra: list[str]) -> list[str]:
        merged: list[str] = []
        for item in [*existing, *extra]:
            cleaned = str(item or "").strip()
            if not cleaned or cleaned in merged:
                continue
            merged.append(cleaned)
        return merged

    @staticmethod
    def _systemctl(args: list[str]) -> None:
        cmd = ["systemctl", *args]
        subprocess.run(cmd, check=True)


__all__ = ["SystemdDeploymentService"]