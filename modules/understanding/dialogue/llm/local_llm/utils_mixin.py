from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LocalLLMUtilsMixin:
    def _extract_server_response_text(self, response_text: str) -> str:
        try:
            payload = json.loads(response_text)
        except Exception:
            return response_text

        extracted = self._extract_text_from_json_payload(payload)
        if extracted:
            return extracted

        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content

            response_value = payload.get("response")
            if isinstance(response_value, str):
                return response_value

        return response_text

    def _normalized_server_base_url(self) -> str:
        return str(self.server_url or "").strip().rstrip("/")

    @staticmethod
    def _join_url(base_url: str, path: str) -> str:
        cleaned_path = "/" + str(path or "").lstrip("/")
        return base_url.rstrip("/") + cleaned_path

    def _server_headers(self, *, json_body: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
        }
        if json_body:
            headers["Content-Type"] = "application/json"

        if self.server_api_key:
            headers["Authorization"] = f"Bearer {self.server_api_key}"

        return headers

    def _log_availability_once(self, available: bool) -> None:
        if self._availability_checked:
            return
        self._availability_checked = True

        if available:
            self.LOGGER.info("Local LLM available: runner=%s", self.runner)
        else:
            self.LOGGER.warning(
                "Local LLM unavailable: %s",
                self._last_availability_error or self._server_availability_error,
            )

    @staticmethod
    def _deduplicate_paths(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for path in paths:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    @staticmethod
    def _decode_output_bytes(raw: bytes | None) -> str:
        if raw is None:
            return ""
        return raw.decode("utf-8", errors="replace").strip()

    @classmethod
    def _compact_whitespace(cls, text: str) -> str:
        return cls._MULTI_SPACE_RE.sub(" ", str(text or "").strip())

    @classmethod
    def _normalize_runner(cls, runner: str | None) -> str:
        normalized = str(runner or "llama-cli").strip().lower()
        if normalized in cls._SERVER_RUNNERS:
            return normalized
        if normalized in cls._CLI_RUNNERS:
            return "llama-cli"
        return normalized or "llama-cli"

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        return "pl" if normalized.startswith("pl") else "en"