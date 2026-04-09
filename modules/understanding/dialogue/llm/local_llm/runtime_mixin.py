from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from typing import Any

from .models import LocalLLMContext, LocalLLMProfile, LocalLLMReply


class LocalLLMRuntimeMixin:
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
            self.LOGGER.warning("Local LLM runtime error: %s", error)
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
            self.LOGGER.info("Local LLM output rejected after cleanup.")
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

        env = self.os.environ.copy()
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