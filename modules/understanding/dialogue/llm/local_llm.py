from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.shared.config.settings import resolve_settings_path
from modules.shared.logging.logger import get_logger
from modules.shared.persistence.paths import APP_ROOT

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class LocalLLMReply:
    ok: bool
    text: str = ""
    language: str = "en"
    source: str = "disabled"
    error: str = ""
    raw_output: str = ""


@dataclass(slots=True)
class LocalLLMContext:
    user_name: str = ""
    assistant_name: str = "NeXa"
    conversation_topics: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    user_text: str = ""
    route_kind: str = "conversation"
    recent_context: str = ""
    user_profile: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LocalLLMProfile:
    prompt_chars: int
    n_predict: int
    timeout_seconds: float
    temperature: float
    top_p: float
    top_k: int
    repeat_penalty: float
    max_sentences: int
    style_hint: str


class LocalLLMService:
    """
    Optional local LLM adapter for NeXa.

    Design goals:
    - keep the dialogue API stable
    - support both direct llama.cpp CLI and local HTTP servers
    - stay lightweight on Raspberry Pi
    - be ready for server-style backends such as llama-server or Hailo-Ollama
    - aggressively clean unusable output before it reaches TTS
    """

    _ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    _BOX_DRAWING_RE = re.compile(r"[\u2500-\u257F\u2580-\u259F]")
    _MULTI_SPACE_RE = re.compile(r"\s+")
    _JSON_FENCE_RE = re.compile(r"^```(?:json|txt|text)?\s*|\s*```$", flags=re.IGNORECASE | re.MULTILINE)
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
        self.server_chat_path = str(llm_cfg.get("server_chat_path", "/v1/chat/completions")).strip() or "/v1/chat/completions"
        self.server_health_path = str(llm_cfg.get("server_health_path", "/health")).strip() or "/health"
        self.server_api_key = str(llm_cfg.get("server_api_key", "")).strip()
        self.server_model_name = str(llm_cfg.get("server_model_name", "")).strip()
        self.server_use_openai_compat = bool(llm_cfg.get("server_use_openai_compat", True))
        self.server_connect_timeout_seconds = max(float(llm_cfg.get("server_connect_timeout_seconds", 3.0)), 1.0)

        self.project_root = APP_ROOT
        self._resolved_command_path: str | None = None
        self._resolved_model_path: str | None = None
        self._availability_checked = False
        self._last_availability_error = ""

        self._server_availability_cache_seconds = 2.5
        self._server_availability_checked_at = 0.0
        self._server_availability_result = False
        self._server_availability_error = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        if not self.enabled:
            self._last_availability_error = "Local LLM is disabled in settings."
            return False

        if self.runner in self._SERVER_RUNNERS:
            available = self._check_server_available()
            self._last_availability_error = self._server_availability_error
            return available

        command_path = self._resolve_command_path()
        if not command_path:
            self._last_availability_error = "Could not resolve llama.cpp command path."
            self._log_availability_once(False)
            return False

        model_path = self._resolve_model_path()
        if not model_path:
            self._last_availability_error = "Could not resolve local LLM model path."
            self._log_availability_once(False)
            return False

        self._last_availability_error = ""
        self._log_availability_once(True)
        return True

    def generate_companion_reply(
        self,
        text: str,
        language: str,
        context: dict[str, Any] | LocalLLMContext | None = None,
    ) -> LocalLLMReply:
        normalized_language = self._normalize_language(language)
        safe_text = str(text or "").strip()

        if not safe_text:
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="empty",
                error="Empty user text.",
            )

        if not self.enabled:
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="disabled",
                error="Local LLM is disabled in settings.",
            )

        if not self.is_available():
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="unavailable",
                error=self._last_availability_error or "Local LLM backend is unavailable.",
            )

        llm_context = self._coerce_context(context, user_text=safe_text)
        profile = self._build_generation_profile(
            language=normalized_language,
            context=llm_context,
            user_prompt=safe_text,
        )
        system_prompt = self._build_system_prompt(
            language=normalized_language,
            context=llm_context,
            profile=profile,
        )
        user_prompt = safe_text[: profile.prompt_chars].strip()

        try:
            if self.runner in self._SERVER_RUNNERS:
                raw_output = self._run_server(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=profile,
                )
                source_name = self.runner
            else:
                raw_output = self._run_llama_cli(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=profile,
                )
                source_name = "llama-cli"
        except subprocess.TimeoutExpired:
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="timeout",
                error=f"Local LLM call exceeded {profile.timeout_seconds:.1f}s timeout.",
            )
        except TimeoutError as error:
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="timeout",
                error=str(error),
            )
        except Exception as error:
            LOGGER.warning("Local LLM runtime error: %s", error)
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="error",
                error=str(error),
            )

        cleaned = self._extract_answer(
            raw_output=raw_output,
            language=normalized_language,
            user_prompt=user_prompt,
            max_sentences=profile.max_sentences,
        )

        if not cleaned:
            LOGGER.info("Local LLM output rejected after cleanup.")
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="empty_output",
                error="Local LLM returned empty or unusable text after cleanup.",
                raw_output=raw_output,
            )

        return LocalLLMReply(
            ok=True,
            text=cleaned,
            language=normalized_language,
            source=source_name,
            raw_output=raw_output,
        )

    # ------------------------------------------------------------------
    # Prompting
    # ------------------------------------------------------------------

    def _coerce_context(
        self,
        context: dict[str, Any] | LocalLLMContext | None,
        *,
        user_text: str,
    ) -> LocalLLMContext:
        if isinstance(context, LocalLLMContext):
            return context

        if isinstance(context, dict):
            user_profile = dict(context.get("user_profile", {}) or {})
            return LocalLLMContext(
                user_name=str(user_profile.get("name", "") or context.get("user_name", "")),
                assistant_name=str(user_profile.get("assistant_name", "NeXa") or "NeXa"),
                conversation_topics=list(context.get("topics", context.get("conversation_topics", [])) or []),
                suggested_actions=list(context.get("suggested_actions", []) or []),
                user_text=user_text,
                route_kind=str(context.get("route_kind", "conversation") or "conversation"),
                recent_context=str(context.get("recent_context", "") or ""),
                user_profile=user_profile,
            )

        return LocalLLMContext(user_text=user_text)

    def _build_generation_profile(
        self,
        *,
        language: str,
        context: LocalLLMContext,
        user_prompt: str,
    ) -> LocalLLMProfile:
        topics = set(context.conversation_topics)
        route_kind = str(context.route_kind or "conversation").strip().lower()
        prompt_length = len(str(user_prompt or ""))

        prompt_chars = self.max_prompt_chars
        n_predict = self.n_predict
        timeout_seconds = self.timeout_seconds
        temperature = self.temperature
        top_p = self.top_p
        top_k = self.top_k
        repeat_penalty = self.repeat_penalty
        max_sentences = 3
        style_hint = "balanced"

        support_topics = {"low_energy", "focus_struggle", "overwhelmed", "encouragement", "small_talk"}
        if topics & support_topics:
            n_predict = min(n_predict, 72)
            timeout_seconds = min(timeout_seconds, 10.0)
            temperature = min(temperature, 0.58)
            top_p = min(top_p, 0.9)
            max_sentences = 2
            style_hint = "warm_brief"

        if "knowledge_query" in topics:
            n_predict = max(n_predict, 112)
            timeout_seconds = max(timeout_seconds, 20.0)
            temperature = min(temperature, 0.55)
            max_sentences = 3
            style_hint = "direct_explainer"

        if route_kind == "unclear":
            n_predict = min(n_predict, 56)
            timeout_seconds = min(timeout_seconds, 8.5)
            temperature = min(temperature, 0.45)
            max_sentences = 2
            style_hint = "clarify_brief"

        if route_kind == "mixed":
            n_predict = min(n_predict, 80)
            timeout_seconds = min(timeout_seconds, 10.0)
            max_sentences = 2
            style_hint = "practical_bridge"

        if prompt_length > 900:
            prompt_chars = min(prompt_chars, 1400)
            n_predict = min(n_predict, 96)

        if self.runner in self._SERVER_RUNNERS:
            timeout_seconds = max(timeout_seconds, 6.0)

        return LocalLLMProfile(
            prompt_chars=max(300, int(prompt_chars)),
            n_predict=max(24, int(n_predict)),
            timeout_seconds=max(4.0, float(timeout_seconds)),
            temperature=max(0.1, float(temperature)),
            top_p=max(0.1, float(top_p)),
            top_k=max(1, int(top_k)),
            repeat_penalty=max(1.0, float(repeat_penalty)),
            max_sentences=max(1, int(max_sentences)),
            style_hint=style_hint,
        )

    def _build_system_prompt(
        self,
        *,
        language: str,
        context: LocalLLMContext,
        profile: LocalLLMProfile,
    ) -> str:
        assistant_name = context.assistant_name or "NeXa"
        user_name = context.user_name or ""
        recent_context = str(context.recent_context or "").strip()
        suggested_actions = ", ".join(context.suggested_actions[:4]) if context.suggested_actions else ""
        topics = ", ".join(context.conversation_topics[:6]) if context.conversation_topics else ""
        style_hint = profile.style_hint

        if language == "pl":
            lines = [
                f"Jesteś {assistant_name}, premium asystentem biurkowym działającym lokalnie.",
                "Odpowiadaj po polsku.",
                "Mów naturalnie, krótko i konkretnie.",
                "Nie opisuj swojego procesu myślenia.",
                "Nie wypisuj punktów, chyba że użytkownik wyraźnie o to prosi.",
                "Nie twórz długich wstępów ani zakończeń.",
                "Brzmij pomocnie, spokojnie i profesjonalnie.",
                "Jeżeli pytanie jest niejasne, poproś o doprecyzowanie w jednym krótkim zdaniu.",
                f"Styl odpowiedzi: {style_hint}.",
                f"Maksymalnie {profile.max_sentences} zdania.",
            ]
            if user_name:
                lines.append(f"Użytkownik ma na imię {user_name}.")
            if topics:
                lines.append(f"Tematy rozmowy: {topics}.")
            if suggested_actions:
                lines.append(f"Sugerowane działania: {suggested_actions}.")
            if recent_context:
                lines.append(f"Ostatni kontekst rozmowy: {recent_context}")
            lines.append("Zwróć wyłącznie końcową odpowiedź dla użytkownika.")
            return "\n".join(lines)

        lines = [
            f"You are {assistant_name}, a premium local desk assistant.",
            "Reply in English.",
            "Be natural, concise, and practical.",
            "Do not describe hidden reasoning.",
            "Avoid bullets unless the user explicitly asks for them.",
            "Do not produce long intros or long wrap-ups.",
            "Sound calm, helpful, and professional.",
            "If the request is unclear, ask for clarification in one short sentence.",
            f"Reply style: {style_hint}.",
            f"Use at most {profile.max_sentences} sentences.",
        ]
        if user_name:
            lines.append(f"The user's name is {user_name}.")
        if topics:
            lines.append(f"Conversation topics: {topics}.")
        if suggested_actions:
            lines.append(f"Suggested actions: {suggested_actions}.")
        if recent_context:
            lines.append(f"Recent conversation context: {recent_context}")
        lines.append("Return only the final user-facing answer.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Availability and path resolution
    # ------------------------------------------------------------------

    def _check_server_available(self) -> bool:
        now = time.monotonic()
        if (now - self._server_availability_checked_at) <= self._server_availability_cache_seconds:
            return self._server_availability_result

        base_url = self._normalized_server_base_url()
        if not base_url:
            self._server_availability_error = "Local LLM server URL is empty."
            self._server_availability_result = False
            self._server_availability_checked_at = now
            self._log_availability_once(False)
            return False

        candidates = [
            self._join_url(base_url, self.server_health_path),
            self._join_url(base_url, self.server_chat_path),
        ]
        if self.server_chat_path != "/api/generate":
            candidates.append(self._join_url(base_url, "/api/generate"))
        if self.server_chat_path != "/api/chat":
            candidates.append(self._join_url(base_url, "/api/chat"))
        if self.server_chat_path != "/v1/chat/completions":
            candidates.append(self._join_url(base_url, "/v1/chat/completions"))

        seen: set[str] = set()
        for url in candidates:
            if url in seen:
                continue
            seen.add(url)

            try:
                if self._probe_server_url(url):
                    self._server_availability_error = ""
                    self._server_availability_result = True
                    self._server_availability_checked_at = now
                    self._log_availability_once(True)
                    return True
            except Exception as error:
                self._server_availability_error = f"Local LLM server is not reachable at {base_url}: {error}"

        if not self._server_availability_error:
            self._server_availability_error = f"Local LLM server is not reachable at {base_url}."
        self._server_availability_result = False
        self._server_availability_checked_at = now
        self._log_availability_once(False)
        return False

    def _probe_server_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        for method in ("GET", "HEAD"):
            request = urllib.request.Request(
                url,
                method=method,
                headers=self._server_headers(json_body=False),
            )
            try:
                with urllib.request.urlopen(request, timeout=self.server_connect_timeout_seconds) as response:
                    status_code = int(getattr(response, "status", 200))
                    if 200 <= status_code < 500:
                        return True
            except urllib.error.HTTPError as error:
                if 200 <= int(error.code) < 500:
                    return True
            except Exception:
                continue

        return False

    def _resolve_command_path(self) -> str | None:
        if self._resolved_command_path:
            return self._resolved_command_path

        raw_command = self.command.strip() or "llama-cli"
        expanded_command = os.path.expanduser(raw_command)
        raw_path = Path(expanded_command)

        candidates: list[Path] = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            if "/" in expanded_command or "\\" in expanded_command:
                candidates.append((Path.cwd() / expanded_command).resolve())
                candidates.append((self.project_root / expanded_command).resolve())

            which_match = shutil.which(expanded_command)
            if which_match:
                candidates.append(Path(which_match))

            candidates.append(Path.home() / ".local" / "bin" / expanded_command)
            candidates.append(self.project_root / "third_party" / "llama.cpp" / "build" / "bin" / expanded_command)
            candidates.append(self.project_root / "llama.cpp" / "build" / "bin" / expanded_command)

            if expanded_command != "llama-cli":
                which_default = shutil.which("llama-cli")
                if which_default:
                    candidates.append(Path(which_default))
                candidates.append(Path.home() / ".local" / "bin" / "llama-cli")
                candidates.append(self.project_root / "third_party" / "llama.cpp" / "build" / "bin" / "llama-cli")
                candidates.append(self.project_root / "llama.cpp" / "build" / "bin" / "llama-cli")

        for candidate in self._deduplicate_paths(candidates):
            if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
                self._resolved_command_path = str(candidate)
                return self._resolved_command_path

        return None

    def _resolve_model_path(self) -> str | None:
        if self._resolved_model_path:
            return self._resolved_model_path

        raw_model = self.model_path.strip()
        if not raw_model:
            return None

        resolved = resolve_settings_path(raw_model)
        if resolved is not None and resolved.exists() and resolved.is_file():
            self._resolved_model_path = str(resolved)
            return self._resolved_model_path

        expanded_model = os.path.expanduser(raw_model)
        raw_path = Path(expanded_model)

        candidates: list[Path] = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.append((Path.cwd() / expanded_model).resolve())
            candidates.append((self.project_root / expanded_model).resolve())
            candidates.append(self.project_root / "models" / expanded_model)

        for candidate in self._deduplicate_paths(candidates):
            if candidate.exists() and candidate.is_file():
                self._resolved_model_path = str(candidate)
                return self._resolved_model_path

        return None

    # ------------------------------------------------------------------
    # Runtime execution
    # ------------------------------------------------------------------

    def _run_llama_cli(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        profile: LocalLLMProfile,
    ) -> str:
        command_path = self._resolve_command_path()
        model_path = self._resolve_model_path()

        if not command_path:
            raise RuntimeError("Local LLM command path could not be resolved.")
        if not model_path:
            raise RuntimeError("Local LLM model path could not be resolved.")

        cmd = [
            command_path,
            "-m",
            model_path,
            "-c",
            str(self.ctx_size),
            "-n",
            str(profile.n_predict),
            "--temp",
            str(profile.temperature),
            "--top-k",
            str(profile.top_k),
            "--top-p",
            str(profile.top_p),
            "--repeat-penalty",
            str(profile.repeat_penalty),
            "-t",
            str(self.threads),
            "--simple-io",
            "--no-display-prompt",
            "--no-show-timings",
            "--no-warmup",
            "--log-colors",
            "off",
            "-cnv",
            "-st",
            "--chat-template",
            "chatml",
            "-sys",
            system_prompt,
            "-p",
            user_prompt,
        ]

        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        env["TERM"] = "dumb"
        env["LLAMA_LOG_COLORS"] = "off"
        env["CLICOLOR"] = "0"

        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            timeout=profile.timeout_seconds,
            check=False,
            cwd=str(self.project_root),
            env=env,
        )

        stdout = self._decode_output_bytes(completed.stdout)
        stderr = self._decode_output_bytes(completed.stderr)
        combined_output = "\n".join(part for part in [stdout, stderr] if part.strip())

        if completed.returncode != 0 and not combined_output.strip():
            raise RuntimeError(f"llama-cli failed with return code {completed.returncode}.")

        return combined_output

    def _run_server(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        profile: LocalLLMProfile,
    ) -> str:
        base_url = self._normalized_server_base_url()
        if not base_url:
            raise RuntimeError("Local LLM server URL is empty.")

        endpoints = self._server_request_candidates(
            base_url=base_url,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            profile=profile,
        )

        last_error: Exception | None = None
        for endpoint in endpoints:
            try:
                response_text = self._post_json(
                    url=endpoint["url"],
                    payload=endpoint["payload"],
                    timeout_seconds=profile.timeout_seconds,
                )
                extracted = self._extract_server_response_text(response_text)
                if extracted.strip():
                    return extracted
            except Exception as error:
                last_error = error
                continue

        if last_error is None:
            raise RuntimeError("Local LLM server returned no usable response.")
        raise RuntimeError(str(last_error))

    def _server_request_candidates(
        self,
        *,
        base_url: str,
        system_prompt: str,
        user_prompt: str,
        profile: LocalLLMProfile,
    ) -> list[dict[str, Any]]:
        openai_url = self._join_url(base_url, self.server_chat_path or "/v1/chat/completions")
        openai_payload = {
            "model": self.server_model_name or "local-model",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": profile.temperature,
            "top_p": profile.top_p,
            "max_tokens": profile.n_predict,
            "stream": False,
        }

        ollama_chat_url = self._join_url(base_url, "/api/chat")
        ollama_chat_payload = {
            "model": self.server_model_name or "local-model",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": self._ollama_options(profile),
        }

        ollama_generate_url = self._join_url(base_url, "/api/generate")
        ollama_generate_payload = {
            "model": self.server_model_name or "local-model",
            "prompt": f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}\n<|assistant|>\n",
            "stream": False,
            "options": self._ollama_options(profile),
        }

        if self.server_use_openai_compat:
            return [
                {"url": openai_url, "payload": openai_payload},
                {"url": ollama_chat_url, "payload": ollama_chat_payload},
                {"url": ollama_generate_url, "payload": ollama_generate_payload},
            ]

        return [
            {"url": ollama_chat_url, "payload": ollama_chat_payload},
            {"url": ollama_generate_url, "payload": ollama_generate_payload},
            {"url": openai_url, "payload": openai_payload},
        ]

    def _ollama_options(self, profile: LocalLLMProfile) -> dict[str, Any]:
        return {
            "num_predict": profile.n_predict,
            "temperature": profile.temperature,
            "top_p": profile.top_p,
            "top_k": profile.top_k,
            "repeat_penalty": profile.repeat_penalty,
            "num_ctx": self.ctx_size,
            "num_thread": self.threads,
        }

    def _post_json(self, *, url: str, payload: dict[str, Any], timeout_seconds: float) -> str:
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._server_headers(json_body=True),
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Local LLM server HTTP {error.code}: {body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Local LLM server request failed: {error}") from error

    # ------------------------------------------------------------------
    # Output cleanup
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Server helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _log_availability_once(self, available: bool) -> None:
        if self._availability_checked:
            return
        self._availability_checked = True

        if available:
            LOGGER.info("Local LLM available: runner=%s", self.runner)
        else:
            LOGGER.warning("Local LLM unavailable: %s", self._last_availability_error or self._server_availability_error)

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


__all__ = [
    "LocalLLMContext",
    "LocalLLMProfile",
    "LocalLLMReply",
    "LocalLLMService",
]