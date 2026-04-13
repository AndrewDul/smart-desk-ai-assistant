from __future__ import annotations

import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.devices.pan_tilt import PanTiltService
from modules.shared.config.settings import load_settings


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def ease_linear(progress: float) -> float:
    return clamp(progress, 0.0, 1.0)


def ease_in_out_sine(progress: float) -> float:
    progress = clamp(progress, 0.0, 1.0)
    return -(math.cos(math.pi * progress) - 1.0) / 2.0


def ease_in_out_cubic(progress: float) -> float:
    progress = clamp(progress, 0.0, 1.0)
    if progress < 0.5:
        return 4.0 * progress * progress * progress
    return 1.0 - pow(-2.0 * progress + 2.0, 3.0) / 2.0


def animate_pose(
    service: PanTiltService,
    *,
    target_pan: float,
    target_tilt: float,
    duration_seconds: float,
    fps: int = 50,
    easing=ease_in_out_sine,
    label: str = "",
    hold_seconds: float = 0.0,
    safe_tilt_min: float | None = None,
    safe_tilt_max: float | None = None,
) -> None:
    start_pan = float(service._angles["pan"])
    start_tilt = float(service._angles["tilt"])

    pan_min = float(service._pan.min_angle)
    pan_max = float(service._pan.max_angle)
    tilt_min = float(service._tilt.min_angle)
    tilt_max = float(service._tilt.max_angle)

    if safe_tilt_min is not None:
        tilt_min = max(tilt_min, float(safe_tilt_min))
    if safe_tilt_max is not None:
        tilt_max = min(tilt_max, float(safe_tilt_max))

    target_pan = clamp(target_pan, pan_min, pan_max)
    target_tilt = clamp(target_tilt, tilt_min, tilt_max)

    steps = max(2, int(max(1.0, duration_seconds) * max(20, fps)))
    sleep_per_step = max(0.0, float(duration_seconds) / steps)

    for step_index in range(1, steps + 1):
        raw_progress = step_index / steps
        eased_progress = easing(raw_progress)

        next_pan = start_pan + ((target_pan - start_pan) * eased_progress)
        next_tilt = start_tilt + ((target_tilt - start_tilt) * eased_progress)

        service._set_axis_angle("pan", next_pan)
        service._set_axis_angle("tilt", next_tilt)

        if sleep_per_step > 0.0:
            time.sleep(sleep_per_step)

    print(f"[PAN_TILT TEST] {label} -> {service.status()}")

    if hold_seconds > 0.0:
        time.sleep(hold_seconds)


def run_direction_showcase(service: PanTiltService) -> None:
    pan_min = float(service._pan.min_angle)
    pan_center = float(service._pan.center_angle)
    pan_max = float(service._pan.max_angle)

    tilt_min = float(service._tilt.min_angle)
    tilt_center = float(service._tilt.center_angle)
    tilt_max = float(service._tilt.max_angle)

    print("[PAN_TILT TEST] Direction showcase: left, right, up, down")

    animate_pose(
        service,
        target_pan=pan_min,
        target_tilt=tilt_center,
        duration_seconds=1.2,
        fps=45,
        easing=ease_in_out_sine,
        label="LEFT",
        hold_seconds=0.35,
    )
    animate_pose(
        service,
        target_pan=pan_max,
        target_tilt=tilt_center,
        duration_seconds=1.5,
        fps=45,
        easing=ease_in_out_sine,
        label="RIGHT",
        hold_seconds=0.35,
    )
    animate_pose(
        service,
        target_pan=pan_center,
        target_tilt=tilt_min,
        duration_seconds=1.2,
        fps=45,
        easing=ease_in_out_sine,
        label="UP",
        hold_seconds=0.35,
    )
    animate_pose(
        service,
        target_pan=pan_center,
        target_tilt=tilt_max,
        duration_seconds=1.2,
        fps=45,
        easing=ease_in_out_sine,
        label="DOWN",
        hold_seconds=0.35,
    )
    animate_pose(
        service,
        target_pan=pan_center,
        target_tilt=tilt_center,
        duration_seconds=1.0,
        fps=45,
        easing=ease_in_out_sine,
        label="CENTER",
        hold_seconds=0.25,
    )


