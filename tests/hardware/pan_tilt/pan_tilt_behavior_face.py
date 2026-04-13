from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.devices.display.display_service import DisplayService
from modules.devices.pan_tilt import PanTiltService
from modules.shared.config.settings import load_settings


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


class BehaviorFaceDisplay:
    """
    Standalone display bridge for hardware behavior demos.

    It uses the existing DisplayService device configuration, but stops the
    default render loop so the test can fully control the LCD contents.
    """

    def __init__(self, settings: dict) -> None:
        display_cfg = dict(settings.get("display", {}) or {})
        self.enabled = bool(display_cfg.get("enabled", False))
        self.display = None

        if not self.enabled:
            return

        try:
            self.display = DisplayService(
                driver=display_cfg.get("driver", "waveshare_2inch"),
                interface=display_cfg.get("interface", "spi"),
                port=int(display_cfg.get("port", 1)),
                address=int(display_cfg.get("address", 0x3C)),
                rotate=int(display_cfg.get("rotate", 0)),
                width=int(display_cfg.get("width", 128)),
                height=int(display_cfg.get("height", 64)),
                spi_port=int(display_cfg.get("spi_port", 0)),
                spi_device=int(display_cfg.get("spi_device", 0)),
                gpio_dc=int(display_cfg.get("gpio_dc", 25)),
                gpio_rst=int(display_cfg.get("gpio_rst", 27)),
                gpio_light=int(display_cfg.get("gpio_light", 18)),
            )

            # Stop the normal idle render loop so our custom frames are not overwritten.
            self.display._stop_event.set()
            if self.display._thread.is_alive():
                self.display._thread.join(timeout=1.0)

        except Exception as error:
            print(f"[PAN_TILT FACE] Display unavailable: {error}")
            self.display = None
            self.enabled = False

    def clear(self) -> None:
        if self.display is None:
            return

        try:
            image = Image.new(
                "RGB" if self.display.is_color else "1",
                (self.display.device_width, self.display.device_height),
                self.display._bg(),
            )
            self.display._show_image(image, force=True)
        except Exception as error:
            print(f"[PAN_TILT FACE] Clear failed: {error}")

    def close(self) -> None:
        if self.display is None:
            return
        try:
            self.clear()
            self.display.close()
        except Exception:
            pass

    def show_expression(
        self,
        expression: str,
        *,
        label: str = "",
        blink: float = 1.0,
        gaze_x: float = 0.0,
        gaze_y: float = 0.0,
    ) -> None:
        if self.display is None:
            return

        try:
            if self.display.is_color:
                image = self._render_color_face(
                    expression=expression,
                    label=label,
                    blink=blink,
                    gaze_x=gaze_x,
                    gaze_y=gaze_y,
                )
            else:
                image = self._render_oled_face(
                    expression=expression,
                    label=label,
                    blink=blink,
                    gaze_x=gaze_x,
                    gaze_y=gaze_y,
                )
            self.display._show_image(image, force=True)
        except Exception as error:
            print(f"[PAN_TILT FACE] Render failed: {error}")

    def _render_color_face(
        self,
        *,
        expression: str,
        label: str,
        blink: float,
        gaze_x: float,
        gaze_y: float,
    ) -> Image.Image:
        width = self.display.device_width
        height = self.display.device_height

        bg = (10, 14, 24)
        fg = (240, 245, 250)
        eye_fill = (232, 242, 255)
        pupil_fill = (14, 30, 58)
        accent = (80, 220, 255)

        if expression == "angry":
            accent = (255, 90, 90)
        elif expression == "happy":
            accent = (255, 210, 90)
        elif expression == "sad":
            accent = (120, 180, 255)
        elif expression == "surprised":
            accent = (255, 255, 255)
        elif expression == "confident":
            accent = (130, 255, 180)

        image = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(image)

        title = label or expression.upper()
        draw.rounded_rectangle((14, 12, width - 15, 52), radius=10, outline=fg, fill=accent)
        draw.text((24, 20), title[:24], font=self.display.font_body, fill=(0, 0, 0))

        eye_top = 82
        eye_bottom = 165
        left_eye = (42, eye_top, 128, eye_bottom)
        right_eye = (192, eye_top, 278, eye_bottom)

        self._draw_face_eyebrows_color(draw, expression, fg)
        self._draw_eye_color(draw, left_eye, blink, gaze_x, gaze_y, eye_fill, pupil_fill, fg, bg)
        self._draw_eye_color(draw, right_eye, blink, gaze_x, gaze_y, eye_fill, pupil_fill, fg, bg)

        self._draw_mouth_color(draw, expression, accent, fg, width, height)

        draw.text(
            (18, height - 24),
            "NeXa behavior demo",
            font=self.display.font_small,
            fill=(175, 190, 208),
        )
        return image

    def _render_oled_face(
        self,
        *,
        expression: str,
        label: str,
        blink: float,
        gaze_x: float,
        gaze_y: float,
    ) -> Image.Image:
        width = self.display.device_width
        height = self.display.device_height

        image = Image.new("1", (width, height), "black")
        draw = ImageDraw.Draw(image)

        title = (label or expression.upper())[:16]
        draw.rectangle((0, 0, width - 1, 12), outline="white", fill="white")
        draw.text((3, 2), title, font=self.display.font_small, fill="black")

        left_eye = (14, 18, 50, 44)
        right_eye = (78, 18, 114, 44)

        self._draw_face_eyebrows_oled(draw, expression)
        self._draw_eye_oled(draw, left_eye, blink, gaze_x, gaze_y)
        self._draw_eye_oled(draw, right_eye, blink, gaze_x, gaze_y)

        self._draw_mouth_oled(draw, expression, width, height)
        return image

    def _draw_face_eyebrows_color(self, draw: ImageDraw.ImageDraw, expression: str, fg) -> None:
        if expression == "angry":
            draw.line((42, 76, 124, 58), fill=fg, width=5)
            draw.line((196, 58, 278, 76), fill=fg, width=5)
        elif expression == "sad":
            draw.line((42, 58, 124, 76), fill=fg, width=5)
            draw.line((196, 76, 278, 58), fill=fg, width=5)
        elif expression == "curious":
            draw.line((42, 70, 124, 58), fill=fg, width=4)
            draw.line((196, 60, 278, 60), fill=fg, width=4)
        else:
            draw.line((42, 64, 124, 56), fill=fg, width=4)
            draw.line((196, 56, 278, 64), fill=fg, width=4)

    def _draw_face_eyebrows_oled(self, draw: ImageDraw.ImageDraw, expression: str) -> None:
        if expression == "angry":
            draw.line((12, 18, 52, 12), fill="white")
            draw.line((76, 12, 116, 18), fill="white")
        elif expression == "sad":
            draw.line((12, 12, 52, 18), fill="white")
            draw.line((76, 18, 116, 12), fill="white")
        elif expression == "curious":
            draw.line((12, 18, 52, 12), fill="white")
            draw.line((76, 14, 116, 14), fill="white")
        else:
            draw.line((12, 14, 52, 12), fill="white")
            draw.line((76, 12, 116, 14), fill="white")

    def _draw_eye_color(
        self,
        draw: ImageDraw.ImageDraw,
        bounds: tuple[int, int, int, int],
        blink: float,
        gaze_x: float,
        gaze_y: float,
        eye_fill,
        pupil_fill,
        outline,
        bg,
    ) -> None:
        x1, y1, x2, y2 = bounds
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        eye_height = y2 - y1

        if blink <= 0.06:
            draw.line((x1, center_y, x2, center_y), fill=outline, width=4)
            return

        draw.ellipse((x1, y1, x2, y2), outline=outline, fill=eye_fill, width=3)

        pupil_radius = 12
        pupil_x = center_x + int(gaze_x)
        pupil_y = center_y + int(gaze_y)
        pupil_x = max(x1 + pupil_radius + 8, min(x2 - pupil_radius - 8, pupil_x))
        pupil_y = max(y1 + pupil_radius + 8, min(y2 - pupil_radius - 8, pupil_y))

        draw.ellipse(
            (pupil_x - pupil_radius, pupil_y - pupil_radius, pupil_x + pupil_radius, pupil_y + pupil_radius),
            outline=pupil_fill,
            fill=pupil_fill,
        )
        draw.ellipse(
            (pupil_x - 5, pupil_y - 5, pupil_x - 1, pupil_y - 1),
            outline=(255, 255, 255),
            fill=(255, 255, 255),
        )

        cover = int(((1.0 - blink) * eye_height) / 2)
        if cover > 0:
            draw.rectangle((x1 - 1, y1 - 1, x2 + 1, y1 + cover), fill=bg)
            draw.rectangle((x1 - 1, y2 - cover, x2 + 1, y2 + 1), fill=bg)
            draw.line((x1 + 2, y1 + cover, x2 - 2, y1 + cover), fill=outline, width=3)
            draw.line((x1 + 2, y2 - cover, x2 - 2, y2 - cover), fill=outline, width=3)

    def _draw_eye_oled(
        self,
        draw: ImageDraw.ImageDraw,
        bounds: tuple[int, int, int, int],
        blink: float,
        gaze_x: float,
        gaze_y: float,
    ) -> None:
        x1, y1, x2, y2 = bounds
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        eye_height = y2 - y1

        if blink <= 0.06:
            draw.line((x1, center_y, x2, center_y), fill="white", width=2)
            return

        draw.ellipse((x1, y1, x2, y2), outline="white", fill="white")

        pupil_radius = 5
        pupil_x = center_x + int(gaze_x * 0.45)
        pupil_y = center_y + int(gaze_y * 0.45)
        pupil_x = max(x1 + 9, min(x2 - 9, pupil_x))
        pupil_y = max(y1 + 9, min(y2 - 9, pupil_y))

        draw.ellipse(
            (pupil_x - pupil_radius, pupil_y - pupil_radius, pupil_x + pupil_radius, pupil_y + pupil_radius),
            outline="black",
            fill="black",
        )

        cover = int(((1.0 - blink) * eye_height) / 2)
        if cover > 0:
            draw.rectangle((x1 - 1, y1 - 1, x2 + 1, y1 + cover), outline="black", fill="black")
            draw.rectangle((x1 - 1, y2 - cover, x2 + 1, y2 + 1), outline="black", fill="black")
            draw.line((x1 + 2, y1 + cover, x2 - 2, y1 + cover), fill="white")
            draw.line((x1 + 2, y2 - cover, x2 - 2, y2 - cover), fill="white")

    def _draw_mouth_color(
        self,
        draw: ImageDraw.ImageDraw,
        expression: str,
        accent,
        fg,
        width: int,
        height: int,
    ) -> None:
        cx = width // 2
        y = 212

        if expression in {"happy", "laugh"}:
            draw.arc((cx - 42, y - 10, cx + 42, y + 28), start=15, end=165, fill=accent, width=5)
        elif expression == "sad":
            draw.arc((cx - 38, y + 6, cx + 38, y + 34), start=200, end=340, fill=fg, width=4)
        elif expression == "angry":
            draw.line((cx - 30, y + 18, cx + 30, y + 14), fill=accent, width=5)
        elif expression == "surprised":
            draw.ellipse((cx - 12, y + 3, cx + 12, y + 29), outline=fg, width=4)
        elif expression == "disagree":
            draw.arc((cx - 34, y + 2, cx + 34, y + 22), start=190, end=350, fill=fg, width=4)
        elif expression == "curious":
            draw.arc((cx - 28, y + 4, cx + 28, y + 18), start=205, end=330, fill=fg, width=4)
        elif expression == "confident":
            draw.line((cx - 20, y + 16, cx + 18, y + 12), fill=accent, width=4)
        else:
            draw.line((cx - 24, y + 16, cx + 24, y + 16), fill=fg, width=4)

    def _draw_mouth_oled(
        self,
        draw: ImageDraw.ImageDraw,
        expression: str,
        width: int,
        height: int,
    ) -> None:
        del height
        cx = width // 2
        y = 50

        if expression in {"happy", "laugh"}:
            draw.arc((cx - 18, y - 2, cx + 18, y + 12), start=15, end=165, fill="white")
        elif expression == "sad":
            draw.arc((cx - 16, y + 6, cx + 16, y + 18), start=200, end=340, fill="white")
        elif expression == "angry":
            draw.line((cx - 12, y + 10, cx + 12, y + 8), fill="white")
        elif expression == "surprised":
            draw.ellipse((cx - 5, y + 4, cx + 5, y + 14), outline="white")
        elif expression == "disagree":
            draw.arc((cx - 16, y + 4, cx + 16, y + 12), start=190, end=350, fill="white")
        elif expression == "curious":
            draw.arc((cx - 12, y + 4, cx + 12, y + 10), start=205, end=330, fill="white")
        elif expression == "confident":
            draw.line((cx - 8, y + 10, cx + 8, y + 8), fill="white")
        else:
            draw.line((cx - 10, y + 10, cx + 10, y + 10), fill="white")


