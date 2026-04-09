from __future__ import annotations

import re
import unicodedata
from typing import Any

from modules.runtime.contracts import normalize_text


class PendingFlowParsingHelpersMixin:
    def _follow_up_language(self, command_lang: str) -> str:
        follow_up = self.assistant.pending_follow_up or {}
        stored = str(follow_up.get("lang", follow_up.get("language", ""))).strip().lower()
        if stored in {"pl", "en"}:
            return stored
        return self._normalize_language(command_lang)

    def _is_yes(self, text: str) -> bool:
        return self._parse_confirmation_action(text) == "confirm_yes"

    def _is_no(self, text: str) -> bool:
        return self._parse_confirmation_action(text) == "confirm_no"

    def _parse_confirmation_action(self, text: str) -> str | None:
        parser = getattr(self.assistant, "parser", None)
        parse_method = getattr(parser, "parse", None)
        if callable(parse_method):
            try:
                result = parse_method(text)
                action = str(getattr(result, "action", "")).strip().lower()
                if action in {"confirm_yes", "confirm_no"}:
                    return action
                if isinstance(result, dict):
                    action = str(result.get("action", "")).strip().lower()
                    if action in {"confirm_yes", "confirm_no"}:
                        return action
            except Exception:
                pass

        normalized = normalize_text(text)
        yes_tokens = {
            "yes",
            "yeah",
            "yep",
            "sure",
            "correct",
            "tak",
            "jasne",
            "pewnie",
            "zgadza sie",
            "zgadza się",
            "potwierdzam",
        }
        no_tokens = {
            "no",
            "nope",
            "cancel",
            "stop",
            "never mind",
            "nie",
            "nie teraz",
            "anuluj",
            "zostaw to",
            "nieważne",
            "niewazne",
        }

        if normalized in yes_tokens:
            return "confirm_yes"
        if normalized in no_tokens:
            return "confirm_no"
        return None

    def _looks_like_cancel_request(self, text: str) -> bool:
        cancel_method = getattr(self.assistant, "_looks_like_cancel_request", None)
        if callable(cancel_method):
            try:
                return bool(cancel_method(text))
            except Exception:
                pass
        return self._is_no(text)

    def _parse_confirmation_choice(self, text: str) -> int | None:
        normalized = normalize_text(text)
        direct_map = {
            "1": 0,
            "one": 0,
            "first": 0,
            "pierwsza": 0,
            "pierwszy": 0,
            "pierwsze": 0,
            "1st": 0,
            "2": 1,
            "two": 1,
            "second": 1,
            "druga": 1,
            "drugi": 1,
            "drugie": 1,
            "2nd": 1,
        }
        return direct_map.get(normalized)

    def _extract_minutes_from_text(self, text: str) -> float | None:
        raw = str(text or "").strip()
        if not raw:
            return None

        normalized_ascii = self._normalize_for_numbers(raw)

        seconds_match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:s|sec|secs|second|seconds|sekunda|sekundy|sekund)\b",
            normalized_ascii,
        )
        if seconds_match:
            value = self._safe_float(seconds_match.group(1))
            if value is not None and value > 0:
                return max(value / 60.0, 1.0 / 60.0)

        minutes_match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:m|min|mins|minute|minutes|minuta|minuty|minut)\b",
            normalized_ascii,
        )
        if minutes_match:
            value = self._safe_float(minutes_match.group(1))
            if value is not None and value > 0:
                return value

        plain_number_match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", normalized_ascii)
        if plain_number_match:
            value = self._safe_float(plain_number_match.group(1))
            if value is not None and value > 0:
                return value

        spoken_map = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "jeden": 1,
            "jedna": 1,
            "dwa": 2,
            "dwie": 2,
            "trzy": 3,
            "cztery": 4,
            "piec": 5,
            "pięć": 5,
            "szesc": 6,
            "sześć": 6,
            "siedem": 7,
            "osiem": 8,
            "dziewiec": 9,
            "dziewięć": 9,
            "dziesiec": 10,
            "dziesięć": 10,
        }

        for token in normalized_ascii.split():
            if token in spoken_map:
                return float(spoken_map[token])

        return None

    def _extract_name(self, text: str) -> str | None:
        raw = str(text or "").strip()
        if not raw:
            return None

        patterns = [
            r"\b(?:mam na imie|mam na imię|nazywam sie|nazywam się|jestem)\s+([A-Za-zÀ-ÿ' -]{2,})$",
            r"\b(?:my name is|i am|i'm)\s+([A-Za-zÀ-ÿ' -]{2,})$",
        ]

        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if not match:
                continue
            first_token = match.group(1).strip().split()[0]
            normalized = self._normalize_name_token(first_token)
            if normalized:
                return normalized

        simple_tokens = re.findall(r"[A-Za-zÀ-ÿ'-]+", raw)
        if len(simple_tokens) == 1:
            return self._normalize_name_token(simple_tokens[0])

        return None

    @staticmethod
    def _normalize_name_token(token: str) -> str | None:
        cleaned = str(token or "").strip(" '-")
        if not cleaned:
            return None

        lowered = cleaned.lower()
        blocked = {
            "assistant",
            "timer",
            "focus",
            "break",
            "time",
            "date",
            "day",
            "help",
            "yes",
            "no",
            "tak",
            "nie",
        }
        if lowered in blocked:
            return None

        if not re.fullmatch(r"[A-Za-zÀ-ÿ'-]{2,20}", cleaned):
            return None

        return cleaned[:1].upper() + cleaned[1:].lower()

    @staticmethod
    def _normalize_for_numbers(text: str) -> str:
        lowered = str(text or "").strip().lower()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s.,]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _safe_float(value: str) -> float | None:
        raw = str(value or "").replace(",", ".").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        return "pl" if normalized.startswith("pl") else "en"

    @staticmethod
    def _first_callable(obj: Any, *names: str):
        for name in names:
            method = getattr(obj, name, None)
            if callable(method):
                return method
        return None

    @staticmethod
    def _result_ok(result: Any) -> bool:
        if isinstance(result, tuple) and result:
            return bool(result[0])
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result["ok"])
            if "success" in result:
                return bool(result["success"])
        return bool(result)

    @staticmethod
    def _result_message(result: Any) -> str:
        if isinstance(result, tuple) and len(result) >= 2:
            return str(result[1] or "").strip()
        if isinstance(result, dict):
            for key in ("message", "detail", "error"):
                value = result.get(key)
                if value:
                    return str(value).strip()
        return ""

    @staticmethod
    def _coerce_suggestions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "")).strip().lower()
            if not action:
                continue
            normalized = {
                "action": action,
                "payload": dict(item.get("payload", {}) or {}),
                "confidence": float(item.get("confidence", 1.0) or 1.0),
            }
            label = str(item.get("label", "")).strip()
            if label:
                normalized["label"] = label
            suggestions.append(normalized)
        return suggestions