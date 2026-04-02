from __future__ import annotations

import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.io.vendors.waveshare_lcd import LCD_2inch


IMAGE_ROTATION = 180
BACKLIGHT_PERCENT = 70
STATIC_SCREEN_SECONDS = 4
ANIMATION_SECONDS = 10
FPS = 10


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


def apply_rotation(image: Image.Image) -> Image.Image:
    if IMAGE_ROTATION == 0:
        return image
    return image.rotate(IMAGE_ROTATION)


def draw_static_diagnostic_frame(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (10, 14, 24))
    draw = ImageDraw.Draw(image)

    title_font = load_font(26)
    body_font = load_font(18)
    small_font = load_font(14)

    draw.rectangle((0, 0, width - 1, height - 1), outline=(255, 255, 255), width=2)

    draw.line((0, 0, width - 1, 0), fill=(255, 0, 0), width=3)
    draw.line((0, height - 1, width - 1, height - 1), fill=(0, 255, 0), width=3)
    draw.line((0, 0, 0, height - 1), fill=(0, 120, 255), width=3)
    draw.line((width - 1, 0, width - 1, height - 1), fill=(255, 255, 0), width=3)

    draw.text((18, 18), "Waveshare LCD Test", font=title_font, fill=(255, 255, 255))
    draw.text((18, 58), "Vendor driver direct test", font=body_font, fill=(220, 230, 240))
    draw.text((18, 86), "This bypasses ConsoleDisplay", font=body_font, fill=(220, 230, 240))
    draw.text((18, 114), "If this works, hardware is OK", font=body_font, fill=(220, 230, 240))

    draw.text((18, 160), "TOP-LEFT", font=small_font, fill=(255, 120, 120))
    draw.text((width - 90, 160), "TOP-RIGHT", font=small_font, fill=(255, 255, 120))
    draw.text((18, height - 28), "BOTTOM-LEFT", font=small_font, fill=(120, 200, 255))
    draw.text((width - 110, height - 28), "BOTTOM-RIGHT", font=small_font, fill=(120, 255, 120))

    return image


def draw_eye(draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, pupil_offset: int, blink: float) -> None:
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


def build_eye_frame(width: int, height: int, frame_index: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (10, 14, 24))
    draw = ImageDraw.Draw(image)

    title_font = load_font(18)
    small_font = load_font(14)

    phase = frame_index / 10.0
    pupil_offset = int(math.sin(phase * 1.7) * 12)

    blink_cycle = frame_index % 40
    if 28 <= blink_cycle <= 32:
        blink_values = {
            28: 0.8,
            29: 0.45,
            30: 0.08,
            31: 0.45,
            32: 0.8,
        }
        blink = blink_values[blink_cycle]
    else:
        blink = 1.0

    draw.text((16, 14), "Eye animation direct test", font=title_font, fill=(230, 236, 242))
    draw.text((16, 38), f"frame: {frame_index}", font=small_font, fill=(170, 180, 190))

    draw_eye(draw, 55, 78, 125, 156, pupil_offset, blink)
    draw_eye(draw, 195, 78, 265, 156, pupil_offset, blink)

    draw.line((48, 62, 130, 52), fill=(245, 247, 250), width=4)
    draw.line((190, 52, 272, 62), fill=(245, 247, 250), width=4)

    bar_x = 20 + (frame_index * 6) % (width - 80)
    draw.rounded_rectangle((bar_x, 185, bar_x + 50, 205), radius=6, fill=(80, 220, 255))

    draw.text((16, 214), "If this animates, repeated ShowImage works", font=small_font, fill=(190, 200, 210))

    return image


def main() -> None:
    print("[VENDOR LCD TEST] Initializing display...")

    disp = LCD_2inch.LCD_2inch()
    disp.Init()
    disp.clear()
    disp.bl_DutyCycle(BACKLIGHT_PERCENT)

    canvas_width = disp.height
    canvas_height = disp.width

    print(f"[VENDOR LCD TEST] Canvas: {canvas_width}x{canvas_height}")
    print(f"[VENDOR LCD TEST] Backlight: {BACKLIGHT_PERCENT}%")
    print(f"[VENDOR LCD TEST] Rotation before ShowImage: {IMAGE_ROTATION}")

    static_image = draw_static_diagnostic_frame(canvas_width, canvas_height)
    disp.ShowImage(apply_rotation(static_image))
    print(f"[VENDOR LCD TEST] Static diagnostic frame for {STATIC_SCREEN_SECONDS}s...")
    time.sleep(STATIC_SCREEN_SECONDS)

    total_frames = ANIMATION_SECONDS * FPS
    print(f"[VENDOR LCD TEST] Animating for {ANIMATION_SECONDS}s at {FPS} FPS...")

    for frame_index in range(total_frames):
        frame = build_eye_frame(canvas_width, canvas_height, frame_index)
        disp.ShowImage(apply_rotation(frame))
        time.sleep(1.0 / FPS)

    print("[VENDOR LCD TEST] Finished. Leaving last frame on screen.")
    print("[VENDOR LCD TEST] Press Ctrl+C if you want to stop the process manually.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[VENDOR LCD TEST] Interrupted by user.")