def build_view_geometry(service: PanTiltService) -> ViewGeometry:
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
    expression: str = "neutral",
    label: str = "",
    blink: float = 1.0,
    gaze_x: float = 0.0,
    gaze_y: float = 0.0,
    hold_seconds: float = 0.0,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
    start_horizontal = float(service._angles["tilt"])
    start_vertical = float(service._angles["pan"])

    target_horizontal = clamp(target_horizontal, geometry.horizontal_min, geometry.horizontal_max)
    target_vertical = clamp(target_vertical, geometry.vertical_min, geometry.vertical_max)

    steps = max(2, int(max(0.2, float(duration_seconds)) * max(20, int(fps))))
    sleep_per_step = max(0.0, float(duration_seconds) / steps)

    if label:
        print(f"[PAN_TILT FACE] {label}")

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

        if face_display is not None:
            face_display.show_expression(
                expression,
                label=label,
                blink=blink,
                gaze_x=gaze_x,
                gaze_y=gaze_y,
            )

        if sleep_per_step > 0.0:
            time.sleep(sleep_per_step)

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
    expression: str = "neutral",
    label: str = "",
    blink: float = 1.0,
    gaze_x: float = 0.0,
    gaze_y: float = 0.0,
    hold_seconds: float = 0.0,
    face_display: BehaviorFaceDisplay | None = None,
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
        print(f"[PAN_TILT FACE] {label}")

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

            if face_display is not None:
                face_display.show_expression(
                    expression,
                    label=label,
                    blink=blink,
                    gaze_x=gaze_x,
                    gaze_y=gaze_y,
                )

            if sleep_per_step > 0.0:
                time.sleep(sleep_per_step)

    if hold_seconds > 0.0:
        time.sleep(hold_seconds)


