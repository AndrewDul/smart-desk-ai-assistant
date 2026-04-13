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

        # Prefer extracting structured content when available.
        structured_text = self._extract_json_text(cleaned)
        if structured_text:
            cleaned = structured_text
        elif self.prefer_json:
            return ""

        cleaned = self._strip_runtime_lines(cleaned)
        cleaned = self._remove_echo(user_prompt, cleaned)
        cleaned = self._strip_chat_labels(cleaned)
        cleaned = self._strip_code_fences(cleaned)
        cleaned = self._strip_inline_artifacts(cleaned)
        cleaned = self._strip_trailing_noise(cleaned)
        cleaned = self._drop_empty_or_noise_lines(cleaned)
        cleaned = self._compact_whitespace(cleaned)

        if not cleaned:
            return ""

        if self._looks_like_runtime_noise(cleaned):
            return ""

        cleaned = self._deduplicate_repeated_sentences(cleaned)
        cleaned = self._limit_sentences(cleaned, max_sentences=max_sentences)
        cleaned = self._strip_incomplete_tail(cleaned)
        cleaned = self._ensure_terminal_punctuation(cleaned, language=language)

        if not cleaned:
            return ""

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

        seen: set[str] = set()
        for raw_json in possible_payloads:
            if raw_json in seen:
                continue
            seen.add(raw_json)

            try:
                payload = json.loads(raw_json)
            except Exception:
                continue

            extracted = self._extract_text_from_json_payload(payload)
            if extracted:
                return extracted

        return ""

    def _extract_text_from_json_payload(
        self,
        payload: Any,
        *,
        preserve_token_spacing: bool = False,
    ) -> str:
        if isinstance(payload, str):
            return payload if preserve_token_spacing else payload.strip()

        if isinstance(payload, dict):
            for key in (
                "text",
                "reply",
                "response",
                "content",
                "spoken_text",
                "message",
                "output_text",
                "output",
            ):
                value = payload.get(key)
                extracted = self._extract_text_from_json_payload(
                    value,
                    preserve_token_spacing=preserve_token_spacing,
                )
                if extracted:
                    return extracted

            choices = payload.get("choices")
            if isinstance(choices, list):
                for item in choices:
                    extracted = self._extract_text_from_json_payload(
                        item,
                        preserve_token_spacing=preserve_token_spacing,
                    )
                    if extracted:
                        return extracted

            message = payload.get("message")
            extracted = self._extract_text_from_json_payload(
                message,
                preserve_token_spacing=preserve_token_spacing,
            )
            if extracted:
                return extracted

            delta = payload.get("delta")
            extracted = self._extract_text_from_json_payload(
                delta,
                preserve_token_spacing=preserve_token_spacing,
            )
            if extracted:
                return extracted

            content = payload.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    extracted = self._extract_text_from_json_payload(
                        item,
                        preserve_token_spacing=preserve_token_spacing,
                    )
                    if extracted:
                        parts.append(extracted)

                if preserve_token_spacing:
                    joined = "".join(part for part in parts if part)
                else:
                    joined = " ".join(part.strip() for part in parts if part.strip()).strip()

                if joined:
                    return joined

        if isinstance(payload, list):
            parts: list[str] = []
            for item in payload:
                extracted = self._extract_text_from_json_payload(
                    item,
                    preserve_token_spacing=preserve_token_spacing,
                )
                if extracted:
                    parts.append(extracted)

            if preserve_token_spacing:
                joined = "".join(part for part in parts if part)
            else:
                joined = " ".join(part.strip() for part in parts if part.strip()).strip()

            if joined:
                return joined

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

        single_quoted_prompt = f"'{clean_user_prompt}'".lower()
        if normalized_text.startswith(single_quoted_prompt):
            trimmed = clean_text[len(clean_user_prompt) + 2 :].lstrip(" :,-")
            return trimmed.strip()

        return text

    def _strip_chat_labels(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""

        prefixes = (
            "assistant:",
            "assistant >",
            "assistant -",
            "assistant reply:",
            "assistant response:",
            "nexa:",
            "nexa >",
            "nexa -",
            "response:",
            "answer:",
            "reply:",
            "final answer:",
            "odpowiedz:",
            "odpowiedź:",
            "asystent:",
        )

        changed = True
        while changed:
            changed = False
            lowered = cleaned.lower()
            for prefix in prefixes:
                if lowered.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
                    changed = True
                    break

        return cleaned

    def _strip_code_fences(self, text: str) -> str:
        return self._JSON_FENCE_RE.sub("", str(text or "")).strip()

    def _strip_inline_artifacts(self, text: str) -> str:
        cleaned = str(text or "").strip()

        # Remove obvious leftover assistant markers inside the text.
        cleaned = re.sub(
            r"\b(?:assistant|response|reply|answer|nexa)\s*[:>\-]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Remove duplicated whitespace again after inline cleanup.
        cleaned = self._compact_whitespace(cleaned)

        return cleaned.strip()

    def _strip_trailing_noise(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        while lines and any(pattern.match(lines[-1]) for pattern in self._BAD_FINAL_PATTERNS):
            lines.pop()
        return "\n".join(lines).strip()

    def _drop_empty_or_noise_lines(self, text: str) -> str:
        kept: list[str] = []
        for raw_line in str(text or "").splitlines():
            line = self._compact_whitespace(raw_line)
            if not line:
                continue
            if self._looks_like_runtime_noise(line):
                continue
            kept.append(line)
        return "\n".join(kept).strip()

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
            "none",
        }:
            return True

        return any(pattern.match(lowered) for pattern in self._BAD_FINAL_PATTERNS)

    def _deduplicate_repeated_sentences(self, text: str) -> str:
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        parts = [part.strip() for part in parts if part.strip()]
        if not parts:
            return text.strip()

        kept: list[str] = []
        seen_normalized: set[str] = set()

        for part in parts:
            normalized = self._compact_whitespace(part).lower()
            if normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            kept.append(part)

        return " ".join(kept).strip()

    def _limit_sentences(self, text: str, *, max_sentences: int) -> str:
        if max_sentences <= 0:
            return text.strip()

        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        parts = [part.strip() for part in parts if part.strip()]
        if not parts:
            return text.strip()

        limited = " ".join(parts[:max_sentences]).strip()
        return limited or text.strip()

    def _strip_incomplete_tail(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""

        # If we already have sentence punctuation, cut to the last solid ending.
        last_terminal = max(cleaned.rfind("."), cleaned.rfind("!"), cleaned.rfind("?"))
        if last_terminal >= 0:
            candidate = cleaned[: last_terminal + 1].strip()
            if candidate:
                return candidate

        # Otherwise remove very obvious cut-off tails.
        trailing_bad_chars = {":", ";", ",", "-", "—", "(", "[", "{", "/"}
        while cleaned and cleaned[-1] in trailing_bad_chars:
            cleaned = cleaned[:-1].rstrip()

        return cleaned

    def _ensure_terminal_punctuation(self, text: str, *, language: str) -> str:
        del language

        cleaned = text.strip()
        if not cleaned:
            return ""

        if cleaned[-1] in ".!?":
            return cleaned

        return f"{cleaned}."