from __future__ import annotations

import random
import threading
import time
import unicodedata
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


class ConsoleDisplay:
    def __init__(
        self,
        driver: str = "ssd1306",
        interface: str = "i2c",
        port: int = 1,
        address: int = 0x3C,
        rotate: int = 0,
        width: int = 128,
        height: int = 64,
        spi_port: int = 0,
        spi_device: int = 0,
        gpio_dc: int = 25,
        gpio_rst: int = 27,
        gpio_light: int = 18,
    ) -> None:
        self.driver = str(driver).lower().strip()
        self.interface = str(interface).lower().strip()
        self.width = int(width)
        self.height = int(height)
        self.rotate = int(rotate)

        self.device = None
        self.device_width = self.width
        self.device_height = self.height
        self.is_color = self.driver == "waveshare_2inch"

        self.font_title = self._load_font(26 if self.is_color else 11)
        self.font_body = self._load_font(18 if self.is_color else 11)
        self.font_small = self._load_font(14 if self.is_color else 11)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._overlay_title = ""
        self._overlay_lines: list[str] = []
        self._overlay_until = 0.0
        self._overlay_style = "standard"

        self._gaze_pattern = [0, -10, 0, 10, 0, -5, 5, 0]
        self._gaze_index = 0
        self._next_gaze_change = time.time() + 2.0

        self._blink_frames = [1.0, 0.8, 0.45, 0.08, 0.45, 0.8, 1.0]
        self._blink_index = -1
        self._next_blink = time.time() + random.uniform(3.0, 5.0)

        self._last_frame_signature: bytes | None = None

        try:
            self.device = self._create_device(
                port=port,
                address=address,
                rotate=rotate,
                width=width,
                height=height,
                spi_port=spi_port,
                spi_device=spi_device,
                gpio_dc=gpio_dc,
                gpio_rst=gpio_rst,
                gpio_light=gpio_light,
            )
            if self.device is not None:
                print(
                    f"[DISPLAY] {self.driver} ready "
                    f"({self.device_width}x{self.device_height}, rotate={self.rotate})"
                )
        except Exception as exc:
            print(f"[DISPLAY] init failed for {self.driver}: {exc}")

        self._thread = threading.Thread(target=self._render_loop, daemon=True)
        self._thread.start()

    def _create_device(
        self,
        *,
        port: int,
        address: int,
        rotate: int,
        width: int,
        height: int,
        spi_port: int,
        spi_device: int,
        gpio_dc: int,
        gpio_rst: int,
        gpio_light: int,
    ):
        if self.driver == "ssd1306":
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306

            serial = i2c(port=port, address=address)
            device = ssd1306(serial, rotate=rotate, width=width, height=height)
            self.device_width = width
            self.device_height = height
            return device

        if self.driver == "waveshare_2inch":
            from modules.io.vendors.waveshare_lcd import LCD_2inch

            device = LCD_2inch.LCD_2inch()
            device.Init()
            device.clear()
            if hasattr(device, "bl_DutyCycle"):
                device.bl_DutyCycle(70)

            self.device_width = int(device.height)
            self.device_height = int(device.width)
            return device

        raise ValueError(f"Unsupported display driver: {self.driver}")

    def close(self) -> None:
        self._stop_event.set()

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self.device is None:
            return

        try:
            if self.driver == "ssd1306":
                from luma.core.render import canvas

                with canvas(self.device) as draw:
                    draw.rectangle(self.device.bounding_box, outline="black", fill="black")
            elif self.driver == "waveshare_2inch":
                image = Image.new("RGB", (self.device_width, self.device_height), self._bg())
                self._show_image(image, force=True)
        except Exception:
            pass

    def show_block(self, title: str, lines: Iterable[str], duration: float = 10.0) -> None:
        max_chars = 28 if self.is_color else 20
        max_lines = 7 if self.is_color else 5

        expanded_lines: list[str] = []
        for line in lines:
            expanded_lines.extend(self._wrap_text(str(line), max_chars))

        safe_lines = expanded_lines[:max_lines]
        safe_title = self._trim_text(title, max_chars)

        style = "brand" if self._normalize_text(title) == "devdul" else "standard"

        with self._lock:
            self._overlay_title = safe_title
            self._overlay_lines = safe_lines
            self._overlay_until = time.time() + max(duration, 0.1)
            self._overlay_style = style

        self._print_block(safe_title, safe_lines)

    def clear_overlay(self) -> None:
        with self._lock:
            self._overlay_until = 0.0
            self._overlay_title = ""
            self._overlay_lines = []
            self._overlay_style = "standard"

    def show_status(self, state: dict, timer_status: dict, duration: float = 10.0) -> None:
        lines = [
            f"focus: {'ON' if state.get('focus_mode') else 'OFF'}",
            f"break: {'ON' if state.get('break_mode') else 'OFF'}",
            f"timer: {state.get('current_timer') or 'none'}",
            f"run: {'ON' if timer_status.get('running') else 'OFF'}",
        ]
        self.show_block("STATUS", lines, duration=duration)

    def _render_loop(self) -> None:
        fps = 10 if self.driver == "waveshare_2inch" else 15
        delay = 1.0 / fps

        while not self._stop_event.is_set():
            now = time.time()

            with self._lock:
                overlay_active = now < self._overlay_until
                title = self._overlay_title
                lines = list(self._overlay_lines)
                style = self._overlay_style

            if overlay_active:
                self._render_block(title, lines, style)
            else:
                self._render_eyes(now)

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
            draw.rectangle((0, 0, self.device_width - 1, self.device_height - 1), outline=(255, 255, 255), width=2)
            draw.text((18, 18), title or "DevDul", font=title_font, fill=(255, 255, 255))

            y = 70
            for line in lines:
                draw.text((18, y), line, font=body_font, fill=(220, 230, 240))
                y += 30

            self._show_image(image)
            return

        draw.rectangle((0, 0, self.device_width - 1, self.device_height - 1), outline=(255, 255, 255), width=2)
        draw.rounded_rectangle((12, 12, self.device_width - 13, 58), radius=8, outline=(255, 255, 255), fill=(80, 220, 255))
        draw.text((20, 20), title, font=title_font, fill=(0, 0, 0))

        y = 82
        for line in lines:
            draw.text((20, y), line, font=body_font, fill=(230, 236, 242))
            y += 30

        draw.text((20, self.device_height - 24), "Smart Desk AI", font=small_font, fill=(180, 190, 205))

        self._show_image(image)

    def _render_block_oled(self, title: str, lines: list[str], style: str) -> None:
        from luma.core.render import canvas

        with canvas(self.device) as draw:
            draw.rectangle((0, 0, self.width - 1, self.height - 1), outline="black", fill="black")

            if style == "brand":
                draw.rectangle((6, 6, self.width - 7, self.height - 7), outline="white", fill="black")
                draw.text((self._center_x(title or "DevDul", self.font_small, self.width), 16), title or "DevDul", font=self.font_small, fill="white")

                if len(lines) > 0:
                    draw.text((self._center_x(lines[0], self.font_small, self.width), 32), lines[0], font=self.font_small, fill="white")
                if len(lines) > 1:
                    draw.text((self._center_x(lines[1], self.font_small, self.width), 46), lines[1], font=self.font_small, fill="white")
                return

            draw.rectangle((0, 0, self.width - 1, 12), outline="white", fill="white")
            draw.text((4, 2), title, font=self.font_small, fill="black")

            y = 16
            for line in lines:
                draw.text((4, y), line, font=self.font_small, fill="white")
                y += 10

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

        bar_x = 20 + (int(now * 10) * 6) % (self.device_width - 80)
        draw.rounded_rectangle((bar_x, 185, bar_x + 50, 205), radius=6, fill=(80, 220, 255))

        self._show_image(image)

    def _draw_eye_color(self, draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, pupil_offset: int, blink: float) -> None:
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

    def _draw_eye_oled(self, draw, x1: int, y1: int, x2: int, y2: int, pupil_offset: int, openness: float) -> None:
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

    def _apply_rotation(self, image: Image.Image) -> Image.Image:
        if self.rotate == 0:
            return image
        return image.rotate(self.rotate)

    def _show_image(self, image: Image.Image, force: bool = False) -> None:
        if self.driver != "waveshare_2inch" or self.device is None:
            return

        final = image.convert("RGB")

        if final.size != (self.device_width, self.device_height):
            final = final.resize((self.device_width, self.device_height))

        final = self._apply_rotation(final)

        signature = final.tobytes()
        if not force and signature == self._last_frame_signature:
            return

        self.device.ShowImage(final)
        self._last_frame_signature = signature

    def _center_x(self, text: str, font, width: int) -> int:
        if hasattr(font, "getbbox"):
            left, _, right, _ = font.getbbox(text)
            text_width = right - left
        else:
            text_width = len(text) * 6
        return max(0, (width - text_width) // 2)

    def _load_font(self, size: int):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]

        for candidate in candidates:
            path = Path(candidate)
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except Exception:
                    continue

        return ImageFont.load_default()

    def _bg(self):
        return (10, 14, 24) if self.is_color else "black"

    def _trim_text(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _wrap_text(self, text: str, max_len: int) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return [""]

        words = cleaned.split()
        lines: list[str] = []
        current = ""

        for word in words:
            test = word if not current else f"{current} {word}"
            if len(test) <= max_len:
                current = test
            else:
                if current:
                    lines.append(current)
                if len(word) <= max_len:
                    current = word
                else:
                    lines.append(word[:max_len])
                    current = word[max_len:]

        if current:
            lines.append(current)

        return lines

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = text.lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        return lowered

    @staticmethod
    def _print_block(title: str, lines: list[str]) -> None:
        print("\n" + "=" * 32)
        print(title)
        print("-" * 32)
        for line in lines:
            print(line)
        print("=" * 32)