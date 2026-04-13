from __future__ import annotations
import os
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


def _evaluate_runtime_productization(
    assistant: CoreAssistant,
    *,
    report: Any,
    runtime_warnings: list[str],
) -> dict[str, Any]:
    runtime_product = getattr(assistant, "runtime_product", None)
    if runtime_product is None:
        return {}

    begin_boot = getattr(runtime_product, "begin_boot", None)
    if callable(begin_boot):
        try:
            begin_boot(
                startup_allowed=bool(getattr(report, "startup_allowed", False)),
                warnings=runtime_warnings,
            )
        except Exception as error:
            append_log(f"Runtime product begin_boot failed: {error}")

    evaluate_startup = getattr(runtime_product, "evaluate_startup", None)
    if not callable(evaluate_startup):
        return {}

    try:
        snapshot = evaluate_startup(
            startup_allowed=bool(getattr(report, "startup_allowed", False)),
            runtime_warnings=runtime_warnings,
        )
    except Exception as error:
        append_log(f"Runtime product startup evaluation failed: {error}")
        return {}

    return dict(snapshot) if isinstance(snapshot, dict) else {}


def _log_startup_summary(
    report: Any,
    assistant: CoreAssistant,
    runtime_warnings: list[str],
    runtime_snapshot: dict[str, Any],
) -> None:
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

    if runtime_snapshot:
        append_log(
            "Runtime product state: "
            f"lifecycle={runtime_snapshot.get('lifecycle_state', '')}, "
            f"ready={bool(runtime_snapshot.get('ready', False))}, "
            f"primary_ready={bool(runtime_snapshot.get('primary_ready', False))}, "
            f"premium_ready={bool(runtime_snapshot.get('premium_ready', False))}, "
            f"degraded={bool(runtime_snapshot.get('degraded', False))}, "
            f"message={runtime_snapshot.get('status_message', '')}"
        )

        blockers = list(runtime_snapshot.get("blockers", []) or [])
        warnings = list(runtime_snapshot.get("warnings", []) or [])
        services = dict(runtime_snapshot.get("services", {}) or {})

        if blockers:
            append_log(f"Runtime startup blockers: {' | '.join(str(item) for item in blockers)}")
        if warnings:
            append_log(f"Runtime startup warnings: {' | '.join(str(item) for item in warnings)}")

        for component, payload in services.items():
            if not isinstance(payload, dict):
                continue

            append_log(
                "Runtime product service: "
                f"component={component}, state={payload.get('state', '')}, "
                f"backend={payload.get('backend', '')}, detail={payload.get('detail', '')}, "
                f"required={bool(payload.get('required', False))}, "
                f"recovery_attempted={bool(payload.get('recovery_attempted', False))}, "
                f"recovery_ok={bool(payload.get('recovery_ok', False))}"
            )
        provider_inventory = dict(runtime_snapshot.get("provider_inventory", {}) or {})
        for component, payload in provider_inventory.items():
            if not isinstance(payload, dict):
                continue

            append_log(
                "Runtime provider inventory: "
                f"component={component}, "
                f"requested={payload.get('requested_backend', '')}, "
                f"selected={payload.get('selected_backend', '')}, "
                f"state={payload.get('state', '')}, "
                f"mode={payload.get('runtime_mode', '')}, "
                f"primary={bool(payload.get('primary', False))}, "
                f"compatibility={bool(payload.get('compatibility_mode', False))}, "
                f"fallback={bool(payload.get('fallback_used', False))}"
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
    runtime_snapshot = _evaluate_runtime_productization(
        assistant,
        report=report,
        runtime_warnings=runtime_warnings,
    )

    assistant._runtime_startup_snapshot = runtime_snapshot
    assistant._boot_report_ok = bool(
        runtime_snapshot.get("ready", report.startup_allowed and not runtime_warnings)
    )
    _log_startup_summary(report, assistant, runtime_warnings, runtime_snapshot)
    runtime_mode = str(os.getenv("NEXA_RUNTIME_MODE", "") or "").strip().lower()
    blockers = [str(item).strip() for item in runtime_snapshot.get("blockers", []) if str(item).strip()]
    if runtime_mode == "systemd" and blockers:
        blocker_text = ", ".join(blockers)
        append_log(
            "Systemd startup aborted because required runtime components are unavailable: "
            f"{blocker_text}"
        )
        raise RuntimeError(
            "Required runtime components unavailable during systemd startup: "
            f"{blocker_text}"
        )
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
    runtime_snapshot = getattr(assistant, "_runtime_startup_snapshot", {}) or {}
    lifecycle_state = str(runtime_snapshot.get("lifecycle_state", "unknown") or "unknown").strip().upper()
    status_message = str(runtime_snapshot.get("status_message", "") or "").strip()

    wake_backend, backend_label = _resolve_wake_backend(assistant)
    wake_name = wake_backend.__class__.__name__ if wake_backend is not None else "none"
    shared_note = (
        " Compatibility wake shares the main voice input backend and keeps a single input owner across standby and command capture."
        if _wake_backend_shares_voice_input(assistant, wake_backend)
        else " Dedicated wake capture owns the microphone only in standby."
    )
    fallback_note = " Standby STT wake fallback is disabled."

    append_log(
        f"Runtime state={lifecycle_state}. "
        "Half-duplex voice mode active. "
        f"Wake path={backend_label} ({wake_name}). "
        "Wake barge-in during assistant speech is disabled to prevent self-interruptions."
        f"{shared_note}{fallback_note}"
        + (f" Status: {status_message}." if status_message else "")
    )
    print(f"Runtime state: {lifecycle_state}. Voice mode: half-duplex.")