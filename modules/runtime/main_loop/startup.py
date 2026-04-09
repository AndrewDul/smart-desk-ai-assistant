from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING, Any

from modules.runtime.health import RuntimeHealthChecker
from modules.shared.logging.logger import append_log

from .backend_helpers import (
    _backend_status_for,
    _component_label,
    _resolve_wake_backend,
    _wake_backend_shares_voice_input,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


def _collect_runtime_warnings(assistant: CoreAssistant) -> list[str]:
    warnings: list[str] = []
    for component, status in assistant.backend_statuses.items():
        label = _component_label(component)

        if component == "wake_gate":
            selected_backend = str(getattr(status, "selected_backend", "") or "").strip().lower()
            voice_input_status = _backend_status_for(assistant, "voice_input")
            compatibility_ready = (
                selected_backend == "compatibility_voice_input"
                and bool(getattr(status, "ok", False))
                and bool(getattr(voice_input_status, "ok", False))
            )
            if compatibility_ready:
                continue

        if status.ok and not status.fallback_used:
            continue
        if status.fallback_used and status.ok:
            warnings.append(f"{label}: fallback active")
            continue
        if status.fallback_used:
            warnings.append(f"{label}: degraded fallback")
            continue
        warnings.append(f"{label}: limited")
    return warnings


def _log_startup_summary(report: Any, assistant: CoreAssistant, runtime_warnings: list[str]) -> None:
    append_log("Startup summary begins.")

    if report.startup_allowed:
        append_log("Startup health report: no blocking critical issues.")
    else:
        append_log("Startup health report: critical issues detected, runtime may be degraded.")

    for item in report.items:
        level = "OK" if item.ok else item.severity.value.upper()
        append_log(f"Startup health item [{level}] {item.name}: {item.details}")

    for component, status in assistant.backend_statuses.items():
        level = "OK" if status.ok and not status.fallback_used else "WARN"
        append_log(
            f"Runtime backend item [{level}] {component}: "
            f"backend={status.selected_backend}, fallback={status.fallback_used}, detail={status.detail}"
        )

    if runtime_warnings:
        append_log(f"Runtime warning summary: {' | '.join(runtime_warnings)}")
    else:
        append_log("Runtime warning summary: none")

    append_log("Startup summary ends.")


def _run_startup_sequence(assistant: CoreAssistant) -> None:
    append_log("Startup sequence initiated.")
    checker = RuntimeHealthChecker(assistant.settings)
    report = checker.run()
    runtime_warnings = _collect_runtime_warnings(assistant)

    assistant._boot_report_ok = report.startup_allowed and not runtime_warnings
    _log_startup_summary(report, assistant, runtime_warnings)
    assistant.boot()


def _perform_system_shutdown(assistant: CoreAssistant) -> None:
    system_cfg = assistant.settings.get("system", {})
    allow_shutdown = bool(system_cfg.get("allow_shutdown_commands", False))
    if not allow_shutdown:
        append_log("Shutdown requested, but system shutdown commands are disabled in config.")
        print("System shutdown requested, but shutdown commands are disabled in config.")
        return

    shutdown_command = system_cfg.get("shutdown_command")
    if isinstance(shutdown_command, list) and shutdown_command:
        cmd = [str(part) for part in shutdown_command]
    elif shutil.which("systemctl"):
        cmd = ["systemctl", "poweroff"]
    elif shutil.which("shutdown"):
        cmd = ["shutdown", "-h", "now"]
    else:
        append_log("Shutdown requested, but no supported shutdown command was found.")
        print("Shutdown requested, but no supported shutdown command was found.")
        return

    append_log(f"Executing system shutdown command: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=False)
    except Exception as error:
        append_log(f"System shutdown command failed: {error}")
        print(f"System shutdown command failed: {error}")


def _log_runtime_mode(assistant: CoreAssistant) -> None:
    wake_backend, backend_label = _resolve_wake_backend(assistant)
    wake_name = wake_backend.__class__.__name__ if wake_backend is not None else "none"
    shared_note = (
        " Compatibility wake shares the main voice input backend and keeps a single input owner across standby and command capture."
        if _wake_backend_shares_voice_input(assistant, wake_backend)
        else " Dedicated wake capture owns the microphone only in standby."
    )
    fallback_note = " Standby STT wake fallback is disabled."
    append_log(
        "Half-duplex voice mode active. "
        f"Wake path={backend_label} ({wake_name}). "
        "Wake barge-in during assistant speech is disabled to prevent self-interruptions."
        f"{shared_note}{fallback_note}"
    )
    print("Voice mode: half-duplex (assistant will not listen while speaking).")