from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.devices.pan_tilt import PanTiltService
from modules.shared.config.settings import load_settings


class BehaviorDisplayBridge:
    """
    Best-effort display hook.

    This test keeps LCD output optional and non-blocking.
    Right now it silently does nothing on the LCD and only prints to terminal.
    """

    def show(self, text: str) -> None:
        del text

    def clear(self) -> None:
        return


@dataclass(slots=True)
class ViewGeometry:
    horizontal_min: float
    horizontal_center: float
    horizontal_max: float
    vertical_min: float
    vertical_center: float
    vertical_max: float

    horizontal_left: float
    horizontal_right: float
    vertical_up: float
    vertical_down_safe: float
    vertical_down_deep: float


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def lerp(start: float, end: float, progress: float) -> float:
    return start + ((end - start) * progress)


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


def ease_out_quint(progress: float) -> float:
    progress = clamp(progress, 0.0, 1.0)
    return 1.0 - pow(1.0 - progress, 5.0)


def build_view_geometry(service: PanTiltService) -> ViewGeometry:
    """
    IMPORTANT:
    On the user's current physical assembly:
    - horizontal movement is driven by the tilt servo
    - vertical movement is driven by the pan servo
    """

    horizontal_min = float(service._tilt.min_angle)
    horizontal_center = float(service._tilt.center_angle)
    horizontal_max = float(service._tilt.max_angle)

    vertical_min = float(service._pan.min_angle)
    vertical_center = float(service._pan.center_angle)
    vertical_max = float(service._pan.max_angle)

    left_span = horizontal_center - horizontal_min
    right_span = horizontal_max - horizontal_center
    up_span = vertical_center - vertical_min
    down_span = vertical_max - vertical_center

    horizontal_left = clamp(horizontal_center - (left_span * 0.88), horizontal_min, horizontal_max)
    horizontal_right = clamp(horizontal_center + (right_span * 0.88), horizontal_min, horizontal_max)

    vertical_up = clamp(vertical_center - (up_span * 0.82), vertical_min, vertical_max)

    # Screen-safe vertical limits.
    vertical_down_safe = clamp(vertical_center + min(10.0, down_span * 0.45), vertical_min, vertical_max)
    vertical_down_deep = clamp(vertical_center + min(14.0, down_span * 0.62), vertical_min, vertical_max)

    return ViewGeometry(
        horizontal_min=horizontal_min,
        horizontal_center=horizontal_center,
        horizontal_max=horizontal_max,
        vertical_min=vertical_min,
        vertical_center=vertical_center,
        vertical_max=vertical_max,
        horizontal_left=horizontal_left,
        horizontal_right=horizontal_right,
        vertical_up=vertical_up,
        vertical_down_safe=vertical_down_safe,
        vertical_down_deep=vertical_down_deep,
    )


def set_view_pose(
    service: PanTiltService,
    *,
    horizontal: float,
    vertical: float,
    geometry: ViewGeometry,
) -> None:
    """
    Maps user-facing view coordinates to the raw servo axes.

    horizontal -> raw tilt
    vertical   -> raw pan
    """
    raw_tilt = clamp(horizontal, geometry.horizontal_min, geometry.horizontal_max)
    raw_pan = clamp(vertical, geometry.vertical_min, geometry.vertical_max)

    service._set_axis_angle("pan", raw_pan)
    service._set_axis_angle("tilt", raw_tilt)


