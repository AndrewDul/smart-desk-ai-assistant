from __future__ import annotations

import re
from difflib import SequenceMatcher

from modules.understanding.parsing.normalization import (
    clean_text,
    normalize_text,
    parse_spoken_number,
    strip_leading_fillers,
    token_overlap_score,
)


class IntentParserFuzzyHelpersMixin:
    def _parse_amount_text(self, text: str) -> int | None:
        cleaned = clean_text(text)
        if not cleaned:
            return None
        if re.fullmatch(r"\d+", cleaned):
            return int(cleaned)

        spoken = parse_spoken_number(cleaned)
        return int(spoken) if spoken is not None else None

    @staticmethod
    def _cleanup_reminder_message(text: str) -> str:
        cleaned = clean_text(text)
        prefixes = (
            "about ",
            "to ",
            "o ",
            "ze ",
            "zebym ",
            "ze mam ",
            "że ",
            "żebym ",
            "że mam ",
        )
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                normalized_cleaned = normalize_text(cleaned)
                normalized_prefix = normalize_text(prefix)
                if normalized_cleaned.startswith(normalized_prefix):
                    cleaned = cleaned[len(prefix) :].strip()
                    changed = True
        return clean_text(cleaned)

    @staticmethod
    def _cleanup_subject(text: str) -> str:
        cleaned = clean_text(text)
        prefixes = ("my ", "the ", "moje ", "moj ", "moja ")
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                normalized_cleaned = normalize_text(cleaned)
                normalized_prefix = normalize_text(prefix)
                if normalized_cleaned.startswith(normalized_prefix):
                    cleaned = cleaned[len(prefix) :].strip()
                    changed = True
        return strip_leading_fillers(cleaned)

    def _get_fuzzy_suggestions(
        self,
        normalized: str,
        allowed_actions: list[str] | None = None,
    ) -> list[dict[str, object]]:
        scores: list[dict[str, object]] = []
        min_ratio = 0.78 if len(normalized) > 5 else 0.85

        for phrase, action, _phrase_tokens in self.fuzzy_candidates:
            if allowed_actions is not None and action not in allowed_actions:
                continue

            sequence_ratio = SequenceMatcher(None, normalized, phrase).ratio()
            overlap_ratio = token_overlap_score(normalized, phrase)
            combined_ratio = max(sequence_ratio, overlap_ratio)

            if combined_ratio >= min_ratio:
                scores.append(
                    {
                        "action": action,
                        "label": self.action_labels.get(action, action),
                        "score": round(combined_ratio, 3),
                    }
                )

        unique: dict[str, dict[str, object]] = {}
        for item in sorted(scores, key=lambda x: float(x["score"]), reverse=True):
            unique.setdefault(str(item["action"]), item)

        return list(unique.values())[:2]

    @staticmethod
    def _matches_any_pattern(normalized: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, normalized) for pattern in patterns)

    @staticmethod
    def _mentions_assistant_target(tokens: set[str]) -> bool:
        return bool({"assistant", "asystenta", "asystent", "nexa"} & tokens)

    @staticmethod
    def _mentions_system_target(tokens: set[str]) -> bool:
        return "system" in tokens or {"raspberry", "pi"}.issubset(tokens) or "komputer" in tokens

    @staticmethod
    def _mentions_off_or_close(tokens: set[str]) -> bool:
        if "shutdown" in tokens:
            return True
        if {"shut", "down"}.issubset(tokens):
            return True
        if {"turn", "off"}.issubset(tokens):
            return True
        if {"switch", "off"}.issubset(tokens):
            return True
        if {"power", "off"}.issubset(tokens):
            return True
        if "wylacz" in tokens or "zamknij" in tokens:
            return True
        return False