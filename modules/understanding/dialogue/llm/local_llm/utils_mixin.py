from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class LocalLLMUtilsMixin:
    def _extract_server_response_text(self, response_text: str) -> str:
        raw_text = str(response_text or "").strip()
        if not raw_text:
            return ""

        direct_text = self._extract_text_from_possible_json(raw_text)
        if direct_text:
            return direct_text

        collected_parts: list[str] = []
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue

            extracted = self._extract_text_from_possible_json(line)
            if extracted:
                collected_parts.append(extracted)

        if collected_parts:
            return self._compact_whitespace("".join(collected_parts))

        return raw_text

    def _extract_text_from_possible_json(self, text: str) -> str:
        try:
            payload = json.loads(text)
        except Exception:
            return ""

        extracted = self._extract_text_from_json_payload(payload)
        if extracted:
            return extracted

        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

            response_value = payload.get("response")
            if isinstance(response_value, str) and response_value.strip():
                return response_value.strip()

            delta = payload.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

        return ""

    def _normalized_server_base_url(self) -> str:
        return str(self.server_url or "").strip().rstrip("/")

    def _fetch_server_model_names(self, *, force_refresh: bool = False) -> list[str]:
        cache_seconds = max(float(getattr(self, "_server_model_catalog_cache_seconds", 30.0) or 30.0), 1.0)
        now = time.monotonic()

        if (
            not force_refresh
            and getattr(self, "_server_model_catalog", None)
            and (now - float(getattr(self, "_server_model_catalog_checked_at", 0.0))) <= cache_seconds
        ):
            return list(self._server_model_catalog)

        base_url = self._normalized_server_base_url()
        if not base_url:
            return list(getattr(self, "_server_model_catalog", []))

        configured_health = str(getattr(self, "server_health_path", "") or "").strip()
        candidate_paths = [configured_health, "/hailo/v1/list", "/api/tags"]

        seen_urls: set[str] = set()
        urls: list[str] = []

        for path in candidate_paths:
            if not path:
                continue
            url = self._join_url(base_url, path)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            urls.append(url)

        discovered: list[str] = []

        for url in urls:
            request = urllib.request.Request(
                url,
                method="GET",
                headers=self._server_headers(json_body=False),
            )
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=max(float(getattr(self, "server_connect_timeout_seconds", 2.0) or 2.0), 1.0),
                ) as response:
                    payload_text = response.read().decode("utf-8", errors="replace")
            except Exception:
                continue

            try:
                payload = json.loads(payload_text)
            except Exception:
                continue

            raw_models = payload.get("models")
            if not isinstance(raw_models, list):
                continue

            names: list[str] = []
            for item in raw_models:
                if isinstance(item, str):
                    name = item.strip()
                    if name:
                        names.append(name)
                    continue
                if isinstance(item, dict):
                    name = str(item.get("name", "") or item.get("model", "")).strip()
                    if name:
                        names.append(name)

            if names:
                discovered = names
                break

        self._server_model_catalog = discovered
        self._server_model_catalog_checked_at = now
        return list(discovered)

    def _resolved_server_model_name(self) -> str:
        explicit = str(self.server_model_name or "").strip()
        raw_model_path = str(self.model_path or "").strip()
        model_path_stem = Path(raw_model_path).stem if raw_model_path else ""

        available_models = self._fetch_server_model_names()
        if not available_models:
            if explicit:
                return explicit
            if model_path_stem:
                return model_path_stem or "local-model"
            return "local-model"

        available_set = {name.strip() for name in available_models if str(name).strip()}
        lowered_map = {name.lower(): name for name in available_set}

        if explicit and explicit in available_set:
            return explicit

        if explicit and explicit.lower() in lowered_map:
            return lowered_map[explicit.lower()]

        preferred: list[str] = []

        if explicit:
            preferred.append(explicit)

            explicit_lower = explicit.lower()
            if "qwen2.5" in explicit_lower:
                preferred.extend(["qwen2.5:1.5b", "qwen2:1.5b", "llama3.2:1b"])
            elif "qwen2" in explicit_lower:
                preferred.extend(["qwen2:1.5b", "qwen2.5:1.5b", "llama3.2:1b"])
            elif "llama" in explicit_lower:
                preferred.extend(["llama3.2:1b", "qwen2:1.5b"])
            elif "deepseek" in explicit_lower:
                preferred.extend(["deepseek_r1:1.5b", "qwen2:1.5b"])

        if model_path_stem:
            stem_lower = model_path_stem.lower()
            if "qwen2.5" in stem_lower:
                preferred.extend(["qwen2.5:1.5b", "qwen2:1.5b"])
            elif "qwen2" in stem_lower:
                preferred.extend(["qwen2:1.5b", "qwen2.5:1.5b"])
            elif "llama" in stem_lower:
                preferred.append("llama3.2:1b")

        preferred.extend(
            [
                "qwen2:1.5b",
                "qwen2.5:1.5b",
                "llama3.2:1b",
                "deepseek_r1:1.5b",
                "qwen2.5-coder:1.5b",
            ]
        )

        seen_candidates: set[str] = set()
        for candidate in preferred:
            normalized_candidate = str(candidate or "").strip()
            if not normalized_candidate or normalized_candidate in seen_candidates:
                continue
            seen_candidates.add(normalized_candidate)

            if normalized_candidate in available_set:
                resolved = normalized_candidate
            else:
                resolved = lowered_map.get(normalized_candidate.lower(), "")

            if resolved:
                warning_key = f"{explicit}->{resolved}"
                if explicit and explicit != resolved and getattr(self, "_last_server_model_resolution_warning", "") != warning_key:
                    self.LOGGER.warning(
                        "Configured server model '%s' is unavailable. Falling back to installed model '%s'.",
                        explicit,
                        resolved,
                    )
                    self._last_server_model_resolution_warning = warning_key
                return resolved

        first_available = next(iter(sorted(available_set)), "local-model")
        if explicit and explicit != first_available:
            warning_key = f"{explicit}->{first_available}"
            if getattr(self, "_last_server_model_resolution_warning", "") != warning_key:
                self.LOGGER.warning(
                    "Configured server model '%s' is unavailable. Falling back to first available installed model '%s'.",
                    explicit,
                    first_available,
                )
                self._last_server_model_resolution_warning = warning_key
        return first_available

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
            self.LOGGER.info(
                "Local LLM available: runner=%s, server=%s",
                self.runner,
                self._normalized_server_base_url() if self.runner in self._SERVER_RUNNERS else "-",
            )
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
        normalized = str(runner or "hailo-ollama").strip().lower()
        if normalized in cls._SERVER_RUNNERS:
            return normalized
        if normalized in cls._CLI_RUNNERS:
            return "llama-cli"
        return normalized or "hailo-ollama"

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        return "pl" if normalized.startswith("pl") else "en"