def center_pose(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    duration_seconds: float = 1.0,
    label: str = "CENTER",
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center,
        target_vertical=geometry.vertical_center,
        duration_seconds=duration_seconds,
        fps=65,
        easing=ease_in_out_sine,
        expression="neutral",
        label=label,
        blink=1.0,
        gaze_x=0.0,
        gaze_y=0.0,
        hold_seconds=0.20,
        face_display=face_display,
    )


def behavior_laugh(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
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
        expression="happy",
        label="LAUGH READY",
        hold_seconds=0.05,
        face_display=face_display,
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
            expression="laugh",
            label="LAUGH POP",
            blink=0.72,
            gaze_x=side * 0.9,
            gaze_y=-2.0,
            hold_seconds=0.02,
            face_display=face_display,
        )
        animate_view_pose(
            service,
            geometry,
            target_horizontal=base_h - (side * 0.35),
            target_vertical=base_v + (amplitude * 0.30),
            duration_seconds=0.25,
            fps=95,
            easing=ease_in_out_sine,
            expression="happy",
            label="LAUGH SETTLE",
            blink=1.0,
            gaze_x=-side * 0.4,
            gaze_y=1.0,
            hold_seconds=0.03,
            face_display=face_display,
        )

    center_pose(service, geometry, duration_seconds=0.95, label="CENTER AFTER LAUGH", face_display=face_display)


