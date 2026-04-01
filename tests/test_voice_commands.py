from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python path so direct script execution also works.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.whisper_input import WhisperVoiceInput


def main() -> None:
    WhisperVoiceInput.list_audio_devices()

    voice = WhisperVoiceInput(
    whisper_cli_path="whisper.cpp/build/bin/whisper-cli",
    model_path="models/ggml-base.bin",
    vad_enabled=False,
    vad_model_path="models/ggml-silero-v6.2.0.bin",
    language="auto",
    device_index=None,
    device_name_contains="USB PnP Sound Device",
    sample_rate=None,
    max_record_seconds=8.0,
    silence_threshold=350.0,
    end_silence_seconds=1.0,
    pre_roll_seconds=0.4,
    threads=4,
)

    print()
    print(f"Using input device: {voice.device_name}")
    print(f"Using sample rate: {voice.sample_rate}")
    print("Say something now...")
    print("Examples:")
    print("- pomoc")
    print("- pokaz menu")
    print("- klucze sa w kuchni")
    print("- gdzie sa klucze")
    print("- przypomnij mi za 10 sekund zebym wstal")
    print()

    text = voice.listen_once(timeout=8, debug=True)

    if text:
        print(f"Transcript: {text}")
    else:
        print("No speech recognized.")


if __name__ == "__main__":
    main()