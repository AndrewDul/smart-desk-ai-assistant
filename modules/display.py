from __future__ import annotations

import random
import threading
import time
from typing import Iterable

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import ImageFont


class ConsoleDisplay:
    def __init__(
        self,
        port: int = 1,
        address: int = 0x3C,
        rotate: int = 0,
        width: int = 128,
        height: int = 64,
    ) -> None:
        self.width = width
        self.height = height
        self.font = ImageFont.load_default()
        self.device = None

        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._overlay_title = ""
        self._overlay_lines: list[str] = []
        self._overlay_until = 0.0

        self._gaze_pattern = [0, -6, 0, 6, 0]
        self._gaze_index = 0
        self._next_gaze_change = time.time() + 2.0

        self._blink_frames = [1.0, 0.8, 0.55, 0.25, 0.05, 0.25, 0.55, 0.8, 1.0]
        self._blink_index = -1
        self._next_blink = time.time() + random.uniform(3.0, 5.0)

        try:
            serial = i2c(port=port, address=address)
            self.device = ssd1306(serial, rotate=rotate)
            print(f"[DISPLAY] OLED ready on I2C address 0x{address:02X}")
        except Exception as exc:
            print(f"[DISPLAY] OLED init failed: {exc}")

        self._thread = threading.Thread(target=self._render_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self.device is not None:
            try:
                with canvas(self.device) as draw:
                    draw.rectangle(self.device.bounding_box, outline="black", fill="black")
            except Exception:
                pass

    def show_block(self, title: str, lines: Iterable[str], duration: float = 10.0) -> None:
        safe_lines = [self._trim_text(str(line), 22) for line in lines][:5]

        with self._lock:
            self._overlay_title = self._trim_text(title, 20)
            self._overlay_lines = safe_lines
            self._overlay_until = time.time() + duration

        self._print_block(self._overlay_title, safe_lines)

    def show_status(self, state: dict, timer_status: dict, duration: float = 10.0) -> None:
        lines = [
            f"focus: {'ON' if state.get('focus_mode') else 'OFF'}",
            f"break: {'ON' if state.get('break_mode') else 'OFF'}",
            f"timer: {state.get('current_timer') or 'none'}",
            f"run: {'ON' if timer_status.get('running') else 'OFF'}",
        ]
        self.show_block("STATUS", lines, duration=duration)

    def _render_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()

            with self._lock:
                overlay_active = now < self._overlay_until
                title = self._overlay_title
                lines = list(self._overlay_lines)

            if overlay_active:
                self._render_block(title, lines)
            else:
                self._render_eyes(now)

            time.sleep(0.08)

    def _render_block(self, title: str, lines: list[str]) -> None:
        if self.device is None:
            return

        with canvas(self.device) as draw:
            draw.rectangle((0, 0, self.width - 1, self.height - 1), outline="black", fill="black")

            draw.rectangle((0, 0, self.width - 1, 12), outline="white", fill="white")
            draw.text((4, 2), title, font=self.font, fill="black")

            y = 16
            for line in lines:
                draw.text((4, y), line, font=self.font, fill="white")
                y += 10

    def _render_eyes(self, now: float) -> None:
        if self.device is None:
            return

        if now >= self._next_gaze_change:
            self._gaze_index = (self._gaze_index + 1) % len(self._gaze_pattern)
            self._next_gaze_change = now + 2.0

        if self._blink_index == -1 and now >= self._next_blink:
            self._blink_index = 0
            self._next_blink = now + random.uniform(3.5, 5.5)

        if self._blink_index != -1:
            openness = self._blink_frames[self._blink_index]
            self._blink_index += 1
            if self._blink_index >= len(self._blink_frames):
                self._blink_index = -1
        else:
            openness = 1.0

        pupil_offset = self._gaze_pattern[self._gaze_index]

        with canvas(self.device) as draw:
            draw.rectangle((0, 0, self.width - 1, self.height - 1), outline="black", fill="black")

            self._draw_eye(draw, 14, 18, 50, 46, pupil_offset, openness)
            self._draw_eye(draw, 78, 18, 114, 46, pupil_offset, openness)

            draw.line((12, 14, 52, 12), fill="white")
            draw.line((76, 12, 116, 14), fill="white")

    def _draw_eye(
        self,
        draw,
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

        draw.ellipse(
            (
                pupil_x - 1,
                pupil_y - 1,
                pupil_x,
                pupil_y,
            ),
            outline="white",
            fill="white",
        )

        cover = int(((1.0 - openness) * eye_height) / 2)

        if cover > 0:
            draw.rectangle((x1 - 1, y1 - 1, x2 + 1, y1 + cover), outline="black", fill="black")
            draw.rectangle((x1 - 1, y2 - cover, x2 + 1, y2 + 1), outline="black", fill="black")

            top_line_y = y1 + cover
            bottom_line_y = y2 - cover

            draw.line((x1 + 2, top_line_y, x2 - 2, top_line_y), fill="white")
            draw.line((x1 + 2, bottom_line_y, x2 - 2, bottom_line_y), fill="white")

    @staticmethod
    def _trim_text(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @staticmethod
    def _print_block(title: str, lines: list[str]) -> None:
        print("\n" + "=" * 32)
        print(title)
        print("-" * 32)
        for line in lines:
            print(line)
        print("=" * 32)
