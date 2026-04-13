from __future__ import annotations

import re

from modules.understanding.parsing.models import IntentResult


class IntentParserPanTiltMixin:
    def _parse_pan_tilt(self, normalized: str) -> IntentResult | None:
        direction_patterns = {
            "left": (
                r"\b(popatrz|spojrz|patrz|obroc sie|skrec) w lewo\b",
                r"\blook left\b",
                r"\bturn left\b",
            ),
            "right": (
                r"\b(popatrz|spojrz|patrz|obroc sie|skrec) w prawo\b",
                r"\blook right\b",
                r"\bturn right\b",
            ),
            "up": (
                r"\b(popatrz|spojrz|patrz) w gore\b",
                r"\bspojrz do gory\b",
                r"\blook up\b",
            ),
            "down": (
                r"\b(popatrz|spojrz|patrz) w dol\b",
                r"\bspojrz na dol\b",
                r"\blook down\b",
            ),
        }

        for direction, patterns in direction_patterns.items():
            if any(re.search(pattern, normalized) for pattern in patterns):
                return IntentResult.from_action(
                    action="look_direction",
                    data={"direction": direction},
                    confidence=0.98,
                    normalized_text=normalized,
                )

        return None