from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SystemdUnitSpec:
    unit_name: str
    description: str
    exec_start: list[str]
    working_directory: str
    service_type: str = "simple"
    after: list[str] = field(default_factory=list)
    wants: list[str] = field(default_factory=list)
    user: str = ""
    group: str = ""
    restart: str = "on-failure"
    restart_sec: float = 2.0
    start_limit_interval_sec: int = 30
    start_limit_burst: int = 5
    timeout_stop_sec: float = 20.0
    kill_signal: str = "SIGINT"
    environment: dict[str, str] = field(default_factory=dict)
    environment_file: str = ""
    standard_output: str = "journal"
    standard_error: str = "journal"
    wanted_by: list[str] = field(default_factory=lambda: ["multi-user.target"])


@dataclass(slots=True)
class DeploymentRenderResult:
    output_dir: str
    rendered_units: dict[str, str] = field(default_factory=dict)
    unit_paths: dict[str, str] = field(default_factory=dict)
    llm_unit_enabled: bool = False


@dataclass(slots=True)
class DeploymentBackupRecord:
    unit_name: str
    source_path: str
    backup_path: str


@dataclass(slots=True)
class DeploymentInstallResult(DeploymentRenderResult):
    system_dir: str = ""
    installed_unit_paths: dict[str, str] = field(default_factory=dict)
    backup_dir: str = ""
    backup_records: list[DeploymentBackupRecord] = field(default_factory=list)


@dataclass(slots=True)
class DeploymentRollbackResult:
    system_dir: str
    backup_dir: str
    restored_unit_paths: dict[str, str] = field(default_factory=dict)
    removed_unit_paths: list[str] = field(default_factory=list)
    restored_unit_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DeploymentUninstallResult:
    system_dir: str
    removed_unit_paths: list[str] = field(default_factory=list)
    missing_unit_names: list[str] = field(default_factory=list)
    stopped_unit_names: list[str] = field(default_factory=list)
    disabled_unit_names: list[str] = field(default_factory=list)


__all__ = [
    "DeploymentBackupRecord",
    "DeploymentInstallResult",
    "DeploymentRenderResult",
    "DeploymentRollbackResult",
    "DeploymentUninstallResult",
    "SystemdUnitSpec",
]