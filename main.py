from __future__ import annotations

import re
import unicodedata

from modules.assistant_logic import CoreAssistant
from modules.utils import append_log


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
    """
    Ignore tiny filler/noise fragments only when the assistant is NOT
    waiting for a follow-up answer like:
    - timer duration
    - focus duration
    - yes/no confirmation
    - display yes/no
    """
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

    # Ignore inputs that contain no letters at all when the assistant
    # is not expecting a short numeric answer.
    if not re.search(r"[a-z]", normalized):
        return True

    return False


def main() -> None:
    assistant = CoreAssistant()
    assistant.boot()

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
        assistant.shutdown()


if __name__ == "__main__":
    main()