def run_diagonal_sweep(service: PanTiltService) -> None:
    pan_min = float(service._pan.min_angle)
    pan_center = float(service._pan.center_angle)
    pan_max = float(service._pan.max_angle)

    tilt_min = float(service._tilt.min_angle)
    tilt_center = float(service._tilt.center_angle)
    tilt_max = float(service._tilt.max_angle)

    print("[PAN_TILT TEST] Diagonal sweep: upper-right -> lower-left")

    animate_pose(
        service,
        target_pan=pan_max,
        target_tilt=tilt_min,
        duration_seconds=1.7,
        fps=50,
        easing=ease_in_out_cubic,
        label="UPPER-RIGHT",
        hold_seconds=0.30,
    )
    animate_pose(
        service,
        target_pan=pan_min,
        target_tilt=tilt_max,
        duration_seconds=2.0,
        fps=50,
        easing=ease_in_out_cubic,
        label="LOWER-LEFT",
        hold_seconds=0.40,
    )
    animate_pose(
        service,
        target_pan=pan_center,
        target_tilt=tilt_center,
        duration_seconds=1.4,
        fps=50,
        easing=ease_in_out_sine,
        label="CENTER AFTER DIAGONAL",
        hold_seconds=0.25,
    )


def run_circle_demo(service: PanTiltService) -> None:
    pan_min = float(service._pan.min_angle)
    pan_center = float(service._pan.center_angle)
    pan_max = float(service._pan.max_angle)

    tilt_min = float(service._tilt.min_angle)
    tilt_center = float(service._tilt.center_angle)
    tilt_max = float(service._tilt.max_angle)

    pan_radius = max(8.0, min(pan_center - pan_min, pan_max - pan_center) * 0.78)
    tilt_radius = max(6.0, min(tilt_center - tilt_min, tilt_max - tilt_center) * 0.65)

    print("[PAN_TILT TEST] Circular motion demo starting...")

    total_points = 80
    total_duration = 4.5
    sleep_per_step = total_duration / total_points

    for point_index in range(total_points + 1):
        angle = (2.0 * math.pi * point_index) / total_points

        target_pan = pan_center + (math.cos(angle) * pan_radius)
        target_tilt = tilt_center - (math.sin(angle) * tilt_radius)

        target_pan = clamp(target_pan, pan_min, pan_max)
        target_tilt = clamp(target_tilt, tilt_min, tilt_max)

        service._set_axis_angle("pan", target_pan)
        service._set_axis_angle("tilt", target_tilt)
        time.sleep(sleep_per_step)

    print(f"[PAN_TILT TEST] Circle complete -> {service.status()}")


def run_velocity_demo(service: PanTiltService) -> None:
    pan_min = float(service._pan.min_angle)
    pan_center = float(service._pan.center_angle)
    pan_max = float(service._pan.max_angle)

    tilt_center = float(service._tilt.center_angle)
    tilt_min = float(service._tilt.min_angle)
    tilt_max = float(service._tilt.max_angle)

    safe_fast_down = min(tilt_max, tilt_center + 10.0)
    safe_medium_down = min(tilt_max, tilt_center + 14.0)
    safe_slow_down = min(tilt_max, tilt_center + 18.0)
    safe_up = max(tilt_min, tilt_center - 18.0)

    print("[PAN_TILT TEST] Smooth velocity demo: slow, medium, fast")

    animate_pose(
        service,
        target_pan=pan_min + 12.0,
        target_tilt=safe_up,
        duration_seconds=2.8,
        fps=60,
        easing=ease_in_out_sine,
        label="SLOW UPPER-LEFT DRIFT",
        hold_seconds=0.30,
    )

    animate_pose(
        service,
        target_pan=pan_max - 12.0,
        target_tilt=safe_slow_down,
        duration_seconds=2.6,
        fps=60,
        easing=ease_in_out_sine,
        label="SLOW LOWER-RIGHT DRIFT",
        hold_seconds=0.30,
        safe_tilt_max=safe_slow_down,
    )

    animate_pose(
        service,
        target_pan=pan_center,
        target_tilt=tilt_center,
        duration_seconds=1.5,
        fps=55,
        easing=ease_in_out_cubic,
        label="MEDIUM RETURN TO CENTER",
        hold_seconds=0.20,
    )

    animate_pose(
        service,
        target_pan=pan_max - 8.0,
        target_tilt=safe_medium_down,
        duration_seconds=1.0,
        fps=70,
        easing=ease_in_out_cubic,
        label="MEDIUM RIGHT SWEEP",
        hold_seconds=0.15,
        safe_tilt_max=safe_medium_down,
    )

    animate_pose(
        service,
        target_pan=pan_min + 8.0,
        target_tilt=safe_up + 4.0,
        duration_seconds=0.95,
        fps=70,
        easing=ease_in_out_cubic,
        label="MEDIUM LEFT SWEEP",
        hold_seconds=0.15,
    )

    animate_pose(
        service,
        target_pan=pan_center + 28.0,
        target_tilt=safe_fast_down,
        duration_seconds=0.55,
        fps=85,
        easing=ease_linear,
        label="FAST RIGHT SNAP",
        hold_seconds=0.10,
        safe_tilt_max=safe_fast_down,
    )

    animate_pose(
        service,
        target_pan=pan_center - 28.0,
        target_tilt=safe_up + 6.0,
        duration_seconds=0.55,
        fps=85,
        easing=ease_linear,
        label="FAST LEFT SNAP",
        hold_seconds=0.10,
    )

    animate_pose(
        service,
        target_pan=pan_center,
        target_tilt=tilt_center,
        duration_seconds=0.85,
        fps=70,
        easing=ease_in_out_sine,
        label="FAST RECENTER",
        hold_seconds=0.20,
    )


