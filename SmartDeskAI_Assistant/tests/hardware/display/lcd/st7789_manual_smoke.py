from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image, ImageDraw, ImageFont
import st7789


WIDTH = 240
HEIGHT = 320

SPI_PORT = 0
SPI_CS = 0
SPI_SPEED_HZ = 16_000_000

PIN_DC = 25
PIN_RST = 27
PIN_BL = 18

ROTATION = 0
OFFSET_LEFT = 0
OFFSET_TOP = 0


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


def main() -> None:
    print("[LCD TEST] Starting ST7789 manual smoke test...")

    display = st7789.ST7789(
        port=SPI_PORT,
        cs=SPI_CS,
        dc=PIN_DC,
        backlight=PIN_BL,
        rst=PIN_RST,
        width=WIDTH,
        height=HEIGHT,
        rotation=ROTATION,
        spi_speed_hz=SPI_SPEED_HZ,
        offset_left=OFFSET_LEFT,
        offset_top=OFFSET_TOP,
    )

    print("[LCD TEST] Display object created.")

    image = Image.new("RGB", (WIDTH, HEIGHT), (8, 12, 22))
    draw = ImageDraw.Draw(image)

    font_title = load_font(24)
    font_body = load_font(18)
    font_small = load_font(14)

    draw.rounded_rectangle(
        (8, 8, WIDTH - 9, HEIGHT - 9),
        radius=16,
        outline=(80, 220, 255),
        width=2,
        fill=(8, 12, 22),
    )

    draw.rounded_rectangle(
        (18, 18, WIDTH - 19, 58),
        radius=10,
        outline=(80, 220, 255),
        fill=(80, 220, 255),
    )
    draw.text((26, 27), "Smart Desk AI", font=font_title, fill=(0, 0, 0))

    lines = [
        "Waveshare 2inch LCD",
        "ST7789 full screen test",
        "No noise = backend OK",
        "Right edge should be clean",
    ]

    y = 85
    for line in lines:
        draw.text((24, y), line, font=font_body, fill=(245, 247, 250))
        y += 32

    draw.line((0, 0, WIDTH - 1, 0), fill=(255, 0, 0), width=2)
    draw.line((0, HEIGHT - 1, WIDTH - 1, HEIGHT - 1), fill=(0, 255, 0), width=2)
    draw.line((0, 0, 0, HEIGHT - 1), fill=(0, 120, 255), width=2)
    draw.line((WIDTH - 1, 0, WIDTH - 1, HEIGHT - 1), fill=(255, 255, 0), width=2)

    draw.text(
        (18, HEIGHT - 26),
        "BL=18  DC=25  RST=27  SPI=0.0",
        font=font_small,
        fill=(180, 190, 205),
    )

    print("[LCD TEST] Sending image to display...")
    display.display(image)
    print("[LCD TEST] Image sent. Waiting 10 seconds...")
    time.sleep(10)
    print("[LCD TEST] Finished successfully.")


if __name__ == "__main__":
    main()