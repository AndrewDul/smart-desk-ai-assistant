from __future__ import annotations

import random

from PIL import Image, ImageDraw


class DisplayServiceEyes:
    """Idle eye animation rendering for the display service."""

    driver: str
    device: object | None
    device_width: int
    device_height: int
    width: int
    height: int
    font_body: object
    font_small: object
    _gaze_pattern: list[int]
    _gaze_index: int
    _next_gaze_change: float
    _blink_frames: list[float]
    _blink_index: int
    _next_blink: float

    def _render_eyes(self, now: float) -> None:
        if self.device is None:
            return

        if now >= self._next_gaze_change:
            self._gaze_index = (self._gaze_index + 1) % len(self._gaze_pattern)
            self._next_gaze_change = now + random.uniform(1.6, 2.4)

        if self._blink_index == -1 and now >= self._next_blink:
            self._blink_index = 0
            self._next_blink = now + random.uniform(3.5, 5.5)

        if self._blink_index != -1:
            blink = self._blink_frames[self._blink_index]
            self._blink_index += 1
            if self._blink_index >= len(self._blink_frames):
                self._blink_index = -1
        else:
            blink = 1.0

        pupil_offset = self._gaze_pattern[self._gaze_index]

        if self.driver == "ssd1306":
            from luma.core.render import canvas

            with canvas(self.device) as draw:
                draw.rectangle((0, 0, self.width - 1, self.height - 1), outline="black", fill="black")
                self._draw_eye_oled(draw, 14, 18, 50, 46, pupil_offset, blink)
                self._draw_eye_oled(draw, 78, 18, 114, 46, pupil_offset, blink)
                draw.line((12, 14, 52, 12), fill="white")
                draw.line((76, 12, 116, 14), fill="white")
            return

        image = Image.new("RGB", (self.device_width, self.device_height), (10, 14, 24))
        draw = ImageDraw.Draw(image)

        draw.text((16, 14), "Smart Desk AI", font=self.font_body, fill=(230, 236, 242))
        draw.text((16, 38), "Animated eyes", font=self.font_small, fill=(170, 180, 190))

        self._draw_eye_color(draw, 55, 78, 125, 156, pupil_offset, blink)
        self._draw_eye_color(draw, 195, 78, 265, 156, pupil_offset, blink)

        draw.line((48, 62, 130, 52), fill=(245, 247, 250), width=4)
        draw.line((190, 52, 272, 62), fill=(245, 247, 250), width=4)

        bar_x = 20 + (int(now * 10) * 6) % max(1, (self.device_width - 80))
        draw.rounded_rectangle((bar_x, 185, bar_x + 50, 205), radius=6, fill=(80, 220, 255))

        self._show_image(image)

    def _draw_eye_color(
        self,
        draw: ImageDraw.ImageDraw,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        pupil_offset: int,
        blink: float,
    ) -> None:
        outline = (245, 247, 250)
        eye_fill = (235, 245, 255)
        pupil_fill = (16, 32, 64)
        bg = (10, 14, 24)

        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        eye_height = y2 - y1

        if blink <= 0.08:
            draw.line((x1, center_y, x2, center_y), fill=outline, width=4)
            return

        draw.ellipse((x1, y1, x2, y2), outline=outline, fill=eye_fill, width=3)

        pupil_radius = 12
        pupil_x = center_x + pupil_offset
        pupil_x = max(x1 + pupil_radius + 8, min(x2 - pupil_radius - 8, pupil_x))
        pupil_y = center_y

        draw.ellipse(
            (
                pupil_x - pupil_radius,
                pupil_y - pupil_radius,
                pupil_x + pupil_radius,
                pupil_y + pupil_radius,
            ),
            outline=pupil_fill,
            fill=pupil_fill,
        )
        draw.ellipse(
            (
                pupil_x - pupil_radius + 6,
                pupil_y - pupil_radius + 6,
                pupil_x - pupil_radius + 10,
                pupil_y - pupil_radius + 10,
            ),
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
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        pupil_offset: int,
        openness: float,
    ) -> None:
        center_y = (y1 + y2) // 2
        center_x = (x1 + x2) // 2
        eye_height = y2 - y1

        if openness <= 0.08:
            draw.line((x1, center_y, x2, center_y), fill="white", width=2)
            return

        draw.ellipse((x1, y1, x2, y2), outline="white", fill="white")

        pupil_radius = 5
        pupil_x = center_x + pupil_offset
        pupil_y = center_y
        pupil_x = max(x1 + 10, min(x2 - 10, pupil_x))

        draw.ellipse(
            (
                pupil_x - pupil_radius,
                pupil_y - pupil_radius,
                pupil_x + pupil_radius,
                pupil_y + pupil_radius,
            ),
            outline="black",
            fill="black",
        )
        draw.ellipse((pupil_x - 1, pupil_y - 1, pupil_x, pupil_y), outline="white", fill="white")

        cover = int(((1.0 - openness) * eye_height) / 2)
        if cover > 0:
            draw.rectangle((x1 - 1, y1 - 1, x2 + 1, y1 + cover), outline="black", fill="black")
            draw.rectangle((x1 - 1, y2 - cover, x2 + 1, y2 + 1), outline="black", fill="black")
            draw.line((x1 + 2, y1 + cover, x2 - 2, y1 + cover), fill="white")
            draw.line((x1 + 2, y2 - cover, x2 - 2, y2 - cover), fill="white")


__all__ = ["DisplayServiceEyes"]