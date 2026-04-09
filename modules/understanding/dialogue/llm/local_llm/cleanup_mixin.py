from __future__ import annotations

import json
import re
from typing import Any


class LocalLLMCleanupMixin:
    def _extract_answer(
        self,
        *,
        raw_output: str,
        language: str,
        user_prompt: str,
        max_sentences: int,
    ) -> str:
        cleaned = self._decode_and_clean(raw_output)
        if not cleaned:
            return ""

        if self.prefer_json:
            extracted_json = self._extract_json_text(cleaned)
            if extracted_json:
                cleaned = extracted_json

        cleaned = self._extract_json_text(cleaned) or cleaned
        cleaned = self._strip_runtime_lines(cleaned)
        cleaned = self._remove_echo(user_prompt, cleaned)
        cleaned = self._strip_chat_labels(cleaned)
        cleaned = self._strip_code_fences(cleaned)
        cleaned = self._strip_trailing_noise(cleaned)
        cleaned = self._compact_whitespace(cleaned)

        if not cleaned:
            return ""

        if self._looks_like_runtime_noise(cleaned):
            return ""

        cleaned = self._limit_sentences(cleaned, max_sentences=max_sentences)
        cleaned = self._ensure_terminal_punctuation(cleaned, language=language)

        if self._looks_like_runtime_noise(cleaned):
            return ""

        return cleaned.strip()

    def _decode_and_clean(self, raw_output: str) -> str:
        text = str(raw_output or "")
        text = self._ANSI_RE.sub("", text)
        text = self._BOX_DRAWING_RE.sub("", text)
        text = self._THINK_TAG_RE.sub("", text)
        text = self._TAG_RE.sub("", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text.strip()

    def _extract_json_text(self, text: str) -> str:
        cleaned = self._strip_code_fences(text)

        possible_payloads: list[str] = []
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            possible_payloads.append(cleaned[start : end + 1])

        if cleaned.startswith("{") and cleaned.endswith("}"):
            possible_payloads.append(cleaned)

        for raw_json in possible_payloads:
            try:
                payload = json.loads(raw_json)
            except Exception:
                continue

            extracted = self._extract_text_from_json_payload(payload)
            if extracted:
                return extracted

        return ""

    def _extract_text_from_json_payload(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()

        if isinstance(payload, dict):
            for key in (
                "text",
                "reply",
                "response",
                "content",
                "spoken_text",
                "message",
                "output_text",
            ):
                value = payload.get(key)
                extracted = self._extract_text_from_json_payload(value)
                if extracted:
                    return extracted

            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                for item in choices:
                    extracted = self._extract_text_from_json_payload(item)
                    if extracted:
                        return extracted

        if isinstance(payload, list):
            for item in payload:
                extracted = self._extract_text_from_json_payload(item)
                if extracted:
                    return extracted

        return ""

    def _strip_runtime_lines(self, text: str) -> str:
        kept_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(pattern.match(line) for pattern in self._RUNTIME_LINE_PATTERNS):
                continue
            kept_lines.append(line)
        return "\n".join(kept_lines).strip()

    def _remove_echo(self, user_prompt: str, text: str) -> str:
        clean_user_prompt = self._compact_whitespace(user_prompt)
        clean_text = self._compact_whitespace(text)

        if not clean_user_prompt or not clean_text:
            return text

        normalized_user = clean_user_prompt.lower()
        normalized_text = clean_text.lower()

        if normalized_text.startswith(normalized_user):
            trimmed = clean_text[len(clean_user_prompt):].lstrip(" :,-")
            return trimmed.strip()

        quoted_prompt = f"\"{clean_user_prompt}\"".lower()
        if normalized_text.startswith(quoted_prompt):
            trimmed = clean_text[len(clean_user_prompt) + 2 :].lstrip(" :,-")
            return trimmed.strip()

        return text

    def _strip_chat_labels(self, text: str) -> str:
        cleaned = text.strip()

        prefixes = (
            "assistant:",
            "assistant >",
            "assistant -",
            "nexa:",
            "nexa >",
            "nexa -",
            "response:",
            "answer:",
            "reply:",
            "final answer:",
            "assistant response:",
        )

        lowered = cleaned.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                return cleaned[len(prefix):].strip()

        return cleaned

    def _strip_code_fences(self, text: str) -> str:
        return self._JSON_FENCE_RE.sub("", str(text or "")).strip()

    def _strip_trailing_noise(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        while lines and any(pattern.match(lines[-1]) for pattern in self._BAD_FINAL_PATTERNS):
            lines.pop()
        return "\n".join(lines).strip()

    def _looks_like_runtime_noise(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True

        lowered = stripped.lower()
        if lowered in {
            "assistant",
            "nexa",
            "response",
            "answer",
            "reply",
            "loading model",
            "system info",
            "true",
            "false",
            "null",
        }:
            return True

        return any(pattern.match(lowered) for pattern in self._BAD_FINAL_PATTERNS)

    def _limit_sentences(self, text: str, *, max_sentences: int) -> str:
        if max_sentences <= 0:
            return text.strip()

        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        parts = [part.strip() for part in parts if part.strip()]
        if not parts:
            return text.strip()

        limited = " ".join(parts[:max_sentences]).strip()
        return limited or text.strip()

    def _ensure_terminal_punctuation(self, text: str, *, language: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""

        if cleaned[-1] in ".!?":
            return cleaned

        return f"{cleaned}."