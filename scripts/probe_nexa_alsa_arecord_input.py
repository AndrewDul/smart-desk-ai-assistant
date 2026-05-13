#!/usr/bin/env python3
"""Probe ALSA arecord capture for NeXa real voice runtime."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np

DEFAULT_DEVICE = "plughw:CARD=Array,DEV=0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe ALSA microphone capture via arecord.")
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=2.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    seconds = max(0.2, float(args.seconds))
    sample_rate = max(1, int(args.sample_rate))
    channels = max(1, int(args.channels))

    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / "capture.raw"
        command = [
            "arecord",
            "-q",
            "-D",
            str(args.device),
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-c",
            str(channels),
            "-d",
            str(int(round(seconds))),
            "-t",
            "raw",
            str(raw_path),
        ]
        print("[PROBE]", " ".join(command))
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr.strip())
            return result.returncode or 1

        data = np.fromfile(raw_path, dtype=np.int16)
        if data.size <= 0:
            print("[PROBE FAIL] Capture file is empty.")
            return 2

        peak = int(np.max(np.abs(data)))
        rms = float(np.sqrt(np.mean(np.square(data.astype(np.float64)))))
        print(f"[PROBE OK] samples={data.size} peak={peak} rms={rms:.2f}")
        if peak <= 8:
            print("[PROBE WARN] Audio is almost silent. Check mic gain or input routing.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
