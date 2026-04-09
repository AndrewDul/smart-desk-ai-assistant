from __future__ import annotations

import os
import re
from typing import Any

from modules.shared.logging.logger import get_logger
from modules.shared.persistence.paths import APP_ROOT

from .availability_mixin import LocalLLMAvailabilityMixin
from .cleanup_mixin import LocalLLMCleanupMixin
from .prompting_mixin import LocalLLMPromptingMixin
from .runtime_mixin import LocalLLMRuntimeMixin
from .utils_mixin import LocalLLMUtilsMixin

LOGGER = get_logger(__name__)


class LocalLLMService(
    LocalLLMUtilsMixin,
    LocalLLMCleanupMixin,
    LocalLLMPromptingMixin,
    LocalLLMAvailabilityMixin,
    LocalLLMRuntimeMixin,
):
    """
    Optional local LLM adapter for NeXa.

    Design goals:
    - keep the dialogue API stable
    - support both direct llama.cpp CLI and local HTTP servers
    - stay lightweight on Raspberry Pi
    - be ready for server-style backends such as llama-server or Hailo-Ollama
    - aggressively clean unusable output before it reaches TTS
    """

    LOGGER = LOGGER

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

    _SERVER_RUNNERS = {"llama-server", "server", "ollama-server", "hailo-ollama", "openai-server"}
    _CLI_RUNNERS = {"llama-cli", "cli", "llama_cpp_cli"}

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}
        llm_cfg = self.settings.get("llm", {}) if isinstance(self.settings, dict) else {}

        self.enabled = bool(llm_cfg.get("enabled", False))
        self.runner = self._normalize_runner(str(llm_cfg.get("runner", "llama-cli")))
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

        self.server_url = str(llm_cfg.get("server_url", "http://127.0.0.1:8080")).strip()
        self.server_chat_path = (
            str(llm_cfg.get("server_chat_path", "/v1/chat/completions")).strip()
            or "/v1/chat/completions"
        )
        self.server_health_path = (
            str(llm_cfg.get("server_health_path", "/health")).strip()
            or "/health"
        )
        self.server_api_key = str(llm_cfg.get("server_api_key", "")).strip()
        self.server_model_name = str(llm_cfg.get("server_model_name", "")).strip()
        self.server_use_openai_compat = bool(llm_cfg.get("server_use_openai_compat", True))
        self.server_connect_timeout_seconds = max(
            float(llm_cfg.get("server_connect_timeout_seconds", 3.0)),
            1.0,
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