def behavior_disagree(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
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
            expression="disagree",
            label="DISAGREE LEFT",
            gaze_x=-8.0,
            hold_seconds=0.01,
            face_display=face_display,
        )
        animate_view_pose(
            service,
            geometry,
            target_horizontal=geometry.horizontal_center + amplitude,
            target_vertical=base_v,
            duration_seconds=0.18,
            fps=90,
            easing=ease_linear,
            expression="disagree",
            label="DISAGREE RIGHT",
            gaze_x=8.0,
            hold_seconds=0.01,
            face_display=face_display,
        )

    center_pose(service, geometry, duration_seconds=0.75, label="CENTER AFTER DISAGREE", face_display=face_display)


def behavior_anger(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center,
        target_vertical=geometry.vertical_down_safe,
        duration_seconds=0.28,
        fps=95,
        easing=ease_out_quint,
        expression="angry",
        label="ANGER DROP",
        blink=0.90,
        gaze_x=0.0,
        gaze_y=3.0,
        hold_seconds=0.04,
        face_display=face_display,
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
        expression="angry",
        label="ANGER JABS",
        blink=0.82,
        gaze_y=4.0,
        hold_seconds=0.08,
        face_display=face_display,
    )

    center_pose(service, geometry, duration_seconds=1.05, label="CENTER AFTER ANGER", face_display=face_display)


def behavior_happiness(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
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
        expression="happy",
        label="HAPPY BOUNCE",
        blink=1.0,
        gaze_y=-2.0,
        hold_seconds=0.10,
        face_display=face_display,
    )

    center_pose(service, geometry, duration_seconds=0.95, label="CENTER AFTER HAPPINESS", face_display=face_display)


