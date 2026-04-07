from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
import traceback
import unicodedata
from importlib import import_module

from modules.core.assistant import CoreAssistant
from modules.core.voice_session import (
    VOICE_STATE_LISTENING,
    VOICE_STATE_ROUTING,
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VOICE_STATE_WAKE_DETECTED,
)
from modules.system.system_health import SystemHealthChecker
from modules.system.utils import append_log


WAKE_GATE_TIMEOUT_SECONDS = 2.4
DEDICATED_WAKE_TIMEOUT_SECONDS = 1.8
POST_COMMAND_WINDOW_SECONDS = 6.0
FOLLOW_UP_WINDOW_SECONDS = 12.0
DUPLICATE_TRANSCRIPT_COOLDOWN_SECONDS = 1.4
ACTIVE_IGNORE_LOG_COOLDOWN_SECONDS = 5.0


def _normalize_gate_text(text: str) -> str:
    lowered = text.lower().strip()
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = lowered.replace("ł", "l")
    lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
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
    *,
    last_transcript_normalized: str | None,
    last_transcript_time: float | None,
    cooldown_seconds: float = DUPLICATE_TRANSCRIPT_COOLDOWN_SECONDS,
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
    cooldown_seconds: float = ACTIVE_IGNORE_LOG_COOLDOWN_SECONDS,
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
            "wake loop ready",
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
        return "Hello. I am NeXa. Startup checks look good. Say NeXa when you need me."

    if runtime_warnings:
        return (
            "Hello. I am NeXa. I started with some limited components, "
            "but I am ready. Say NeXa when you need me."
        )

    return (
        "Hello. I am NeXa. Startup finished with warnings, "
        "but I am ready. Say NeXa when you need me."
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
    assistant.voice_session.close_active_window()

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

    assistant.voice_session.set_state(VOICE_STATE_STANDBY, detail="startup_complete")
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


def _log_ignored_active_transcript(
    event_key: str,
    heard_text: str,
    gate_log_times: dict[str, float],
    message: str,
) -> None:
    if _should_log_gate_event(event_key, gate_log_times):
        append_log(f"Ignored active transcript [{event_key}]: {heard_text}")
    print(message)


def _should_ignore_active_transcript(
    assistant: CoreAssistant,
    heard_text: str,
    gate_log_times: dict[str, float],
    *,
    last_transcript_normalized: str | None,
    last_transcript_time: float | None,
) -> bool:
    if _is_blank_or_silence(heard_text):
        _log_ignored_active_transcript(
            "blank_or_silence",
            heard_text,
            gate_log_times,
            "Ignored blank audio marker.",
        )
        return True

    normalized_heard = _normalize_gate_text(heard_text)
    if not normalized_heard:
        _log_ignored_active_transcript(
            "empty_normalized",
            heard_text,
            gate_log_times,
            "Ignored empty normalized transcript.",
        )
        return True

    if _is_bracketed_non_speech(heard_text):
        _log_ignored_active_transcript(
            "bracketed_non_speech",
            heard_text,
            gate_log_times,
            f"Ignored non-speech transcript: {heard_text}",
        )
        return True

    if _is_low_value_noise(heard_text, assistant):
        _log_ignored_active_transcript(
            "low_value_noise",
            heard_text,
            gate_log_times,
            f"Ignored low-value noise: {heard_text}",
        )
        return True

    if _should_ignore_duplicate_transcript(
        heard_text,
        assistant,
        last_transcript_normalized=last_transcript_normalized,
        last_transcript_time=last_transcript_time,
    ):
        _log_ignored_active_transcript(
            "duplicate_transcript",
            heard_text,
            gate_log_times,
            f"Ignored duplicate transcript: {heard_text}",
        )
        return True

    return False


def _acknowledge_wake(assistant: CoreAssistant) -> None:
    assistant.voice_session.set_state(VOICE_STATE_WAKE_DETECTED, detail="wake_phrase_detected")

    wake_ack = assistant.voice_session.build_wake_acknowledgement()
    assistant.voice_session.set_state(VOICE_STATE_SPEAKING, detail="wake_acknowledgement")
    assistant.voice_out.speak(wake_ack, language="en")

    if hasattr(assistant, "_remember_assistant_turn"):
        assistant._remember_assistant_turn(
            wake_ack,
            language="en",
            metadata={
                "source": "wake_word",
                "route_kind": "wake_ack",
            },
        )

    append_log(f"Wake phrase detected. Acknowledgement spoken: {wake_ack}")
    assistant.voice_session.open_active_window()
    assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail="awaiting_command")
    print("Wake phrase detected. Waiting for command...")


def _assistant_output_blocks_input(assistant: CoreAssistant) -> bool:
    coordinator = getattr(assistant, "audio_coordinator", None)
    if coordinator is None:
        return False

    try:
        blocked = bool(coordinator.input_blocked())
    except Exception:
        return False

    if blocked:
        assistant.voice_session.set_state(VOICE_STATE_SPEAKING, detail="assistant_output_shield")

    return blocked


