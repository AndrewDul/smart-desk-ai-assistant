from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image, ImageDraw, ImageFont
from modules.io.vendors.waveshare_lcd import LCD_2inch


def load_font(size: int):
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


def make_canvas(display, color):
    return Image.new("RGB", (display.width, display.height), color)


def push(display, image, rotate=270):
    final = image.rotate(rotate, expand=True)
    display.ShowImage(final)


def show_overlay(display) -> None:
    image = make_canvas(display, "WHITE")
    draw = ImageDraw.Draw(image)

    width, height = image.size
    font_title = load_font(24)
    font_body = load_font(18)
    font_small = load_font(14)

    draw.rectangle((0, 0, width - 1, height - 1), outline="BLACK", fill="WHITE")
    draw.rounded_rectangle((10, 10, width - 11, 54), radius=8, outline="BLACK", fill=(80, 220, 255))
    draw.text((20, 18), "Smart Desk AI", font=font_title, fill="BLACK")

    lines = [
        "Waveshare direct test",
        "Buffer uses width,height",
        "Then rotate 270",
        "This should stay visible",
    ]
    y = 78
    for line in lines:
        draw.text((20, y), line, font=font_body, fill="BLACK")
        y += 30

    draw.line((0, 0, width - 1, 0), fill=(255, 0, 0), width=2)
    draw.line((0, height - 1, width - 1, height - 1), fill=(0, 255, 0), width=2)
    draw.line((0, 0, 0, height - 1), fill=(0, 120, 255), width=2)
    draw.line((width - 1, 0, width - 1, height - 1), fill=(255, 200, 0), width=2)

    draw.text((20, height - 24), "rotate(270)", font=font_small, fill="BLACK")

    push(display, image)


def show_eyes(display) -> None:
    image = make_canvas(display, (8, 12, 22))
    draw = ImageDraw.Draw(image)

    eyebrow_color = (245, 247, 250)
    eye_fill = (235, 245, 255)
    pupil_fill = (16, 32, 64)

    left = (70, 80, 145, 160)
    right = (175, 80, 250, 160)

    draw.ellipse(left, outline=eyebrow_color, fill=eye_fill, width=3)
    draw.ellipse(right, outline=eyebrow_color, fill=eye_fill, width=3)

    draw.ellipse((96, 108, 120, 132), outline=pupil_fill, fill=pupil_fill)
    draw.ellipse((201, 108, 225, 132), outline=pupil_fill, fill=pupil_fill)

    draw.line((64, 62, 148, 52), fill=eyebrow_color, width=4)
    draw.line((172, 52, 256, 62), fill=eyebrow_color, width=4)

    push(display, image)


def main() -> None:
    print("[WAVESHARE TEST] Init display...")
    display = LCD_2inch.LCD_2inch()
    display.Init()
    display.clear()

    print(f"[WAVESHARE TEST] Drawing buffer: {display.width}x{display.height}")

    print("[WAVESHARE TEST] Showing overlay for 8 seconds...")
    show_overlay(display)
    time.sleep(8)

    print("[WAVESHARE TEST] Showing static eyes for 12 seconds...")
    show_eyes(display)
    time.sleep(12)

    print("[WAVESHARE TEST] Finished.")


if __name__ == "__main__":
    main()