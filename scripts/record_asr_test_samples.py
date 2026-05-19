"""
Record short WAV samples from the same microphone NeXa uses.
Saves under var/data/asr_test_samples/ for use with asr_benchmark.py.

Usage:
    .venv/bin/python scripts/record_asr_test_samples.py [--device-index N] [--list-devices]
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "var" / "data" / "asr_test_samples"
SAMPLE_RATE = 16000
CHANNELS = 1
RECORD_SECONDS = 3.5  # long enough to say the phrase clearly

TEST_PHRASES = [
    {"text": "what is teleportation", "language": "en"},
    {"text": "what is the speed of light", "language": "en"},
    {"text": "what are colors", "language": "en"},
    {"text": "how big is the USA", "language": "en"},
    {"text": "explain gravity", "language": "en"},
    {"text": "co to jest teleportacja", "language": "pl"},
    {"text": "czym jest teleportacja", "language": "pl"},
    {"text": "jaka jest prędkość światła", "language": "pl"},
    {"text": "jak szybkie jest światło", "language": "pl"},
    {"text": "co to są kolory", "language": "pl"},
    {"text": "jak duże jest USA", "language": "pl"},
    {"text": "wyjaśnij grawitację", "language": "pl"},
]


def _load_settings() -> dict:
    settings_path = ROOT / "config" / "settings.json"
    try:
        with open(settings_path) as f:
            return json.load(f)
    except Exception:
        return {}


def _select_device(settings: dict, device_index_override: int | None) -> tuple[int | None, str]:
    if device_index_override is not None:
        return device_index_override, f"explicit override device_index={device_index_override}"

    vi = settings.get("voice_input", {})
    name_contains = vi.get("device_name_contains", "")
    fallback_index = vi.get("device_index", None)

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        if name_contains:
            name_lower = name_contains.lower()
            for i, dev in enumerate(devices):
                if name_lower in str(dev.get("name", "")).lower():
                    if dev.get("max_input_channels", 0) > 0:
                        return i, f"matched device_name_contains='{name_contains}'"

        if fallback_index is not None:
            idx = int(fallback_index)
            if 0 <= idx < len(devices) and devices[idx].get("max_input_channels", 0) > 0:
                return idx, f"fallback to settings device_index={idx}"

        default = sd.default.device[0]
        return default, "using system default input device"
    except Exception as err:
        print(f"[record_asr] sounddevice error: {err}")
        return None, "unknown (sounddevice unavailable)"


def _list_devices() -> None:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        print("Available audio devices:")
        for i, dev in enumerate(devices):
            tag = " [INPUT]" if dev.get("max_input_channels", 0) > 0 else ""
            print(f"  {i:3d}: {dev['name']}{tag}")
    except ImportError:
        print("sounddevice not installed")


def _record_wav(path: Path, *, device: int | None, seconds: float) -> bool:
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        print("sounddevice / numpy not installed — cannot record")
        return False

    frames: list[bytes] = []

    def _callback(indata: "np.ndarray", frame_count: int, time_info: object, status: object) -> None:
        frames.append(bytes(indata))

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        device=device,
        callback=_callback,
    ):
        time.sleep(seconds)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Record ASR test samples for NeXa benchmarking")
    parser.add_argument("--device-index", type=int, default=None, help="Override mic device index")
    parser.add_argument("--list-devices", action="store_true", help="List available audio devices")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR), help="Output directory")
    args = parser.parse_args()

    if args.list_devices:
        _list_devices()
        return

    output_dir = Path(args.output_dir)
    settings = _load_settings()
    device_index, device_reason = _select_device(settings, args.device_index)

    print(f"[record_asr] Selected mic: device_index={device_index!r} reason={device_reason!r}")
    print(f"[record_asr] Output dir: {output_dir}")
    print(f"[record_asr] sample_rate={SAMPLE_RATE} channels={CHANNELS} record_seconds={RECORD_SECONDS}")
    print()

    index_data = []
    for entry in TEST_PHRASES:
        phrase = entry["text"]
        language = entry["language"]
        safe_name = phrase.replace(" ", "_").replace("/", "_")[:60]
        filename = f"{language}_{safe_name}.wav"
        path = output_dir / filename

        print(f"  [{language}] SAY: \"{phrase}\"")
        print(f"         Press ENTER to start recording ({RECORD_SECONDS:.1f}s)...", end="")
        input()
        print(f"         Recording... ", end="", flush=True)
        ok = _record_wav(path, device=device_index, seconds=RECORD_SECONDS)
        if ok:
            print(f"saved: {path.name}")
            index_data.append({
                "file": filename,
                "expected_text": phrase,
                "language": language,
                "device_index": device_index,
                "device_reason": device_reason,
                "sample_rate": SAMPLE_RATE,
                "channels": CHANNELS,
            })
        else:
            print("FAILED")

    index_path = output_dir / "index.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)
    print(f"\n[record_asr] Wrote index: {index_path} ({len(index_data)} samples)")


if __name__ == "__main__":
    main()