def animate_view_pose(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    target_horizontal: float,
    target_vertical: float,
    duration_seconds: float,
    fps: int = 60,
    easing=ease_in_out_sine,
    label: str = "",
    hold_seconds: float = 0.0,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    start_horizontal = float(service._angles["tilt"])
    start_vertical = float(service._angles["pan"])

    target_horizontal = clamp(
        target_horizontal,
        geometry.horizontal_min,
        geometry.horizontal_max,
    )
    target_vertical = clamp(
        target_vertical,
        geometry.vertical_min,
        geometry.vertical_max,
    )

    steps = max(2, int(max(0.2, float(duration_seconds)) * max(20, int(fps))))
    sleep_per_step = max(0.0, float(duration_seconds) / steps)

    if label:
        print(f"[PAN_TILT BEHAVIOR] {label}")
        if display is not None:
            display.show(label)

    for step_index in range(1, steps + 1):
        raw_progress = step_index / steps
        eased_progress = easing(raw_progress)

        current_horizontal = lerp(start_horizontal, target_horizontal, eased_progress)
        current_vertical = lerp(start_vertical, target_vertical, eased_progress)

        set_view_pose(
            service,
            horizontal=current_horizontal,
            vertical=current_vertical,
            geometry=geometry,
        )

        if sleep_per_step > 0.0:
            time.sleep(sleep_per_step)

    print(f"[PAN_TILT BEHAVIOR] pose -> {service.status()}")

    if hold_seconds > 0.0:
        time.sleep(hold_seconds)


def animate_path(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    points: list[tuple[float, float]],
    duration_seconds: float,
    fps: int = 70,
    easing=ease_in_out_sine,
    label: str = "",
    hold_seconds: float = 0.0,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    if not points:
        return

    start_horizontal = float(service._angles["tilt"])
    start_vertical = float(service._angles["pan"])

    path = [(start_horizontal, start_vertical)] + [
        (
            clamp(h, geometry.horizontal_min, geometry.horizontal_max),
            clamp(v, geometry.vertical_min, geometry.vertical_max),
        )
        for h, v in points
    ]

    segment_count = len(path) - 1
    if segment_count <= 0:
        return

    if label:
        print(f"[PAN_TILT BEHAVIOR] {label}")
        if display is not None:
            display.show(label)

    segment_duration = float(duration_seconds) / segment_count

    for segment_index in range(segment_count):
        from_horizontal, from_vertical = path[segment_index]
        to_horizontal, to_vertical = path[segment_index + 1]

        steps = max(2, int(max(0.12, segment_duration) * max(20, int(fps))))
        sleep_per_step = max(0.0, segment_duration / steps)

        for step_index in range(1, steps + 1):
            raw_progress = step_index / steps
            eased_progress = easing(raw_progress)

            current_horizontal = lerp(from_horizontal, to_horizontal, eased_progress)
            current_vertical = lerp(from_vertical, to_vertical, eased_progress)

            set_view_pose(
                service,
                horizontal=current_horizontal,
                vertical=current_vertical,
                geometry=geometry,
            )

            if sleep_per_step > 0.0:
                time.sleep(sleep_per_step)

    print(f"[PAN_TILT BEHAVIOR] path -> {service.status()}")

    if hold_seconds > 0.0:
        time.sleep(hold_seconds)


def center_pose(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    duration_seconds: float = 1.0,
    label: str = "CENTER",
    display: BehaviorDisplayBridge | None = None,
) -> None:
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center,
        target_vertical=geometry.vertical_center,
        duration_seconds=duration_seconds,
        fps=65,
        easing=ease_in_out_sine,
        label=label,
        hold_seconds=0.20,
        display=display,
    )


def run_speed_profiles(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] SPEED PROFILE DEMO")

    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_left,
        target_vertical=geometry.vertical_center,
        duration_seconds=3.2,
        fps=90,
        easing=ease_in_out_sine,
        label="ULTRA SMOOTH SLOW LEFT",
        hold_seconds=0.35,
        display=display,
    )
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_right,
        target_vertical=geometry.vertical_center,
        duration_seconds=2.5,
        fps=85,
        easing=ease_in_out_sine,
        label="SMOOTH MEDIUM RIGHT",
        hold_seconds=0.30,
        display=display,
    )
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center,
        target_vertical=geometry.vertical_center,
        duration_seconds=1.2,
        fps=75,
        easing=ease_in_out_cubic,
        label="NATURAL RECENTER",
        hold_seconds=0.20,
        display=display,
    )
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_right - 8.0,
        target_vertical=geometry.vertical_up + 4.0,
        duration_seconds=0.65,
        fps=95,
        easing=ease_out_quint,
        label="FAST PRECISE SNAP",
        hold_seconds=0.15,
        display=display,
    )
    center_pose(
        service,
        geometry,
        duration_seconds=0.95,
        label="CENTER AFTER SPEED PROFILES",
        display=display,
    )


def run_ultra_smooth_showcase(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] ULTRA SMOOTH SHOWCASE")

    total_points = 180
    total_duration = 7.2
    sleep_per_step = total_duration / total_points

    if display is not None:
        display.show("ULTRA SMOOTH GLIDE")

    for point_index in range(total_points + 1):
        progress = point_index / total_points

        horizontal = lerp(
            geometry.horizontal_left + 4.0,
            geometry.horizontal_right - 4.0,
            ease_in_out_sine(progress),
        )
        vertical = geometry.vertical_center + (math.sin(progress * math.pi) * 4.0)

        set_view_pose(
            service,
            horizontal=horizontal,
            vertical=vertical,
            geometry=geometry,
        )
        time.sleep(sleep_per_step)

    print(f"[PAN_TILT BEHAVIOR] ULTRA SMOOTH GLIDE -> {service.status()}")
    time.sleep(0.30)

    center_pose(
        service,
        geometry,
        duration_seconds=1.1,
        label="CENTER AFTER ULTRA SMOOTH",
        display=display,
    )


