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
    lowered = re.sub(r"[^a-z0-9\s\[\]_-]", " ", lowered)
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
    }

    return normalized in blank_markers


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
    }

    if normalized in filler_words:
        return True

    if not re.search(r"[a-z]", normalized):
        return True

    return False


def _run_startup_sequence(assistant: CoreAssistant) -> None:
    append_log("Startup sequence initiated.")

    assistant.display.show_block(
        "DevDul",
        [
            "Smart Assistant",
            "starting up...",
        ],
        duration=assistant.boot_overlay_seconds,
    )

    checker = SystemHealthChecker(assistant.settings)
    report = checker.run()

    assistant.state["assistant_running"] = True
    assistant._save_state()

    if not assistant._reminder_thread.is_alive():
        assistant._reminder_thread.start()

    time.sleep(max(assistant.boot_overlay_seconds, 0.8))
    assistant.display.clear_overlay()

    time.sleep(0.2)

    if report.ok:
        assistant.voice_out.speak(
            "Hello. I am ready. You can speak in Polish or in English.",
            language="en",
        )
        append_log("Startup completed successfully.")
        return

    assistant.voice_out.speak(
        "Hello. I started, but some system checks reported problems. I may work in limited mode.",
        language="en",
    )
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

    try:
        while True:
            print("\nListening for speech...")
            heard_text = assistant.voice_in.listen(
                timeout=assistant.voice_listen_timeout,
                debug=assistant.voice_debug,
            )

            if heard_text is None:
                append_log("Ignored silent input: recognizer returned None.")
                print("No speech recognized.")
                continue

            heard_text = heard_text.strip()

            if _is_blank_or_silence(heard_text):
                append_log(f"Ignored blank audio marker: {heard_text}")
                print("Ignored blank audio marker.")
                continue

            if not _normalize_gate_text(heard_text):
                append_log("Ignored empty normalized transcript.")
                print("Ignored empty normalized transcript.")
                continue

            if _is_low_value_noise(heard_text, assistant):
                append_log(f"Ignored low-value noise: {heard_text}")
                print(f"Ignored low-value noise: {heard_text}")
                continue

            print(f"Heard: {heard_text}")

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