def _listen_with_backend_fallback(
    assistant: CoreAssistant,
    *,
    timeout: float,
    debug: bool,
) -> str | None:
    """
    Read one utterance using the first supported method exposed by the
    current voice backend.
    """
    voice_in = assistant.voice_in

    listen_method = getattr(voice_in, "listen", None)
    if callable(listen_method):
        return listen_method(timeout=timeout, debug=debug)

    listen_once_method = getattr(voice_in, "listen_once", None)
    if callable(listen_once_method):
        return listen_once_method(timeout=timeout, debug=debug)

    listen_for_command_method = getattr(voice_in, "listen_for_command", None)
    if callable(listen_for_command_method):
        return listen_for_command_method(timeout=timeout, debug=debug)

    raise AttributeError(
        "Voice input backend does not expose listen(), listen_once(), "
        "or listen_for_command()."
    )


def _build_dedicated_wake_gate(assistant: CoreAssistant):
    voice_cfg = assistant.settings.get("voice_input", {})
    wake_engine = str(voice_cfg.get("wake_engine", "faster_whisper")).strip().lower()

    if wake_engine not in {"openwakeword", "open_wakeword"}:
        return None

    try:
        gate_module = import_module("modules.io.openwakeword_gate")
        gate_class = getattr(gate_module, "OpenWakeWordGate")

        gate = gate_class(
            model_path=str(voice_cfg.get("wake_model_path", "models/wake/nexa.onnx")),
            device_index=voice_cfg.get("device_index"),
            device_name_contains=voice_cfg.get("device_name_contains"),
            threshold=float(voice_cfg.get("wake_threshold", 0.42)),
            trigger_level=int(voice_cfg.get("wake_trigger_level", 2)),
            block_ms=int(voice_cfg.get("wake_block_ms", 80)),
            vad_threshold=float(voice_cfg.get("wake_vad_threshold", 0.25)),
            enable_speex_noise_suppression=bool(
                voice_cfg.get("wake_enable_speex_noise_suppression", False)
            ),
            debug=bool(voice_cfg.get("wake_debug", False)),
        )

        set_audio_coordinator = getattr(gate, "set_audio_coordinator", None)
        if callable(set_audio_coordinator):
            set_audio_coordinator(getattr(assistant, "audio_coordinator", None))

        print("Dedicated wake gate active: openWakeWord")
        append_log("Dedicated wake gate active: openWakeWord")
        return gate

    except Exception as error:
        print("Wake gate fallback active: FasterWhisper.")
        append_log(
            "OpenWakeWord wake gate unavailable. "
            f"Falling back to FasterWhisper. Error: {error}"
        )
        return None


def _listen_for_wake(assistant: CoreAssistant, state_flags: dict[str, bool], wake_gate=None) -> bool:
    if assistant.voice_session.state != VOICE_STATE_STANDBY:
        assistant.voice_session.close_active_window()

    assistant.voice_session.set_state(VOICE_STATE_STANDBY, detail="wake_gate")

    if not state_flags.get("standby_banner_shown", False):
        print("\nStandby. Waiting for wake phrase...")
        state_flags["standby_banner_shown"] = True

    if wake_gate is not None:
        heard_wake = wake_gate.listen_for_wake_phrase(
            timeout=DEDICATED_WAKE_TIMEOUT_SECONDS,
            debug=False,
        )
        if heard_wake is None:
            return False

        state_flags["standby_banner_shown"] = False
        _acknowledge_wake(assistant)
        return True

    wake_method = getattr(assistant.voice_in, "listen_for_wake_phrase", None)

    if callable(wake_method):
        heard_wake = wake_method(
            timeout=WAKE_GATE_TIMEOUT_SECONDS,
            debug=False,
        )
        if heard_wake is None:
            return False

        state_flags["standby_banner_shown"] = False
        _acknowledge_wake(assistant)
        return True

    if not state_flags.get("compatibility_wake_mode_logged", False):
        append_log(
            "Voice input backend does not expose listen_for_wake_phrase(). "
            "Using compatibility wake flow through standard listen method."
        )
        print("Compatibility wake mode active for current voice backend.")
        state_flags["compatibility_wake_mode_logged"] = True

    heard_text = _listen_with_backend_fallback(
        assistant,
        timeout=WAKE_GATE_TIMEOUT_SECONDS,
        debug=False,
    )
    if heard_text is None:
        return False

    heard_text = heard_text.strip()
    if not heard_text:
        return False

    if not assistant.voice_session.heard_wake_phrase(heard_text):
        append_log(f"Ignored transcript while waiting for wake phrase: {heard_text}")
        return False

    state_flags["standby_banner_shown"] = False
    _acknowledge_wake(assistant)
    return True


def _listen_for_active_command(assistant: CoreAssistant) -> str | None:
    assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail="active_window")
    print("\nListening for your request...")

    heard_text = _listen_with_backend_fallback(
        assistant,
        timeout=assistant.voice_listen_timeout,
        debug=assistant.voice_debug,
    )
    if heard_text is None:
        return None

    return heard_text.strip()