def run_wave_demo(service: PanTiltService) -> None:
    pan_center = float(service._pan.center_angle)
    tilt_center = float(service._tilt.center_angle)

    pan_min = float(service._pan.min_angle)
    pan_max = float(service._pan.max_angle)
    tilt_min = float(service._tilt.min_angle)
    tilt_max = float(service._tilt.max_angle)

    pan_radius = max(10.0, min(pan_center - pan_min, pan_max - pan_center) * 0.72)
    tilt_radius = max(5.0, min(tilt_center - tilt_min, tilt_max - tilt_center) * 0.28)

    safe_fast_down = min(tilt_max, tilt_center + 10.0)

    print("[PAN_TILT TEST] Natural wave demo starting...")

    total_points = 90
    total_duration = 4.2
    sleep_per_step = total_duration / total_points

    for point_index in range(total_points + 1):
        progress = point_index / total_points
        phase = progress * (2.0 * math.pi)

        target_pan = pan_center + (math.sin(phase) * pan_radius)
        target_tilt = tilt_center + (math.sin(phase * 2.0) * tilt_radius)

        target_pan = clamp(target_pan, pan_min, pan_max)
        target_tilt = clamp(target_tilt, tilt_min, safe_fast_down)

        service._set_axis_angle("pan", target_pan)
        service._set_axis_angle("tilt", target_tilt)
        time.sleep(sleep_per_step)

    print(f"[PAN_TILT TEST] Natural wave complete -> {service.status()}")


def main() -> None:
    settings = load_settings()
    config = settings.get("pan_tilt", {})

    print("[PAN_TILT TEST] Building PanTiltService...")
    service = PanTiltService(config=config)

    try:
        print(f"[PAN_TILT TEST] Initial status: {service.status()}")

        animate_pose(
            service,
            target_pan=float(service._pan.center_angle),
            target_tilt=float(service._tilt.center_angle),
            duration_seconds=1.0,
            fps=45,
            easing=ease_in_out_sine,
            label="INITIAL CENTER",
            hold_seconds=0.35,
        )

        run_direction_showcase(service)
        run_diagonal_sweep(service)
        run_circle_demo(service)
        run_velocity_demo(service)
        run_wave_demo(service)

        print("[PAN_TILT TEST] Returning to center...")
        animate_pose(
            service,
            target_pan=float(service._pan.center_angle),
            target_tilt=float(service._tilt.center_angle),
            duration_seconds=1.2,
            fps=50,
            easing=ease_in_out_sine,
            label="FINAL CENTER",
            hold_seconds=0.30,
        )
    finally:
        service.close()
        print("[PAN_TILT TEST] Closed.")


if __name__ == "__main__":
    main()