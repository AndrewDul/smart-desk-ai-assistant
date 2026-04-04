from __future__ import annotations

import re
import shutil
import subprocess
import time
import unicodedata

from modules.core.assistant import CoreAssistant
from modules.system.system_health import SystemHealthChecker
from modules.system.utils import append_log


def _normalize_gate_text(text: str) -> str:
    lowered = text.lower().strip()
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
    lowered = lowered.replace("ł", "l")
    lowered = re.sub(r"[^a-z0-9\s\[\]().,_-]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _is_blank_or_silence(text: str) -> bool:
    normalized = _normalize_gate_text(text)

    blank_markers = {
        "",
        "blank audio",
        "[blank_audio]",
        "blank_audio",
        "[ silence ]",
        "silence",
        "no speech",
        "no speech recognized",
        "[noise]",
        "noise",
        "...",
        ".",
        "-",
    }

    return normalized in blank_markers


def _is_bracketed_non_speech(text: str) -> bool:
    normalized = _normalize_gate_text(text)
    if not normalized:
        return True

    bracketed_patterns = [
        r"^\[[a-z0-9 _-]+\]$",
        r"^\([a-z0-9 _-]+\)$",
    ]
    if not any(re.fullmatch(pattern, normalized) for pattern in bracketed_patterns):
        return False

    inner = re.sub(r"^[\[(]|[\])]\Z", "", normalized).strip()

    non_speech_terms = {
        "music",
        "upbeat music",
        "applause",
        "laughter",
        "background noise",
        "ambient sound",
        "static",
        "noise",
        "silence",
        "coughing",
        "breathing",
        "sigh",
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "desk hit",
        "clap",
        "clapping",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }

    return inner in non_speech_terms


def _looks_like_non_speech_description(normalized: str) -> bool:
    if not normalized:
        return True

    exact_non_speech = {
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "desk hit",
        "clap",
        "clapping",
        "applause",
        "music",
        "laughter",
        "noise",
        "static",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }

    if normalized in exact_non_speech:
        return True

    non_speech_keywords = {
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "clap",
        "clapping",
        "applause",
        "music",
        "noise",
        "static",
        "stukanie",
        "klawiatura",
        "krzeslo",
        "klasniecie",
        "klaskanie",
    }

    tokens = set(normalized.split())
    if tokens and tokens.issubset(non_speech_keywords):
        return True

    if len(tokens) <= 4 and (tokens & non_speech_keywords):
        return True

    return False


def _is_low_value_noise(text: str, assistant: CoreAssistant) -> bool:
    if assistant.pending_follow_up or assistant.pending_confirmation:
        return False

    normalized = _normalize_gate_text(text)
    if not normalized:
        return True

    filler_words = {
        "uh",
        "um",
        "hmm",
        "hm",
        "mmm",
        "ah",
        "eh",
        "yyy",
        "eee",
        "ok",
        "okay",
        "huh",
    }

    silence_hallucinations = {
        "thank you",
        "thanks for watching",
        "you",
        "bye",
        "foreign",
        "speaking in foreign language",
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "clap",
        "clapping",
        "applause",
        "music",
        "noise",
        "static",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }

    if normalized in filler_words:
        return True

    if normalized in silence_hallucinations:
        return True

    if _looks_like_non_speech_description(normalized):
        return True

    if not re.search(r"[a-z]", normalized):
        return True

    alpha_only = re.sub(r"[^a-z]", "", normalized)
    if len(alpha_only) <= 1:
        return True

    return False


def _should_ignore_duplicate_transcript(
    text: str,
    assistant: CoreAssistant,
    last_transcript_normalized: str | None,
    last_transcript_time: float | None,
    cooldown_seconds: float = 1.4,
) -> bool:
    if assistant.pending_follow_up or assistant.pending_confirmation:
        return False

    normalized = _normalize_gate_text(text)
    if not normalized:
        return False

    if last_transcript_normalized is None or last_transcript_time is None:
        return False

    now = time.monotonic()
    return normalized == last_transcript_normalized and (now - last_transcript_time) <= cooldown_seconds


def _should_log_gate_event(
    gate_event: str,
    gate_log_times: dict[str, float],
    cooldown_seconds: float = 5.0,
) -> bool:
    now = time.monotonic()
    last_time = gate_log_times.get(gate_event)

    if last_time is None or (now - last_time) >= cooldown_seconds:
        gate_log_times[gate_event] = now
        return True

    return False


def _component_label(component: str) -> str:
    labels = {
        "voice_input": "voice input",
        "voice_output": "voice output",
        "display": "display",
    }
    return labels.get(component, component.replace("_", " "))


def _collect_runtime_warnings(assistant: CoreAssistant) -> list[str]:
    warnings: list[str] = []

    for component in ("voice_input", "voice_output", "display"):
        status = assistant.backend_statuses.get(component)
        if status is None:
            continue

        label = _component_label(component)

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


def _collect_health_failures(report) -> list[str]:
    failures: list[str] = []

    for item in report.items:
        if not item.ok:
            failures.append(f"{item.name}: {item.details}")

    return failures


def _startup_overlay_lines(report, runtime_warnings: list[str]) -> list[str]:
    if report.ok and not runtime_warnings:
        return [
            "startup checks ok",
            "voice loop ready",
        ]

    if runtime_warnings:
        primary_warning = runtime_warnings[0][:20]
        return [
            "startup warnings",
            primary_warning,
        ]

    failed_items = [item for item in report.items if not item.ok]
    if failed_items:
        primary_issue = failed_items[0].name[:20]
        return [
            "startup warnings",
            primary_issue,
        ]

    return [
        "startup warnings",
        "check system log",
    ]


def _startup_greeting(report_ok: bool, runtime_warnings: list[str]) -> str:
    if report_ok and not runtime_warnings:
        return "Hello. I am NeXa. Startup checks look good. You can ask me at any time how I can help."

    if runtime_warnings:
        return (
            "Hello. I am NeXa. I started with some limited components, "
            "but I am ready and listening."
        )

    return (
        "Hello. I am NeXa. Startup finished with warnings, "
        "but I am ready and listening."
    )


def _log_startup_summary(report, assistant: CoreAssistant, runtime_warnings: list[str]) -> None:
    append_log("Startup summary begins.")

    if report.ok:
        append_log("Startup health report: all configured checks passed.")
    else:
        append_log("Startup health report: one or more checks reported warnings.")

    for item in report.items:
        level = "OK" if item.ok else "WARN"
        append_log(f"Startup health item [{level}] {item.name}: {item.details}")

    for component in ("voice_input", "voice_output", "display"):
        status = assistant.backend_statuses.get(component)
        if status is None:
            continue

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

    checker = SystemHealthChecker(assistant.settings)
    report = checker.run()
    runtime_warnings = _collect_runtime_warnings(assistant)
    health_failures = _collect_health_failures(report)

    assistant.last_language = "en"
    assistant.pending_follow_up = None
    assistant.pending_confirmation = None
    assistant.shutdown_requested = False

    assistant.state["assistant_running"] = True
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant.state["current_timer"] = None
    assistant._save_state()

    if not assistant._reminder_thread.is_alive():
        assistant._reminder_thread.start()

    assistant.display.show_block(
        "NeXa",
        _startup_overlay_lines(report, runtime_warnings),
        duration=assistant.boot_overlay_seconds,
    )

    time.sleep(max(assistant.boot_overlay_seconds, 0.8))
    assistant.display.clear_overlay()
    time.sleep(0.15)

    startup_message = _startup_greeting(report.ok, runtime_warnings)
    assistant.voice_out.speak(
        startup_message,
        language="en",
    )

    if hasattr(assistant, "_remember_assistant_turn"):
        assistant._remember_assistant_turn(
            startup_message,
            language="en",
            metadata={
                "source": "system",
                "route_kind": "startup",
                "health_ok": report.ok,
                "runtime_warnings": list(runtime_warnings),
                "health_failures": list(health_failures),
            },
        )

    _log_startup_summary(report, assistant, runtime_warnings)

    if report.ok and not runtime_warnings:
        append_log("Startup completed successfully.")
    else:
        append_log("Startup completed with warnings.")


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


def main() -> None:
    assistant = CoreAssistant()
    _run_startup_sequence(assistant)

    gate_log_times: dict[str, float] = {}
    last_transcript_normalized: str | None = None
    last_transcript_time: float | None = None

    try:
        while True:
            print("\nListening for speech...")
            heard_text = assistant.voice_in.listen(
                timeout=assistant.voice_listen_timeout,
                debug=assistant.voice_debug,
            )

            if heard_text is None:
                if _should_log_gate_event("silent_none", gate_log_times):
                    append_log("Ignored silent input: recognizer returned None.")
                print("No speech recognized.")
                continue

            heard_text = heard_text.strip()

            if _is_blank_or_silence(heard_text):
                if _should_log_gate_event("blank_or_silence", gate_log_times):
                    append_log(f"Ignored blank audio marker: {heard_text}")
                print("Ignored blank audio marker.")
                continue

            normalized_heard = _normalize_gate_text(heard_text)

            if not normalized_heard:
                if _should_log_gate_event("empty_normalized", gate_log_times):
                    append_log("Ignored empty normalized transcript.")
                print("Ignored empty normalized transcript.")
                continue

            if _is_bracketed_non_speech(heard_text):
                if _should_log_gate_event("bracketed_non_speech", gate_log_times):
                    append_log(f"Ignored bracketed non-speech transcript: {heard_text}")
                print(f"Ignored non-speech transcript: {heard_text}")
                continue

            if _is_low_value_noise(heard_text, assistant):
                if _should_log_gate_event("low_value_noise", gate_log_times):
                    append_log(f"Ignored low-value noise: {heard_text}")
                print(f"Ignored low-value noise: {heard_text}")
                continue

            if _should_ignore_duplicate_transcript(
                heard_text,
                assistant,
                last_transcript_normalized=last_transcript_normalized,
                last_transcript_time=last_transcript_time,
            ):
                if _should_log_gate_event("duplicate_transcript", gate_log_times):
                    append_log(f"Ignored duplicate transcript: {heard_text}")
                print(f"Ignored duplicate transcript: {heard_text}")
                continue

            print(f"Heard: {heard_text}")

            last_transcript_normalized = normalized_heard
            last_transcript_time = time.monotonic()

            should_continue = assistant.handle_command(heard_text)
            if not should_continue:
                break

    except KeyboardInterrupt:
        print("\nStopping assistant with keyboard interrupt.")
        append_log("Assistant stopped with keyboard interrupt.")

    finally:
        shutdown_requested = assistant.shutdown_requested
        assistant.shutdown()

        if shutdown_requested:
            _perform_system_shutdown(assistant)


if __name__ == "__main__":
    main()