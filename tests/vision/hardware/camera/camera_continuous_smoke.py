# tests/vision/hardware/camera/camera_continuous_smoke.py
"""
Hardware smoke test — Continuous Capture Worker on a real camera.

Run manually on Pi:
    python tests/vision/hardware/camera/camera_continuous_smoke.py

Expected output:
    - Worker starts without error
    - First frame arrives within 3 seconds
    - FPS measured over 3 seconds is within acceptable range
    - Worker stops cleanly
"""
from __future__ import annotations

import sys
import time

from modules.devices.vision.capture.continuous_worker import ContinuousCaptureWorker
from modules.devices.vision.capture.reader import VisionCaptureReader
from modules.devices.vision.config import VisionRuntimeConfig

TARGET_FPS = 10.0
WARMUP_SECONDS = 2.0
MEASURE_SECONDS = 3.0
MIN_ACCEPTABLE_FPS = 4.0
FIRST_FRAME_TIMEOUT = 5.0


def _sep(char: str = "-", width: int = 60) -> None:
    print(char * width)


def main() -> int:
    _sep("=")
    print("NeXa Vision — Continuous Capture Smoke Test")
    _sep("=")

    config = VisionRuntimeConfig.from_mapping({
        "enabled": True,
        "continuous_capture_enabled": True,
        "continuous_capture_target_fps": TARGET_FPS,
        "lazy_start": True,
    })

    print(f"[config] backend={config.backend} fallback={config.fallback_backend}")
    print(f"[config] target_fps={config.continuous_capture_target_fps}")
    print(f"[config] resolution={config.frame_width}x{config.frame_height}")
    _sep()

    reader = VisionCaptureReader(config=config)
    worker = ContinuousCaptureWorker(reader, target_fps=TARGET_FPS)

    print("[1] Starting worker...")
    worker.start()

    # --- Wait for first frame ---
    print(f"[2] Waiting for first frame (timeout={FIRST_FRAME_TIMEOUT}s)...")
    deadline = time.monotonic() + FIRST_FRAME_TIMEOUT
    first_frame = None
    while time.monotonic() < deadline:
        first_frame = worker.latest_frame()
        if first_frame is not None:
            break
        time.sleep(0.05)

    if first_frame is None:
        print("[FAIL] No frame received within timeout.")
        worker.stop()
        return 1

    elapsed_to_first = time.monotonic() - (deadline - FIRST_FRAME_TIMEOUT)
    print(f"[OK] First frame received in ~{elapsed_to_first:.2f}s")
    print(f"     backend={first_frame.backend_label} size={first_frame.width}x{first_frame.height}")

    # --- Warmup ---
    print(f"[3] Warming up for {WARMUP_SECONDS}s...")
    time.sleep(WARMUP_SECONDS)

    # --- Measure FPS ---
    print(f"[4] Measuring FPS over {MEASURE_SECONDS}s...")
    stats_before = worker.stats()
    frames_before = stats_before["frames_captured"]
    t0 = time.monotonic()

    time.sleep(MEASURE_SECONDS)

    stats_after = worker.stats()
    frames_after = stats_after["frames_captured"]
    elapsed = time.monotonic() - t0

    frames_in_window = frames_after - frames_before
    measured_fps = frames_in_window / elapsed if elapsed > 0 else 0.0

    _sep()
    print(f"[result] frames in window : {frames_in_window}")
    print(f"[result] elapsed          : {elapsed:.2f}s")
    print(f"[result] measured FPS     : {measured_fps:.2f}")
    print(f"[result] target FPS       : {TARGET_FPS:.2f}")
    print(f"[result] total captured   : {stats_after['frames_captured']}")
    print(f"[result] total dropped    : {stats_after['frames_dropped']}")
    print(f"[result] consecutive err  : {stats_after['consecutive_errors']}")
    print(f"[result] last error       : {stats_after['last_error']}")

    fps_ok = measured_fps >= MIN_ACCEPTABLE_FPS
    _sep()

    if fps_ok:
        print(f"[PASS] FPS {measured_fps:.2f} >= minimum {MIN_ACCEPTABLE_FPS:.2f}")
    else:
        print(f"[FAIL] FPS {measured_fps:.2f} < minimum {MIN_ACCEPTABLE_FPS:.2f}")

    # --- Stop ---
    print("[5] Stopping worker...")
    worker.stop()
    print(f"[OK] Worker stopped. is_running={worker.is_running}")
    _sep("=")

    return 0 if fps_ok else 1


if __name__ == "__main__":
    sys.exit(main())