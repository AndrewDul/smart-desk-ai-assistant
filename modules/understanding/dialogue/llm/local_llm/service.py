from __future__ import annotations

import os
import re
import time
from typing import Any

from modules.shared.logging.logger import get_logger
from modules.shared.persistence.paths import APP_ROOT

from .availability_mixin import LocalLLMAvailabilityMixin
from .cleanup_mixin import LocalLLMCleanupMixin
from .models import LocalLLMBackendPolicy, LocalLLMProfile
from .prompting_mixin import LocalLLMPromptingMixin
from .runtime_mixin import LocalLLMRuntimeMixin
from .streaming_mixin import LocalLLMStreamingMixin

from .utils_mixin import LocalLLMUtilsMixin

LOGGER = get_logger(__name__)


class LocalLLMService(
    LocalLLMUtilsMixin,
    LocalLLMCleanupMixin,
    LocalLLMPromptingMixin,
    LocalLLMAvailabilityMixin,
    LocalLLMRuntimeMixin,
    LocalLLMStreamingMixin,
):
    """
    Premium local LLM adapter for NeXa.

    Production policy:
    - persistent local service is the primary runtime path
    - streaming-ready HTTP backend is the preferred inference interface
    - direct CLI execution is allowed only as an explicit fallback
    - output is aggressively cleaned before it reaches TTS
    """

    LOGGER = LOGGER

    _profile_class = LocalLLMProfile

    _ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    _BOX_DRAWING_RE = re.compile(r"[\u2500-\u257F\u2580-\u259F]")
    _MULTI_SPACE_RE = re.compile(r"\s+")
    _JSON_FENCE_RE = re.compile(
        r"^```(?:json|txt|text)?\s*|\s*```$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    _TAG_RE = re.compile(r"<\|/?(?:system|user|assistant)\|>", flags=re.IGNORECASE)
    _THINK_TAG_RE = re.compile(r"<think>.*?</think>", flags=re.IGNORECASE | re.DOTALL)

    _RUNTIME_LINE_PATTERNS = [
        re.compile(pattern, flags=re.IGNORECASE)
        for pattern in (
            r"^\s*loading model\b.*$",
            r"^\s*build\s*:\s*.*$",
            r"^\s*model\s*:\s*.*$",
            r"^\s*modalities\s*:\s*.*$",
            r"^\s*available commands\s*:?\s*$",
            r"^\s*/exit\b.*$",
            r"^\s*/regen\b.*$",
            r"^\s*/clear\b.*$",
            r"^\s*/read\b.*$",
            r"^\s*/glob\b.*$",
            r"^\s*main\s*:\s*.*$",
            r"^\s*llama[_\w\s\-:]*$",
            r"^\s*ggml[_\w\s\-:]*$",
            r"^\s*system info\b.*$",
            r"^\s*sampler seed\b.*$",
            r"^\s*prompt eval time\b.*$",
            r"^\s*eval time\b.*$",
            r"^\s*total time\b.*$",
            r"^\s*tokens per second\b.*$",
            r"^\s*common_init_from_params\b.*$",
            r"^\s*load_tensors\b.*$",
            r"^\s*llama_model_loader\b.*$",
            r"^\s*llama_context\b.*$",
            r"^\s*kv cache\b.*$",
            r"^\s*n_ctx\b.*$",
            r"^\s*n_batch\b.*$",
            r"^\s*n_ubatch\b.*$",
            r"^\s*n_threads\b.*$",
            r"^\s*chat template\b.*$",
            r"^\s*interactive\b.*$",
            r"^\s*warming up\b.*$",
            r"^\s*binary size\b.*$",
            r"^\s*version\s*:\s*.*$",
            r"^\s*seed\s*:\s*.*$",
            r"^\s*cpu\s*:\s*.*$",
            r"^\s*memory\s*:\s*.*$",
            r"^\s*slot\s+launch\b.*$",
            r"^\s*slot\s+update\b.*$",
            r"^\s*srv\s+.*$",
        )
    ]

    _BAD_FINAL_PATTERNS = [
        re.compile(pattern, flags=re.IGNORECASE)
        for pattern in (
            r"^\s*loading model\b",
            r"^\s*build\s*:",
            r"^\s*model\s*:",
            r"^\s*modalities\s*:",
            r"^\s*available commands\b",
            r"^\s*/exit\b",
            r"^\s*/regen\b",
            r"^\s*/clear\b",
            r"^\s*/read\b",
            r"^\s*/glob\b",
            r"^\s*main\s*:",
            r"^\s*llama\b",
            r"^\s*ggml\b",
            r"^\s*prompt eval time\b",
            r"^\s*eval time\b",
            r"^\s*total time\b",
            r"^\s*tokens per second\b",
            r"^\s*system info\b",
            r"^\s*slot\s+launch\b",
            r"^\s*slot\s+update\b",
        )
    ]

    _SERVER_RUNNERS = {
        "llama-server",
        "server",
        "ollama-server",
        "hailo-ollama",
        "openai-server",
    }
    _CLI_RUNNERS = {
        "llama-cli",
        "cli",
        "llama_cpp_cli",
    }

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}
        llm_cfg = self.settings.get("llm", {}) if isinstance(self.settings, dict) else {}

        self.enabled = bool(llm_cfg.get("enabled", False))
        self.runner = self._normalize_runner(str(llm_cfg.get("runner", "hailo-ollama")))
        self.command = str(llm_cfg.get("command", "llama-cli")).strip() or "llama-cli"
        self.model_path = str(llm_cfg.get("model_path", "")).strip()

        self.n_predict = max(int(llm_cfg.get("n_predict", 96)), 16)
        self.temperature = max(float(llm_cfg.get("temperature", 0.7)), 0.1)
        self.top_p = max(float(llm_cfg.get("top_p", 0.9)), 0.1)
        self.top_k = max(int(llm_cfg.get("top_k", 40)), 1)
        self.ctx_size = max(int(llm_cfg.get("ctx_size", 2048)), 512)
        self.threads = max(int(llm_cfg.get("threads", 4)), 1)
        self.timeout_seconds = max(float(llm_cfg.get("timeout_seconds", 18.0)), 4.0)
        self.repeat_penalty = max(float(llm_cfg.get("repeat_penalty", 1.1)), 1.0)
        self.max_prompt_chars = max(int(llm_cfg.get("max_prompt_chars", 2400)), 400)
        self.prefer_json = bool(llm_cfg.get("prefer_json", False))
        self._last_first_chunk_latency_ms = 0.0
        self.stream_sentence_min_chars = max(int(llm_cfg.get("stream_sentence_min_chars", 18)), 8)
        self.stream_sentence_soft_max_chars = max(
            int(llm_cfg.get("stream_sentence_soft_max_chars", 120)),
            self.stream_sentence_min_chars + 8,
        )

        self.server_url = str(llm_cfg.get("server_url", "http://127.0.0.1:8000")).strip()
        self.server_chat_path = (
            str(llm_cfg.get("server_chat_path", "/api/chat")).strip()
            or "/api/chat"
        )
        self.server_health_path = (
            str(llm_cfg.get("server_health_path", "/hailo/v1/list")).strip()
            or "/hailo/v1/list"
        )
        self.server_api_key = str(llm_cfg.get("server_api_key", "")).strip()
        self.server_model_name = str(llm_cfg.get("server_model_name", "")).strip()
        self.server_use_openai_compat = bool(llm_cfg.get("server_use_openai_compat", False))
        self.server_connect_timeout_seconds = max(
            float(llm_cfg.get("server_connect_timeout_seconds", 3.0)),
            1.0,
        )

        self.policy = LocalLLMBackendPolicy(
            require_persistent_backend=bool(llm_cfg.get("require_persistent_backend", True)),
            allow_cli_fallback=bool(llm_cfg.get("allow_cli_fallback", False)),
            stream_responses=bool(llm_cfg.get("stream_responses", True)),
            startup_warmup=bool(llm_cfg.get("startup_warmup", True)),
            startup_warmup_timeout_seconds=max(
                float(llm_cfg.get("startup_warmup_timeout_seconds", 8.0)),
                1.0,
            ),
        )

        self.project_root = APP_ROOT
        self.os = os

        self._resolved_command_path: str | None = None
        self._resolved_model_path: str | None = None
        self._availability_checked = False
        self._last_availability_error = ""

        self._server_availability_cache_seconds = 2.5
        self._server_availability_checked_at = 0.0
        self._server_availability_result = False
        self._server_availability_error = ""
        self._server_model_catalog_cache_seconds = 30.0
        self._server_model_catalog_checked_at = 0.0
        self._server_model_catalog: list[str] = []
        self._last_server_model_resolution_warning = ""
        self._server_model_catalog_cache_seconds = 30.0
        self._server_model_catalog_checked_at = 0.0
        self._server_model_catalog: list[str] = []
        self._last_server_model_resolution_warning = ""
        self._server_model_catalog_cache_seconds = 30.0
        self._server_model_catalog_checked_at = 0.0
        self._server_model_catalog: list[str] = []
        self._last_server_model_resolution_warning = ""
        self._last_generation_started_at = 0.0
        self._last_generation_finished_at = 0.0
        self._last_generation_latency_ms = 0.0
        self._last_first_chunk_latency_ms = 0.0
        self._last_generation_streamed = False
        self._last_generation_ok = False
        self._last_generation_source = ""
        self._last_generation_error = ""

        self._last_warmup_ok = False
        self._last_warmup_error = ""

        self._coerce_server_defaults()

    def _coerce_server_defaults(self) -> None:
        if self.runner not in self._SERVER_RUNNERS:
            return

        if not self.server_url:
            self.server_url = "http://127.0.0.1:8000"

        if self.runner == "hailo-ollama":
            if not self.server_health_path:
                self.server_health_path = "/hailo/v1/list"
            if not self.server_chat_path:
                self.server_chat_path = "/api/chat"

        if self.runner in {"openai-server", "llama-server", "server"}:
            if not self.server_chat_path:
                self.server_chat_path = "/v1/chat/completions"
            if not self.server_health_path:
                self.server_health_path = "/health"

    def mark_generation_started(self) -> None:
        self._last_generation_started_at = time.perf_counter()
        self._last_generation_finished_at = 0.0
        self._last_generation_latency_ms = 0.0
        self._last_first_chunk_latency_ms = 0.0
        self._last_generation_streamed = False
        self._last_generation_ok = False
        self._last_generation_source = ""
        self._last_generation_error = ""

    def mark_first_chunk_received(self, latency_ms: float) -> None:
        self._last_first_chunk_latency_ms = max(float(latency_ms), 0.0)

    def mark_generation_finished(
        self,
        *,
        ok: bool,
        source: str,
        error: str = "",
        streamed: bool = False,
    ) -> None:
        finished_at = time.perf_counter()
        self._last_generation_finished_at = finished_at
        self._last_generation_ok = bool(ok)
        self._last_generation_streamed = bool(streamed)
        self._last_generation_source = str(source or "").strip()
        self._last_generation_error = str(error or "").strip()

        if self._last_generation_started_at > 0.0:
            self._last_generation_latency_ms = (
                finished_at - self._last_generation_started_at
            ) * 1000.0
        else:
            self._last_generation_latency_ms = 0.0

    def reset_backend_cache(self) -> None:
        self._resolved_command_path = None
        self._resolved_model_path = None
        self._availability_checked = False
        self._last_availability_error = ""

        self._server_availability_checked_at = 0.0
        self._server_availability_result = False
        self._server_availability_error = ""
        self._server_model_catalog_checked_at = 0.0
        self._server_model_catalog = []
        self._last_server_model_resolution_warning = ""
        self._server_model_catalog_checked_at = 0.0
        self._server_model_catalog = []
        self._last_server_model_resolution_warning = ""
        self._server_model_catalog_checked_at = 0.0
        self._server_model_catalog = []
        self._last_server_model_resolution_warning = ""
        self._last_warmup_ok = False
        self._last_warmup_error = ""


    def warmup_backend_if_enabled(self) -> bool:
        self._last_warmup_ok = False
        self._last_warmup_error = ""

        if not self.enabled:
            self._last_warmup_ok = True
            return False

        if not self.is_available():
            self._last_warmup_error = self._last_availability_error or self._server_availability_error
            return False

        if not self.policy.startup_warmup:
            self._last_warmup_ok = True
            return True

        if self.runner not in self._SERVER_RUNNERS:
            self._last_warmup_ok = True
            return True

        base_url = self._normalized_server_base_url()
        if not base_url:
            self._last_warmup_error = "Local LLM server URL is empty."
            return False

        profile = LocalLLMProfile(
            prompt_chars=48,
            n_predict=8,
            timeout_seconds=max(1.0, float(self.policy.startup_warmup_timeout_seconds)),
            temperature=0.1,
            top_p=0.9,
            top_k=20,
            repeat_penalty=1.0,
            max_sentences=1,
            style_hint="warmup",
        )

        try:
            self._fetch_server_model_names(force_refresh=True)

            endpoints = self._server_request_candidates(
                base_url=base_url,
                system_prompt="You are NeXa. Reply with exactly one word: ready.",
                user_prompt="ready",
                profile=profile,
                stream=False,
            )
            if not endpoints:
                self._last_warmup_error = "No warmup endpoints available for local LLM service."
                return False

            response_text = self._post_json(
                url=endpoints[0]["url"],
                payload=endpoints[0]["payload"],
                timeout_seconds=profile.timeout_seconds,
            )
            extracted = self._extract_server_response_text(response_text)
            if not extracted.strip():
                self._last_warmup_error = "Warmup request returned empty text."
                return False

            self._last_warmup_ok = True
            self.LOGGER.info(
                "Local LLM warmup completed: runner=%s model=%s",
                self.runner,
                self._resolved_server_model_name(),
            )
            return True
        except Exception as error:
            self._last_warmup_error = str(error)
            self.LOGGER.warning("Local LLM warmup failed: %s", error)
            return False
        
    def warmup_backend_if_enabled(self) -> bool:
        self._last_warmup_ok = False
        self._last_warmup_error = ""

        if not self.enabled:
            self._last_warmup_ok = True
            return False

        if not self.is_available():
            self._last_warmup_error = self._last_availability_error or self._server_availability_error
            return False

        if not self.policy.startup_warmup:
            self._last_warmup_ok = True
            return True

        if self.runner not in self._SERVER_RUNNERS:
            self._last_warmup_ok = True
            return True

        base_url = self._normalized_server_base_url()
        if not base_url:
            self._last_warmup_error = "Local LLM server URL is empty."
            return False

        profile = LocalLLMProfile(
            prompt_chars=64,
            n_predict=8,
            timeout_seconds=max(1.0, float(self.policy.startup_warmup_timeout_seconds)),
            temperature=0.1,
            top_p=0.9,
            top_k=20,
            repeat_penalty=1.0,
            max_sentences=1,
            style_hint="warmup",
        )

        try:
            self._fetch_server_model_names(force_refresh=True)

            endpoints = self._server_request_candidates(
                base_url=base_url,
                system_prompt="You are NeXa. Reply with exactly one word: ready.",
                user_prompt="ready",
                profile=profile,
                stream=False,
            )
            if not endpoints:
                self._last_warmup_error = "No warmup endpoints available for local LLM service."
                return False

            response_text = self._post_json(
                url=endpoints[0]["url"],
                payload=endpoints[0]["payload"],
                timeout_seconds=profile.timeout_seconds,
            )
            extracted = self._extract_server_response_text(response_text)
            if not extracted.strip():
                self._last_warmup_error = "Warmup request returned empty text."
                return False

            self._last_warmup_ok = True
            self.LOGGER.info(
                "Local LLM warmup completed: runner=%s model=%s",
                self.runner,
                self._resolved_server_model_name(),
            )
            return True
        except Exception as error:
            self._last_warmup_error = str(error)
            self.LOGGER.warning("Local LLM warmup failed: %s", error)
            return False

    def describe_backend(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "runner": self.runner,
            "is_server_runner": self.runner in self._SERVER_RUNNERS,
            "requires_persistent_backend": self.policy.require_persistent_backend,
            "allow_cli_fallback": self.policy.allow_cli_fallback,
            "stream_responses": self.policy.stream_responses,
            "startup_warmup": self.policy.startup_warmup,
            "command": self.command,
            "model_path": self.model_path,
            "server_model_name": self._resolved_server_model_name(),
            "resolved_command_path": self._resolved_command_path,
            "resolved_model_path": self._resolved_model_path,
            "server_url": self.server_url,
            "server_chat_path": self.server_chat_path,
            "server_health_path": self.server_health_path,
            "server_use_openai_compat": self.server_use_openai_compat,
            "timeout_seconds": self.timeout_seconds,
            "ctx_size": self.ctx_size,
            "threads": self.threads,
            "last_availability_error": self._last_availability_error,
            "server_availability_error": self._server_availability_error,
            "last_generation_latency_ms": self._last_generation_latency_ms,
            "last_first_chunk_latency_ms": self._last_first_chunk_latency_ms,
            "last_generation_streamed": self._last_generation_streamed,
            "stream_sentence_min_chars": self.stream_sentence_min_chars,
            "stream_sentence_soft_max_chars": self.stream_sentence_soft_max_chars,
            "last_generation_ok": self._last_generation_ok,
            "last_generation_source": self._last_generation_source,
            "last_generation_error": self._last_generation_error,
            "last_warmup_ok": self._last_warmup_ok,
            "last_warmup_error": self._last_warmup_error,

        }

    def last_generation_snapshot(self) -> dict[str, Any]:
        return {
            "started_at": self._last_generation_started_at,
            "finished_at": self._last_generation_finished_at,
            "latency_ms": self._last_generation_latency_ms,
            "first_chunk_latency_ms": self._last_first_chunk_latency_ms,
            "streamed": self._last_generation_streamed,
            "ok": self._last_generation_ok,
            "source": self._last_generation_source,
            "error": self._last_generation_error,
        }


__all__ = ["LocalLLMService"]