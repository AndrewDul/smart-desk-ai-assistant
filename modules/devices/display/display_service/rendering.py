from __future__ import annotations

import time

from PIL import Image, ImageDraw

from .utils import LOGGER, DisplayServiceUtils


class DisplayServiceRendering(DisplayServiceUtils):
    """Render loop and block rendering for the display service."""

    driver: str
    device: object | None
    device_width: int
    device_height: int
    width: int
    height: int
    font_title: object
    font_body: object
    font_small: object
    _lock: object
    _stop_event: object
    _overlay_title: str
    _overlay_lines: list[str]
    _overlay_until: float
    _overlay_style: str
    _developer_overlay_title: str
    _developer_overlay_lines: list[str]
    _developer_overlay_enabled: bool
    _last_frame_signature: bytes | None

    def _render_loop(self) -> None:
        fps = 10 if self.driver == "waveshare_2inch" else 15
        delay = 1.0 / fps

        while not self._stop_event.is_set():
            try:
                now = time.time()

                with self._lock:
                    overlay_active = now < self._overlay_until
                    title = self._overlay_title
                    lines = list(self._overlay_lines)
                    style = self._overlay_style
                    developer_title = self._developer_overlay_title
                    developer_lines = list(self._developer_overlay_lines)
                    developer_active = self._developer_overlay_enabled

                if overlay_active:
                    self._render_block(title, lines, style)
                else:
                    self._render_eyes(
                        now,
                        developer_title=developer_title if developer_active else "",
                        developer_lines=developer_lines if developer_active else [],
                    )
            except Exception as error:
                LOGGER.warning("Display render loop warning: %s", error)

            time.sleep(delay)

    def _render_block(self, title: str, lines: list[str], style: str) -> None:
        if self.device is None:
            return

        if self.driver == "ssd1306":
            self._render_block_oled(title, lines, style)
            return

        image = Image.new("RGB", (self.device_width, self.device_height), (10, 14, 24))
        draw = ImageDraw.Draw(image)

        title_font = self.font_title
        body_font = self.font_body
        small_font = self.font_small

        if style == "brand":
            draw.rectangle(
                (0, 0, self.device_width - 1, self.device_height - 1),
                outline=(255, 255, 255),
                width=2,
            )
            draw.text((18, 18), title or "DevDul", font=title_font, fill=(255, 255, 255))

            y = 70
            for line in lines:
                draw.text((18, y), line, font=body_font, fill=(220, 230, 240))
                y += 30

            self._show_image(image)
            return

        draw.rectangle(
            (0, 0, self.device_width - 1, self.device_height - 1),
            outline=(255, 255, 255),
            width=2,
        )
        draw.rounded_rectangle(
            (12, 12, self.device_width - 13, 58),
            radius=8,
            outline=(255, 255, 255),
            fill=(80, 220, 255),
        )
        draw.text((20, 20), title, font=title_font, fill=(0, 0, 0))

        y = 82
        for line in lines:
            draw.text((20, y), line, font=body_font, fill=(230, 236, 242))
            y += 30

        draw.text(
            (20, self.device_height - 24),
            "Smart Desk AI",
            font=small_font,
            fill=(180, 190, 205),
        )

        self._show_image(image)

    def _render_block_oled(self, title: str, lines: list[str], style: str) -> None:
        from luma.core.render import canvas

        with canvas(self.device) as draw:
            draw.rectangle((0, 0, self.width - 1, self.height - 1), outline="black", fill="black")

            if style == "brand":
                draw.rectangle((6, 6, self.width - 7, self.height - 7), outline="white", fill="black")
                draw.text(
                    (self._center_x(title or "DevDul", self.font_small, self.width), 16),
                    title or "DevDul",
                    font=self.font_small,
                    fill="white",
                )

                if len(lines) > 0:
                    draw.text(
                        (self._center_x(lines[0], self.font_small, self.width), 32),
                        lines[0],
                        font=self.font_small,
                        fill="white",
                    )
                if len(lines) > 1:
                    draw.text(
                        (self._center_x(lines[1], self.font_small, self.width), 46),
                        lines[1],
                        font=self.font_small,
                        fill="white",
                    )
                return

            draw.rectangle((0, 0, self.width - 1, 12), outline="white", fill="white")
            draw.text((4, 2), title, font=self.font_small, fill="black")

            y = 16
            for line in lines:
                draw.text((4, y), line, font=self.font_small, fill="white")
                y += 10

    def _show_image(self, image: Image.Image, force: bool = False) -> None:
        if self.driver != "waveshare_2inch" or self.device is None:
            return

        final = image.convert("RGB")
        if final.size != (self.device_width, self.device_height):
            final = final.resize((self.device_width, self.device_height), self._resample_filter())

        final = self._apply_rotation(final)

        signature = final.tobytes()
        if not force and signature == self._last_frame_signature:
            return

        self.device.ShowImage(final)
        self._last_frame_signature = signature


__all__ = ["DisplayServiceRendering"]