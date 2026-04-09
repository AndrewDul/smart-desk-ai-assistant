from __future__ import annotations

import unicodedata
from pathlib import Path

from PIL import Image, ImageFont

from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__package__ or __name__)


class DisplayServiceUtils:
    """Small shared helpers for the display service."""

    rotate: int
    is_color: bool

    def _apply_rotation(self, image: Image.Image) -> Image.Image:
        if self.rotate == 0:
            return image
        return image.rotate(self.rotate)

    @staticmethod
    def _resample_filter():
        if hasattr(Image, "Resampling"):
            return Image.Resampling.LANCZOS
        return Image.LANCZOS

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

    @staticmethod
    def _trim_text(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @staticmethod
    def _wrap_text(text: str, max_len: int) -> list[str]:
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
        lowered = str(text or "").lower().strip()
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


__all__ = ["LOGGER", "DisplayServiceUtils"]