def behavior_curiosity(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
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
        expression="curious",
        label="CURIOUS SEARCH",
        blink=1.0,
        gaze_x=5.0,
        gaze_y=-1.0,
        hold_seconds=0.15,
        face_display=face_display,
    )

    center_pose(service, geometry, duration_seconds=0.95, label="CENTER AFTER CURIOSITY", face_display=face_display)


def behavior_surprise(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center,
        target_vertical=geometry.vertical_up,
        duration_seconds=0.22,
        fps=100,
        easing=ease_out_quint,
        expression="surprised",
        label="SURPRISE SNAP UP",
        blink=1.0,
        gaze_y=-4.0,
        hold_seconds=0.20,
        face_display=face_display,
    )
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center + 5.0,
        target_vertical=geometry.vertical_up + 2.0,
        duration_seconds=0.18,
        fps=95,
        easing=ease_linear,
        expression="surprised",
        label="SURPRISE MICRO FLINCH",
        blink=0.92,
        gaze_x=4.0,
        gaze_y=-2.0,
        hold_seconds=0.04,
        face_display=face_display,
    )
    center_pose(service, geometry, duration_seconds=1.05, label="CENTER AFTER SURPRISE", face_display=face_display)


def behavior_sadness(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center - 8.0,
        target_vertical=geometry.vertical_down_safe,
        duration_seconds=2.8,
        fps=75,
        easing=ease_in_out_sine,
        expression="sad",
        label="SAD DROOP",
        blink=0.96,
        gaze_y=4.0,
        hold_seconds=0.40,
        face_display=face_display,
    )
    animate_view_pose(
        service,
        geometry,
        target_horizontal=geometry.horizontal_center + 4.0,
        target_vertical=geometry.vertical_down_safe - 2.0,
        duration_seconds=1.6,
        fps=70,
        easing=ease_in_out_sine,
        expression="sad",
        label="SAD SWAY",
        blink=1.0,
        gaze_x=-3.0,
        gaze_y=3.0,
        hold_seconds=0.15,
        face_display=face_display,
    )
    center_pose(service, geometry, duration_seconds=1.25, label="CENTER AFTER SADNESS", face_display=face_display)


def behavior_confidence(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
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
        expression="confident",
        label="CONFIDENT NOD SWEEP",
        blink=1.0,
        gaze_y=-2.0,
        hold_seconds=0.15,
        face_display=face_display,
    )
    center_pose(service, geometry, duration_seconds=0.85, label="CENTER AFTER CONFIDENCE", face_display=face_display)


def run_ultra_smooth_showcase(
    service: PanTiltService,
    geometry: ViewGeometry,
    *,
    face_display: BehaviorFaceDisplay | None = None,
) -> None:
    total_points = 180
    total_duration = 7.2
    sleep_per_step = total_duration / total_points

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

        if face_display is not None:
            face_display.show_expression(
                "curious",
                label="ULTRA SMOOTH GLIDE",
                blink=1.0,
                gaze_x=lerp(-8.0, 8.0, progress),
                gaze_y=-1.5,
            )

        time.sleep(sleep_per_step)

    center_pose(service, geometry, duration_seconds=1.1, label="CENTER AFTER ULTRA SMOOTH", face_display=face_display)


def main() -> None:
    settings = load_settings()
    config = settings.get("pan_tilt", {})

    print("[PAN_TILT FACE] Building PanTiltService...")
    service = PanTiltService(config=config)
    face_display = BehaviorFaceDisplay(settings)

    try:
        geometry = build_view_geometry(service)

        print(f"[PAN_TILT FACE] Initial status: {service.status()}")
        print(f"[PAN_TILT FACE] Geometry: {geometry}")

        center_pose(
            service,
            geometry,
            duration_seconds=1.1,
            label="INITIAL CENTER",
            face_display=face_display,
        )

        run_ultra_smooth_showcase(service, geometry, face_display=face_display)

        behavior_laugh(service, geometry, face_display=face_display)
        behavior_disagree(service, geometry, face_display=face_display)
        behavior_anger(service, geometry, face_display=face_display)
        behavior_happiness(service, geometry, face_display=face_display)
        behavior_curiosity(service, geometry, face_display=face_display)
        behavior_surprise(service, geometry, face_display=face_display)
        behavior_sadness(service, geometry, face_display=face_display)
        behavior_confidence(service, geometry, face_display=face_display)

        center_pose(
            service,
            geometry,
            duration_seconds=1.15,
            label="FINAL CENTER",
            face_display=face_display,
        )

    finally:
        if face_display is not None:
            face_display.close()
        service.close()
        print("[PAN_TILT FACE] Closed.")


if __name__ == "__main__":
    main()