def _rearm_active_window(assistant: CoreAssistant) -> None:
    if assistant.pending_confirmation or assistant.pending_follow_up:
        assistant.voice_session.open_active_window(seconds=FOLLOW_UP_WINDOW_SECONDS)
    else:
        assistant.voice_session.open_active_window(seconds=POST_COMMAND_WINDOW_SECONDS)

class WakeInterruptMonitor:
    def __init__(
        self,
        *,
        assistant: CoreAssistant,
        wake_gate,
        timeout_seconds: float = 0.35,
        idle_sleep_seconds: float = 0.05,
    ) -> None:
        self.assistant = assistant
        self.wake_gate = wake_gate
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.idle_sleep_seconds = max(0.02, float(idle_sleep_seconds))
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="wake-interrupt-monitor",
            daemon=True,
        )

    def start(self) -> None:
        if self.wake_gate is None:
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _assistant_interruptible_now(self) -> bool:
        state = self.assistant.voice_session.state
        return state in {VOICE_STATE_SPEAKING, "thinking"}

    def _run(self) -> None:
        if self.wake_gate is None:
            return

        while not self._stop_event.is_set():
            if not self._assistant_interruptible_now():
                time.sleep(self.idle_sleep_seconds)
                continue

            try:
                heard_wake = self.wake_gate.listen_for_wake_phrase(
                    timeout=self.timeout_seconds,
                    debug=False,
                    ignore_audio_block=True,
                )
            except Exception as error:
                append_log(f"Wake interrupt monitor warning: {error}")
                time.sleep(0.15)
                continue

            if heard_wake is None:
                continue

            append_log("Wake barge-in detected during speaking/thinking.")
            self.assistant.request_interrupt(
                reason="wake_barge_in",
                source="wake_interrupt_monitor",
                open_active_window=True,
            )
            time.sleep(0.25)

def main() -> None:
    assistant = CoreAssistant()
    _run_startup_sequence(assistant)
    wake_gate = _build_dedicated_wake_gate(assistant)
    
    wake_interrupt_monitor = WakeInterruptMonitor(
        assistant=assistant,
        wake_gate=wake_gate,
    )
    wake_interrupt_monitor.start()

    gate_log_times: dict[str, float] = {}
    last_transcript_normalized: str | None = None
    last_transcript_time: float | None = None
    state_flags = {
        "standby_banner_shown": False,
        "compatibility_wake_mode_logged": False,
    }

    fatal_error: Exception | None = None

    try:
        while True:
            if _assistant_output_blocks_input(assistant):
                poll_seconds = getattr(
                    getattr(assistant, "audio_coordinator", None),
                    "input_poll_interval_seconds",
                    0.05,
                )
                time.sleep(max(0.01, float(poll_seconds)))
                continue

            if not assistant.voice_session.active_window_open():
                _listen_for_wake(assistant, state_flags, wake_gate=wake_gate)
                continue

            heard_text = _listen_for_active_command(assistant)
            if heard_text is None:
                continue

            if assistant.voice_session.heard_wake_phrase(heard_text):
                assistant.voice_session.extend_active_window(
                    seconds=assistant.voice_session.active_listen_window_seconds,
                )
                print("Wake phrase heard again. Still listening...")
                continue

            if _should_ignore_active_transcript(
                assistant,
                heard_text,
                gate_log_times,
                last_transcript_normalized=last_transcript_normalized,
                last_transcript_time=last_transcript_time,
            ):
                continue

            normalized_command = _normalize_gate_text(heard_text)
            if not normalized_command:
                continue

            print(f"Heard: {heard_text}")
            append_log(f"Accepted transcript in active session: {heard_text}")

            last_transcript_normalized = normalized_command
            last_transcript_time = time.monotonic()

            assistant.voice_session.set_state(VOICE_STATE_ROUTING, detail="dispatching_command")
            should_continue = assistant.handle_command(heard_text)

            if not should_continue:
                assistant.voice_session.set_state(VOICE_STATE_SHUTDOWN, detail="main_loop_exit")
                break

            _rearm_active_window(assistant)

    except KeyboardInterrupt:
        print("\nStopping assistant with keyboard interrupt.")
        append_log("Assistant stopped with keyboard interrupt.")
    except Exception as error:
        fatal_error = error
        append_log(f"Fatal runtime error in main loop: {error}")
        append_log(traceback.format_exc())
        print("\nFatal runtime error in main loop:")
        traceback.print_exc()
    finally:
        shutdown_requested = assistant.shutdown_requested
        try:
            wake_interrupt_monitor.stop()
        except Exception as error:
            append_log(f"Wake interrupt monitor stop warning: {error}")

        if wake_gate is not None:
            try:
                wake_gate.close()
            except Exception as error:
                append_log(f"Wake gate close warning: {error}")

        try:
            assistant.shutdown()
        except Exception as shutdown_error:
            append_log(f"Error during assistant shutdown: {shutdown_error}")
            append_log(traceback.format_exc())
            print("\nError during assistant shutdown:")
            traceback.print_exc()

        if shutdown_requested:
            _perform_system_shutdown(assistant)

        if fatal_error is not None:
            print("Assistant exited after handling a runtime error.")


if __name__ == "__main__":
    main()