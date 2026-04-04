from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.system.utils import append_log


@dataclass(slots=True)
class LLMReply:
    ok: bool
    text: str = ""
    language: str = "en"
    source: str = "disabled"
    error: str = ""
    raw_output: str = ""


@dataclass(slots=True)
class LLMContext:
    user_name: str = ""
    assistant_name: str = "NeXa"
    conversation_topics: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    user_text: str = ""
    route_kind: str = "conversation"


@dataclass(slots=True)
class LLMGenerationProfile:
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
    - keep llama-cli compatibility
    - support llama-server as a first-class runtime option
    - keep the dialogue API stable
    - reject runtime noise and unusable output aggressively
    - stay fast and predictable on Raspberry Pi
    - prepare the service for future streaming upgrades
    """

    _ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    _BOX_DRAWING_RE = re.compile(r"[\u2500-\u257F\u2580-\u259F]")

    _RUNTIME_LINE_PATTERNS = [
        re.compile(pattern, flags=re.IGNORECASE)
        for pattern in (
            r"^\s*loading model\b.*$",
            r"^\s*build\s*:\s*.*$",
            r"^\s*model\s*:\s*.*$",
            r"^\s*modalities\s*:\s*.*$",
            r"^\s*using custom system prompt\b.*$",
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
            r"^\s*slot launch_slot_\b.*$",
            r"^\s*encode\b.*$",
            r"^\s*decode\b.*$",
            r"^\s*print_info\b.*$",
            r"^\s*n_ctx\b.*$",
            r"^\s*n_batch\b.*$",
            r"^\s*n_ubatch\b.*$",
            r"^\s*n_threads\b.*$",
            r"^\s*chat template\b.*$",
            r"^\s*interactive\b.*$",
            r"^\s*processing\b.*$",
            r"^\s*warming up\b.*$",
            r"^\s*binary size\b.*$",
            r"^\s*version\s*:\s*.*$",
            r"^\s*seed\s*:\s*.*$",
            r"^\s*cpu\s*:\s*.*$",
            r"^\s*memory\s*:\s*.*$",
        )
    ]

    _BAD_FINAL_PATTERNS = [
        re.compile(pattern, flags=re.IGNORECASE)
        for pattern in (
            r"^\s*loading model\b",
            r"^\s*build\s*:",
            r"^\s*model\s*:",
            r"^\s*modalities\s*:",
            r"^\s*using custom system prompt\b",
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
        )
    ]

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

        llm_cfg = self.settings.get("llm", {})
        self.enabled = bool(llm_cfg.get("enabled", False))
        self.runner = str(llm_cfg.get("runner", "llama-cli")).strip().lower()
        self.command = str(llm_cfg.get("command", "llama-cli")).strip()
        self.model_path = str(llm_cfg.get("model_path", "")).strip()
        self.n_predict = int(llm_cfg.get("n_predict", 96))
        self.temperature = float(llm_cfg.get("temperature", 0.7))
        self.top_p = float(llm_cfg.get("top_p", 0.9))
        self.top_k = int(llm_cfg.get("top_k", 40))
        self.ctx_size = int(llm_cfg.get("ctx_size", 2048))
        self.threads = int(llm_cfg.get("threads", 4))
        self.timeout_seconds = float(llm_cfg.get("timeout_seconds", 18.0))
        self.repeat_penalty = float(llm_cfg.get("repeat_penalty", 1.1))
        self.max_prompt_chars = int(llm_cfg.get("max_prompt_chars", 2400))
        self.prefer_json = bool(llm_cfg.get("prefer_json", False))

        self.server_url = str(llm_cfg.get("server_url", "http://127.0.0.1:8080")).strip()
        self.server_chat_path = str(llm_cfg.get("server_chat_path", "/v1/chat/completions")).strip() or "/v1/chat/completions"
        self.server_health_path = str(llm_cfg.get("server_health_path", "/health")).strip() or "/health"
        self.server_api_key = str(llm_cfg.get("server_api_key", "")).strip()
        self.server_model_name = str(llm_cfg.get("server_model_name", "")).strip()
        self.server_use_openai_compat = bool(llm_cfg.get("server_use_openai_compat", True))
        self.server_connect_timeout_seconds = float(llm_cfg.get("server_connect_timeout_seconds", 3.0))

        self.project_root = Path(__file__).resolve().parents[2]
        self._resolved_command_path: str | None = None
        self._resolved_model_path: str | None = None
        self._availability_checked = False
        self._last_availability_error = ""

    def is_available(self) -> bool:
        if not self.enabled:
            self._last_availability_error = "Local LLM is disabled in settings."
            return False

        if self.runner == "llama-server":
            return self._check_llama_server_available()

        command_path = self._resolve_command_path()
        if not command_path:
            self._last_availability_error = "Could not resolve llama.cpp command path."
            self._log_availability_once(False)
            return False

        model_path = self._resolve_model_path()
        if not model_path:
            self._last_availability_error = "Could not resolve model path."
            self._log_availability_once(False)
            return False

        self._last_availability_error = ""
        self._log_availability_once(True)
        return True

    def generate_companion_reply(
        self,
        text: str,
        language: str,
        context: LLMContext | None = None,
    ) -> LLMReply:
        normalized_language = "pl" if str(language).strip().lower() == "pl" else "en"
        safe_text = str(text or "").strip()

        if not safe_text:
            return LLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="empty",
                error="Empty user text.",
            )

        if not self.enabled:
            return LLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="disabled",
                error="Local LLM is disabled in settings.",
            )

        if not self.is_available():
            return LLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="unavailable",
                error=self._last_availability_error or "Local LLM backend is unavailable.",
            )

        llm_context = context or LLMContext(user_text=safe_text)
        profile = self._build_generation_profile(
            language=normalized_language,
            context=llm_context,
            user_prompt=safe_text,
        )
        system_prompt = self._build_system_prompt(normalized_language, llm_context, profile)
        user_prompt = safe_text[: profile.prompt_chars].strip()

        try:
            if self.runner == "llama-server":
                raw_output = self._run_llama_server(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=profile,
                )
                source_name = "llama-server"
            else:
                raw_output = self._run_llama_cli(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=profile,
                )
                source_name = "llama-cli"

        except subprocess.TimeoutExpired:
            return LLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="timeout",
                error=f"llama.cpp call exceeded {profile.timeout_seconds:.1f}s timeout.",
            )
        except TimeoutError as error:
            return LLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="timeout",
                error=str(error),
            )
        except Exception as error:
            append_log(f"Local LLM runtime error: {error}")
            return LLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="error",
                error=str(error),
            )

        cleaned = self._extract_answer(
            raw_output,
            normalized_language,
            user_prompt,
            max_sentences=profile.max_sentences,
        )

        if not cleaned:
            append_log("Local LLM output rejected after cleanup. Falling back to template reply.")
            return LLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="empty_output",
                error="Local LLM returned empty or unusable text after cleanup.",
                raw_output=raw_output,
            )

        return LLMReply(
            ok=True,
            text=cleaned,
            language=normalized_language,
            source=source_name,
            raw_output=raw_output,
        )

    def _build_generation_profile(
        self,
        *,
        language: str,
        context: LLMContext,
        user_prompt: str,
    ) -> LLMGenerationProfile:
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
            temperature = min(temperature, 0.6)
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
            temperature = min(temperature, 0.5)
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

        return LLMGenerationProfile(
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

    def _check_llama_server_available(self) -> bool:
        base_url = self._normalized_server_base_url()
        if not base_url:
            self._last_availability_error = "llama-server base URL is empty."
            self._log_availability_once(False)
            return False

        health_url = self._join_url(base_url, self.server_health_path)

        try:
            request = urllib.request.Request(
                health_url,
                method="GET",
                headers=self._server_headers(json_body=False),
            )
            with urllib.request.urlopen(request, timeout=self.server_connect_timeout_seconds) as response:
                status_code = int(getattr(response, "status", 200))
                if 200 <= status_code < 300:
                    self._last_availability_error = ""
                    self._log_availability_once(True)
                    return True
        except Exception:
            pass

        chat_url = self._join_url(base_url, self.server_chat_path)

        try:
            request = urllib.request.Request(
                chat_url,
                method="HEAD",
                headers=self._server_headers(json_body=False),
            )
            with urllib.request.urlopen(request, timeout=self.server_connect_timeout_seconds) as response:
                status_code = int(getattr(response, "status", 200))
                if 200 <= status_code < 500:
                    self._last_availability_error = ""
                    self._log_availability_once(True)
                    return True
        except urllib.error.HTTPError as error:
            if 200 <= int(error.code) < 500:
                self._last_availability_error = ""
                self._log_availability_once(True)
                return True
        except Exception as error:
            self._last_availability_error = f"llama-server is not reachable at {base_url}: {error}"
            self._log_availability_once(False)
            return False

        self._last_availability_error = f"llama-server is not reachable at {base_url}"
        self._log_availability_once(False)
        return False

    def _resolve_command_path(self) -> str | None:
        if self._resolved_command_path:
            return self._resolved_command_path

        raw_command = self.command.strip() or "llama-cli"
        expanded_command = os.path.expanduser(raw_command)

        candidates: list[Path] = []

        raw_path = Path(expanded_command)
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
            candidates.append(self.project_root / "llama.cpp" / "build" / "bin" / expanded_command)
            candidates.append(Path.cwd() / "llama.cpp" / "build" / "bin" / expanded_command)

            if expanded_command != "llama-cli":
                which_default = shutil.which("llama-cli")
                if which_default:
                    candidates.append(Path(which_default))
                candidates.append(Path.home() / ".local" / "bin" / "llama-cli")
                candidates.append(self.project_root / "llama.cpp" / "build" / "bin" / "llama-cli")
                candidates.append(Path.cwd() / "llama.cpp" / "build" / "bin" / "llama-cli")

        checked: list[str] = []
        for candidate in self._deduplicate_paths(candidates):
            checked.append(str(candidate))
            if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
                self._resolved_command_path = str(candidate)
                return self._resolved_command_path

        append_log(f"Local LLM command not found. Checked: {checked}")
        return None

    def _resolve_model_path(self) -> str | None:
        if self._resolved_model_path:
            return self._resolved_model_path

        raw_model = self.model_path.strip()
        if not raw_model:
            append_log("Local LLM model_path is empty in settings.")
            return None

        expanded_model = os.path.expanduser(raw_model)
        raw_path = Path(expanded_model)

        candidates: list[Path] = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.append((Path.cwd() / expanded_model).resolve())
            candidates.append((self.project_root / expanded_model).resolve())

        checked: list[str] = []
        for candidate in self._deduplicate_paths(candidates):
            checked.append(str(candidate))
            if candidate.exists() and candidate.is_file():
                self._resolved_model_path = str(candidate)
                return self._resolved_model_path

        append_log(f"Local LLM model not found. Checked: {checked}")
        return None

    def _run_llama_cli(self, system_prompt: str, user_prompt: str, profile: LLMGenerationProfile) -> str:
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

        if completed.returncode != 0:
            message = combined_output.strip() or f"llama.cpp exited with code {completed.returncode}"
            raise RuntimeError(message)

        return combined_output

    def _run_llama_server(
        self,
        system_prompt: str,
        user_prompt: str,
        profile: LLMGenerationProfile,
    ) -> str:
        base_url = self._normalized_server_base_url()
        if not base_url:
            raise RuntimeError("llama-server base URL is empty.")

        if self.server_use_openai_compat:
            return self._run_llama_server_openai_chat(base_url, system_prompt, user_prompt, profile)

        return self._run_llama_server_completion(base_url, system_prompt, user_prompt, profile)

    def _run_llama_server_openai_chat(
        self,
        base_url: str,
        system_prompt: str,
        user_prompt: str,
        profile: LLMGenerationProfile,
    ) -> str:
        url = self._join_url(base_url, self.server_chat_path)

        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": profile.temperature,
            "top_p": profile.top_p,
            "max_tokens": profile.n_predict,
            "stream": False,
        }

        if self.server_model_name:
            payload["model"] = self.server_model_name

        if profile.repeat_penalty > 0:
            payload["repeat_penalty"] = profile.repeat_penalty

        if profile.top_k > 0:
            payload["top_k"] = profile.top_k

        response_text = self._post_json(url, payload, timeout_seconds=profile.timeout_seconds)
        parsed = self._safe_json_loads(response_text)

        if isinstance(parsed, dict):
            choices = parsed.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str) and content.strip():
                            return content.strip()

                    text = first_choice.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()

        return response_text

    def _run_llama_server_completion(
        self,
        base_url: str,
        system_prompt: str,
        user_prompt: str,
        profile: LLMGenerationProfile,
    ) -> str:
        url = self._join_url(base_url, "/completion")

        prompt = (
            "<|im_start|>system\n"
            f"{system_prompt}\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"{user_prompt}\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        payload: dict[str, Any] = {
            "prompt": prompt,
            "n_predict": profile.n_predict,
            "temperature": profile.temperature,
            "top_p": profile.top_p,
            "stream": False,
        }

        if profile.repeat_penalty > 0:
            payload["repeat_penalty"] = profile.repeat_penalty

        if profile.top_k > 0:
            payload["top_k"] = profile.top_k

        response_text = self._post_json(url, payload, timeout_seconds=profile.timeout_seconds)
        parsed = self._safe_json_loads(response_text)

        if isinstance(parsed, dict):
            content = parsed.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

            text = parsed.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

        return response_text

    def _post_json(self, url: str, payload: dict[str, Any], *, timeout_seconds: float) -> str:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers=self._server_headers(json_body=True),
        )

        timeout = max(float(timeout_seconds), self.server_connect_timeout_seconds)

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_bytes = response.read()
                return self._decode_output_bytes(response_bytes)
        except urllib.error.HTTPError as error:
            body = self._decode_output_bytes(error.read())
            raise RuntimeError(
                f"llama-server HTTP {error.code} at {url}. Body: {body[:500]}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not connect to llama-server at {url}: {error}") from error
        except TimeoutError as error:
            raise TimeoutError(
                f"llama-server request exceeded timeout of {timeout:.1f}s."
            ) from error

    def _build_system_prompt(
        self,
        language: str,
        context: LLMContext,
        profile: LLMGenerationProfile,
    ) -> str:
        assistant_name = context.assistant_name.strip() or "NeXa"
        user_name = context.user_name.strip() or "the user"
        route_kind = context.route_kind.strip() or "conversation"
        topic_text = ", ".join(context.conversation_topics) if context.conversation_topics else "none"
        actions_text = ", ".join(context.suggested_actions) if context.suggested_actions else "none"

        internal_context = {
            "assistant_name": assistant_name,
            "user_name": user_name,
            "route_kind": route_kind,
            "conversation_topics": context.conversation_topics,
            "suggested_actions": context.suggested_actions,
            "style_hint": profile.style_hint,
            "max_sentences": profile.max_sentences,
        }

        if self.prefer_json:
            context_block = json.dumps(internal_context, ensure_ascii=False)
        else:
            context_block = (
                f"assistant_name={assistant_name}; "
                f"user_name={user_name}; "
                f"route_kind={route_kind}; "
                f"conversation_topics={topic_text}; "
                f"suggested_actions={actions_text}; "
                f"style_hint={profile.style_hint}; "
                f"max_sentences={profile.max_sentences}"
            )

        if language == "pl":
            return (
                f"Jesteś {assistant_name}, spokojnym i pomocnym lokalnym towarzyszem biurkowym działającym offline na Raspberry Pi 5. "
                "Zawsze odpowiadaj wyłącznie po polsku. "
                "Odpowiadaj naturalnie, krótko i praktycznie. "
                "Najpierw daj sensowną odpowiedź, bez długiego wstępu. "
                "Jeśli użytkownik zadaje zwykłe pytanie wiedzy, rozumowania albo proste pytanie matematyczne, odpowiedz bezpośrednio. "
                "Jeśli użytkownik brzmi na zmęczonego, przytłoczonego albo rozproszonego, odpowiedz empatycznie najpierw. "
                "Możesz delikatnie zasugerować focus, break, timer albo reminder, ale nie udawaj wykonania narzędzia. "
                "Nie mów, że jesteś modelem AI. "
                "Nie pokazuj technicznych logów, statusów ładowania, informacji o modelu ani komunikatów runtime. "
                "Nie powtarzaj pytania użytkownika. "
                f"Zwykle odpowiadaj maksymalnie w {profile.max_sentences} zdaniach. "
                "Nie używaj list punktowanych, markdownu ani cudzysłowów wokół całej odpowiedzi. "
                f"Kontekst wewnętrzny: {context_block}"
            )

        return (
            f"You are {assistant_name}, a calm and helpful local desk companion running offline on Raspberry Pi 5. "
            "Always reply only in English. "
            "Reply naturally, briefly, and practically. "
            "Give the useful answer first, without a long preamble. "
            "If the user asks a normal knowledge, reasoning, or simple math question, answer directly. "
            "If the user sounds tired, overwhelmed, or distracted, respond empathetically first. "
            "You may gently suggest focus mode, break mode, a timer, or a reminder, but do not pretend you already executed a tool. "
            "Do not say you are an AI model. "
            "Do not show technical logs, loading messages, model status, command help, or runtime messages. "
            "Do not repeat the user's question. "
            f"Usually answer in no more than {profile.max_sentences} sentences. "
            "Do not use bullet lists, markdown, or wrapping quotation marks around the whole answer. "
            f"Internal context: {context_block}"
        )

    def _extract_answer(
        self,
        raw_output: str,
        language: str,
        user_prompt: str,
        *,
        max_sentences: int,
    ) -> str:
        text = str(raw_output or "").strip()
        if not text:
            return ""

        text = self._strip_ansi(text)
        text = self._strip_box_drawing(text)

        lines = [self._collapse_whitespace(line) for line in text.splitlines()]
        kept_lines = [line for line in lines if self._keep_output_line(line)]

        if not kept_lines:
            return ""

        text = "\n".join(kept_lines).strip()
        text = self._drop_preamble_before_user_prompt(text, user_prompt)
        text = self._drop_prompt_echo(text, user_prompt)

        markers = [
            "assistant\n",
            "Assistant:",
            "<|assistant|>",
            "<|im_start|>assistant",
        ]
        for marker in markers:
            if marker in text:
                text = text.split(marker, 1)[-1].strip()

        if "<|im_end|>" in text:
            text = text.split("<|im_end|>", 1)[0].strip()

        if "<|im_start|>" in text:
            text = text.split("<|im_start|>", 1)[0].strip()

        text = text.replace("</s>", " ").replace("<s>", " ").strip()
        text = self._remove_inline_runtime_fragments(text)
        text = self._cleanup_formatting(text)
        text = self._collapse_whitespace(text)
        text = self._trim_unwanted_prefixes(text, language)
        text = self._limit_sentences(text, max_sentences=max_sentences)
        text = text.strip()

        if not text:
            return ""

        if any(pattern.match(text) for pattern in self._BAD_FINAL_PATTERNS):
            return ""

        if self._looks_like_metadata_blob(text):
            return ""

        return text

    def _cleanup_formatting(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^[\-•*]+\s*", "", cleaned)
        cleaned = re.sub(r"\s*\n\s*", " ", cleaned)
        cleaned = cleaned.strip(" \"'`")
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned

    def _keep_output_line(self, line: str) -> bool:
        cleaned = line.strip()
        if not cleaned:
            return False

        if self._looks_like_runtime_line(cleaned):
            return False

        if self._looks_like_box_progress(cleaned):
            return False

        if cleaned.lower() in {"assistant", "assistant:", "user", "user:"}:
            return False

        return True

    def _looks_like_runtime_line(self, line: str) -> bool:
        lowered = line.lower().strip()

        for pattern in self._RUNTIME_LINE_PATTERNS:
            if pattern.match(lowered):
                return True

        metadata_hits = 0
        for token in [
            "build :",
            "model :",
            "modalities :",
            "available commands",
            "using custom system prompt",
            "n_ctx",
            "n_batch",
            "llama",
            "ggml",
            "prompt eval",
            "eval time",
        ]:
            if token in lowered:
                metadata_hits += 1

        if metadata_hits >= 2:
            return True

        return False

    def _looks_like_box_progress(self, text: str) -> bool:
        if not text:
            return False

        total = len(text)
        box_count = len(self._BOX_DRAWING_RE.findall(text))
        if total > 0 and (box_count / total) >= 0.15:
            return True

        weird_blocks = sum(1 for ch in text if ch in {"▄", "█", "▀", "▌", "▐", "▖", "▗", "▘", "▝"})
        if total > 0 and (weird_blocks / total) >= 0.12:
            return True

        return False

    def _looks_like_metadata_blob(self, text: str) -> bool:
        lowered = text.lower()

        bad_tokens = [
            "build :",
            "model :",
            "modalities :",
            "available commands",
            "using custom system prompt",
            "loading model",
            "prompt eval time",
            "eval time",
            "total time",
            "tokens per second",
            "ggml",
            "llama",
        ]
        hits = sum(1 for token in bad_tokens if token in lowered)
        return hits >= 2

    def _drop_preamble_before_user_prompt(self, text: str, user_prompt: str) -> str:
        prompt = self._collapse_whitespace(str(user_prompt or "").strip())
        if not prompt:
            return text

        candidates = [
            f"> {prompt}",
            f"> {prompt.rstrip('.')}",
            prompt,
        ]

        chosen_index = -1
        chosen_length = 0

        haystack = text
        haystack_lower = haystack.lower()

        for candidate in candidates:
            candidate_clean = candidate.strip()
            if not candidate_clean:
                continue

            idx = haystack_lower.rfind(candidate_clean.lower())
            if idx > chosen_index:
                chosen_index = idx
                chosen_length = len(candidate_clean)

        if chosen_index >= 0:
            after = haystack[chosen_index + chosen_length :].strip()
            if after:
                return after

        return text

    def _drop_prompt_echo(self, text: str, user_prompt: str) -> str:
        cleaned = text.strip()
        prompt = self._collapse_whitespace(str(user_prompt or "").strip())

        if not prompt:
            return cleaned

        prompt_variants = {
            prompt,
            prompt.rstrip("."),
            f"> {prompt}",
            f"> {prompt.rstrip('.')}",
        }

        for variant in sorted(prompt_variants, key=len, reverse=True):
            if cleaned.lower().startswith(variant.lower()):
                cleaned = cleaned[len(variant):].strip(" \n\t.:>-")
                break

        return cleaned

    def _remove_inline_runtime_fragments(self, text: str) -> str:
        cleaned = text

        inline_patterns = [
            r"\bloading model\b.*",
            r"\bbuild\s*:\s*[^\n]+",
            r"\bmodel\s*:\s*[^\n]+",
            r"\bmodalities\s*:\s*[^\n]+",
            r"\busing custom system prompt\b[^\n]*",
            r"\bavailable commands\s*:?[^\\n]*",
            r"/exit[^\n]*",
            r"/regen[^\n]*",
            r"/clear[^\n]*",
            r"/read[^\n]*",
            r"/glob[^\n]*",
            r"\bprompt eval time\b[^\n]*",
            r"\beval time\b[^\n]*",
            r"\btotal time\b[^\n]*",
            r"\btokens per second\b[^\n]*",
        ]

        for pattern in inline_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

        cleaned = self._strip_box_drawing(cleaned)
        cleaned = self._collapse_whitespace(cleaned)
        return cleaned

    def _log_availability_once(self, ok: bool) -> None:
        if self._availability_checked:
            return

        self._availability_checked = True

        if ok:
            if self.runner == "llama-server":
                append_log(
                    "Local LLM available: "
                    f"runner=llama-server, url={self._normalized_server_base_url()}"
                )
            else:
                append_log(
                    "Local LLM available: "
                    f"command={self._resolved_command_path}, model={self._resolved_model_path}"
                )
        else:
            append_log(f"Local LLM unavailable: {self._last_availability_error}")

    def _server_headers(self, *, json_body: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}

        if json_body:
            headers["Content-Type"] = "application/json; charset=utf-8"

        if self.server_api_key:
            headers["Authorization"] = f"Bearer {self.server_api_key}"

        return headers

    def _normalized_server_base_url(self) -> str:
        return self.server_url.rstrip("/")

    @staticmethod
    def _join_url(base_url: str, path: str) -> str:
        clean_base = str(base_url or "").rstrip("/")
        clean_path = str(path or "").strip()

        if not clean_path:
            return clean_base

        if clean_path.startswith("http://") or clean_path.startswith("https://"):
            return clean_path

        if not clean_path.startswith("/"):
            clean_path = "/" + clean_path

        return clean_base + clean_path

    @staticmethod
    def _safe_json_loads(text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    @staticmethod
    def _deduplicate_paths(paths: list[Path]) -> list[Path]:
        result: list[Path] = []
        seen: set[str] = set()

        for path in paths:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            result.append(path)

        return result

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        return " ".join(text.split())

    @classmethod
    def _strip_ansi(cls, text: str) -> str:
        return cls._ANSI_RE.sub("", text)

    @classmethod
    def _strip_box_drawing(cls, text: str) -> str:
        return cls._BOX_DRAWING_RE.sub(" ", text)

    @staticmethod
    def _decode_output_bytes(data: bytes | None) -> str:
        if not data:
            return ""

        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return data.decode(encoding, errors="ignore")
            except Exception:
                continue

        return ""

    @staticmethod
    def _limit_sentences(text: str, max_sentences: int = 3) -> str:
        if not text:
            return ""

        sentence_breaks = []
        for index, char in enumerate(text):
            if char in ".!?":
                sentence_breaks.append(index)

        if len(sentence_breaks) < max_sentences:
            return text

        cut_index = sentence_breaks[max_sentences - 1] + 1
        return text[:cut_index].strip()

    @staticmethod
    def _trim_unwanted_prefixes(text: str, language: str) -> str:
        candidates = [
            "Sure,",
            "Of course,",
            "Certainly,",
            "Okay,",
            "Jasne,",
            "Oczywiście,",
            "Pewnie,",
            "Dobrze,",
            "And,",
            "And",
        ]

        cleaned = text.strip()
        for prefix in candidates:
            if cleaned.startswith(prefix) and len(cleaned) > len(prefix) + 8:
                cleaned = cleaned[len(prefix):].strip()
                break

        if language == "pl":
            cleaned = re.sub(r"^(to\s+znaczy[, ]+)", "", cleaned, flags=re.IGNORECASE).strip()
        else:
            cleaned = re.sub(r"^(that means[, ]+)", "", cleaned, flags=re.IGNORECASE).strip()

        return cleaned