def behavior_laugh(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] LAUGH")

    if display is not None:
        display.show("LAUGH")

    base_h = geometry.horizontal_center
    base_v = geometry.vertical_center - 2.0

    amplitudes = [8.0, 7.0, 6.0, 4.5]
    side_offsets = [5.0, -5.0, 4.0, -3.0]

    animate_view_pose(
        service,
        geometry,
        target_horizontal=base_h,
        target_vertical=base_v,
        duration_seconds=0.45,
        fps=70,
        easing=ease_in_out_sine,
        label="LAUGH READY",
        hold_seconds=0.05,
        display=display,
    )

    for amplitude, side in zip(amplitudes, side_offsets):
        animate_view_pose(
            service,
            geometry,
            target_horizontal=base_h + side,
            target_vertical=base_v - amplitude,
            duration_seconds=0.16,
            fps=90,
            easing=ease_out_quint,
            label="LAUGH POP",
            hold_seconds=0.02,
            display=display,
        )
        animate_view_pose(
            service,
            geometry,
            target_horizontal=base_h - (side * 0.35),
            target_vertical=base_v + (amplitude * 0.30),
            duration_seconds=0.25,
            fps=95,
            easing=ease_in_out_sine,
            label="LAUGH SETTLE",
            hold_seconds=0.03,
            display=display,
        )

    center_pose(
        service,
        geometry,
        duration_seconds=0.95,
        label="CENTER AFTER LAUGH",
        display=display,
    )


def behavior_disagree(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] DISAGREE")

    if display is not None:
        display.show("DISAGREE")

    base_v = geometry.vertical_center
    amplitudes = [22.0, 18.0, 14.0, 10.0]

    for amplitude in amplitudes:
        animate_view_pose(
            service,
            geometry,
            target_horizontal=geometry.horizontal_center - amplitude,
            target_vertical=base_v,
            duration_seconds=0.17,
            fps=90,
            easing=ease_linear,
            label="DISAGREE LEFT",
            hold_seconds=0.01,
            display=display,
        )
        animate_view_pose(
            service,
            geometry,
            target_horizontal=geometry.horizontal_center + amplitude,
            target_vertical=base_v,
            duration_seconds=0.18,
            fps=90,
            easing=ease_linear,
            label="DISAGREE RIGHT",
            hold_seconds=0.01,
            display=display,
        )

    center_pose(
        service,
        geometry,
        duration_seconds=0.75,
        label="CENTER AFTER DISAGREE",
        display=display,
    )


def behavior_anger(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] ANGER")

    if display is not None:
        display.show("ANGER")

    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center,
        target_vertical=geometry.vertical_down_safe,
        duration_seconds=0.28,
        fps=95,
        easing=ease_out_quint,
        label="ANGER DROP",
        hold_seconds=0.04,
        display=display,
    )

    animate_path(
        service,
        geometry,
        points=[
            (geometry.horizontal_center + 22.0, geometry.vertical_down_safe),
            (geometry.horizontal_center - 22.0, geometry.vertical_down_safe),
            (geometry.horizontal_center + 14.0, geometry.vertical_down_safe - 2.0),
            (geometry.horizontal_center, geometry.vertical_down_safe - 3.0),
        ],
        duration_seconds=0.95,
        fps=95,
        easing=ease_linear,
        label="ANGER JABS",
        hold_seconds=0.08,
        display=display,
    )

    center_pose(
        service,
        geometry,
        duration_seconds=1.05,
        label="CENTER AFTER ANGER",
        display=display,
    )


def behavior_happiness(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] HAPPINESS")

    if display is not None:
        display.show("HAPPINESS")

    animate_path(
        service,
        geometry,
        points=[
            (geometry.horizontal_center - 18.0, geometry.vertical_up + 5.0),
            (geometry.horizontal_center + 18.0, geometry.vertical_up + 2.0),
            (geometry.horizontal_center - 10.0, geometry.vertical_up + 3.0),
            (geometry.horizontal_center + 10.0, geometry.vertical_up + 4.0),
            (geometry.horizontal_center, geometry.vertical_center - 3.0),
        ],
        duration_seconds=2.0,
        fps=85,
        easing=ease_in_out_sine,
        label="HAPPY BOUNCE",
        hold_seconds=0.10,
        display=display,
    )

    center_pose(
        service,
        geometry,
        duration_seconds=0.95,
        label="CENTER AFTER HAPPINESS",
        display=display,
    )


def behavior_curiosity(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] CURIOSITY")

    if display is not None:
        display.show("CURIOSITY")

    animate_path(
        service,
        geometry,
        points=[
            (geometry.horizontal_center + 12.0, geometry.vertical_center - 2.0),
            (geometry.horizontal_center + 22.0, geometry.vertical_up + 4.0),
            (geometry.horizontal_center + 8.0, geometry.vertical_center + 2.0),
            (geometry.horizontal_center - 16.0, geometry.vertical_center - 1.0),
            (geometry.horizontal_center - 24.0, geometry.vertical_up + 3.0),
            (geometry.horizontal_center, geometry.vertical_center),
        ],
        duration_seconds=3.1,
        fps=80,
        easing=ease_in_out_sine,
        label="CURIOUS SEARCH",
        hold_seconds=0.15,
        display=display,
    )

    center_pose(
        service,
        geometry,
        duration_seconds=0.95,
        label="CENTER AFTER CURIOSITY",
        display=display,
    )


def behavior_surprise(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] SURPRISE")

    if display is not None:
        display.show("SURPRISE")

    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center,
        target_vertical=geometry.vertical_up,
        duration_seconds=0.22,
        fps=100,
        easing=ease_out_quint,
        label="SURPRISE SNAP UP",
        hold_seconds=0.20,
        display=display,
    )
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center + 5.0,
        target_vertical=geometry.vertical_up + 2.0,
        duration_seconds=0.18,
        fps=95,
        easing=ease_linear,
        label="SURPRISE MICRO FLINCH",
        hold_seconds=0.04,
        display=display,
    )
    center_pose(
        service,
        geometry,
        duration_seconds=1.05,
        label="CENTER AFTER SURPRISE",
        display=display,
    )


def behavior_sadness(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] SADNESS")

    if display is not None:
        display.show("SADNESS")

    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center - 8.0,
        target_vertical=geometry.vertical_down_safe,
        duration_seconds=2.8,
        fps=75,
        easing=ease_in_out_sine,
        label="SAD DROOP",
        hold_seconds=0.40,
        display=display,
    )
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center + 4.0,
        target_vertical=geometry.vertical_down_safe - 2.0,
        duration_seconds=1.6,
        fps=70,
        easing=ease_in_out_sine,
        label="SAD SWAY",
        hold_seconds=0.15,
        display=display,
    )
    center_pose(
        service,
        geometry,
        duration_seconds=1.25,
        label="CENTER AFTER SADNESS",
        display=display,
    )


def behavior_no_problem(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    display: BehaviorDisplayBridge | None = None,
) -> None:
    print("[PAN_TILT BEHAVIOR] CONFIDENCE")

    if display is not None:
        display.show("CONFIDENCE")

    animate_path(
        service,
        geometry,
        points=[
            (geometry.horizontal_center - 10.0, geometry.vertical_center - 2.0),
            (geometry.horizontal_center + 12.0, geometry.vertical_center - 2.0),
            (geometry.horizontal_center, geometry.vertical_center - 4.0),
            (geometry.horizontal_center, geometry.vertical_center),
        ],
        duration_seconds=1.9,
        fps=80,
        easing=ease_in_out_cubic,
        label="CONFIDENT NOD SWEEP",
        hold_seconds=0.15,
        display=display,
    )

    center_pose(
        service,
        geometry,
        duration_seconds=0.85,
        label="CENTER AFTER CONFIDENCE",
        display=display,
    )


def main() -> None:
    settings = load_settings()
    config = settings.get("pan_tilt", {})

    print("[PAN_TILT BEHAVIOR] Building PanTiltService...")
    service = PanTiltService(config=config)
    display = BehaviorDisplayBridge()

    try:
        geometry = build_view_geometry(service)

        print(f"[PAN_TILT BEHAVIOR] Initial status: {service.status()}")
        print(f"[PAN_TILT BEHAVIOR] Geometry: {geometry}")

        center_pose(
            service,
            geometry,
            duration_seconds=1.1,
            label="INITIAL CENTER",
            display=display,
        )

        run_speed_profiles(service, geometry, display=display)
        run_ultra_smooth_showcase(service, geometry, display=display)

        behavior_laugh(service, geometry, display=display)
        behavior_disagree(service, geometry, display=display)
        behavior_anger(service, geometry, display=display)
        behavior_happiness(service, geometry, display=display)
        behavior_curiosity(service, geometry, display=display)
        behavior_surprise(service, geometry, display=display)
        behavior_sadness(service, geometry, display=display)
        behavior_no_problem(service, geometry, display=display)

        center_pose(
            service,
            geometry,
            duration_seconds=1.15,
            label="FINAL CENTER",
            display=display,
        )

    finally:
        display.clear()
        service.close()
        print("[PAN_TILT BEHAVIOR] Closed.")


if __name__ == "__main__":
    main()