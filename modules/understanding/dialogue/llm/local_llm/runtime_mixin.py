from __future__ import annotations

import json
import subprocess
import time
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
        started_at = time.perf_counter()
        self.mark_generation_started()

        try:
            prepared = self._prepare_generation_request(
                text=text,
                language=language,
                context=context,
            )
        except ValueError as error:
            self.mark_generation_finished(ok=False, source="validation", error=str(error))
            return LocalLLMReply(
                ok=False,
                text="",
                language=self._normalize_language(language),
                source="validation",
                error=str(error),
            )
        except RuntimeError as error:
            self.mark_generation_finished(ok=False, source="unavailable", error=str(error))
            return LocalLLMReply(
                ok=False,
                text="",
                language=self._normalize_language(language),
                source="unavailable",
                error=str(error),
            )

        normalized_language, user_prompt, profile, system_prompt = prepared
        streamed = False

        try:
            if self.runner in self._SERVER_RUNNERS:
                raw_output = self._run_server(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=profile,
                    stream=self.policy.stream_responses,
                )
                source_name = self.runner
                streamed = bool(self.policy.stream_responses)
            else:
                raw_output = self._run_llama_cli(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=profile,
                )
                source_name = "llama-cli"
        except subprocess.TimeoutExpired:
            error_text = f"Local LLM call exceeded {profile.timeout_seconds:.1f}s timeout."
            self.mark_generation_finished(ok=False, source="timeout", error=error_text)
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="timeout",
                error=error_text,
            )
        except TimeoutError as error:
            error_text = str(error)
            self.mark_generation_finished(ok=False, source="timeout", error=error_text)
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="timeout",
                error=error_text,
            )
        except Exception as error:
            error_text = str(error)
            self.LOGGER.warning("Local LLM runtime error: %s", error)
            self.mark_generation_finished(ok=False, source="error", error=error_text)
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="error",
                error=error_text,
            )

        cleaned = self._extract_answer(
            raw_output=raw_output,
            language=normalized_language,
            user_prompt=user_prompt,
            max_sentences=profile.max_sentences,
        )

        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self.LOGGER.info(
            "Local LLM finished: runner=%s ok=%s latency_ms=%.1f streamed=%s first_chunk_ms=%.1f",
            self.runner,
            bool(cleaned),
            elapsed_ms,
            streamed,
            float(self._last_first_chunk_latency_ms),
        )

        if not cleaned:
            error_text = "Local LLM returned empty or unusable text after cleanup."
            self.LOGGER.info("Local LLM output rejected after cleanup.")
            self.mark_generation_finished(
                ok=False,
                source="empty_output",
                error=error_text,
                streamed=streamed,
            )
            return LocalLLMReply(
                ok=False,
                text="",
                language=normalized_language,
                source="empty_output",
                error=error_text,
                raw_output=raw_output,
                streamed=streamed,
                first_chunk_latency_ms=float(self._last_first_chunk_latency_ms),
            )

        self.mark_generation_finished(
            ok=True,
            source=source_name,
            streamed=streamed,
        )
        return LocalLLMReply(
            ok=True,
            text=cleaned,
            language=normalized_language,
            source=source_name,
            raw_output=raw_output,
            streamed=streamed,
            first_chunk_latency_ms=float(self._last_first_chunk_latency_ms),
        )

    def _prepare_generation_request(
        self,
        *,
        text: str,
        language: str,
        context: dict[str, Any] | LocalLLMContext | None,
    ) -> tuple[str, str, LocalLLMProfile, str]:
        normalized_language = self._normalize_language(language)
        safe_text = str(text or "").strip()

        if not safe_text:
            raise ValueError("Empty user text.")

        if not self.enabled:
            raise ValueError("Local LLM is disabled in settings.")

        backend_snapshot = self.ensure_backend_ready(auto_recover=False)
        if not bool(backend_snapshot.get("available", False)):
            raise RuntimeError(
                str(
                    backend_snapshot.get("last_error")
                    or backend_snapshot.get("health_reason")
                    or self._last_availability_error
                    or "Local LLM backend is unavailable."
                ).strip()
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
        return normalized_language, user_prompt, profile, system_prompt

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

        cmd = self._build_llama_cli_command(
            command_path=command_path,
            model_path=model_path,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            profile=profile,
        )

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

        if completed.returncode != 0 and not stdout and not stderr:
            raise RuntimeError(f"llama-cli failed with return code {completed.returncode}.")

        if completed.returncode != 0 and stderr:
            self.LOGGER.warning(
                "llama-cli returned non-zero exit code %s: %s",
                completed.returncode,
                stderr[:400],
            )

        if stdout.strip():
            return stdout

        if stderr.strip():
            return stderr

        return "\n".join(part for part in (stdout, stderr) if part.strip()).strip()

    def _build_llama_cli_command(
        self,
        *,
        command_path: str,
        model_path: str,
        system_prompt: str,
        user_prompt: str,
        profile: LocalLLMProfile,
    ) -> list[str]:
        return [
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

    def _run_server(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        profile: LocalLLMProfile,
        stream: bool,
    ) -> str:
        if stream:
            streamed_text, _ = self._run_server_streaming(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                profile=profile,
            )
            if streamed_text.strip():
                return streamed_text

        base_url = self._normalized_server_base_url()
        if not base_url:
            raise RuntimeError("Local LLM server URL is empty.")

        endpoints = self._server_request_candidates(
            base_url=base_url,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            profile=profile,
            stream=False,
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
                self.LOGGER.debug("Local LLM server candidate failed: %s", error)
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
        stream: bool,
    ) -> list[dict[str, Any]]:
        configured_path = str(self.server_chat_path or "").strip() or "/api/chat"

        if self.runner == "hailo-ollama":
            candidate_paths = [
                configured_path,
                "/api/chat",
            ]
            if not stream:
                candidate_paths.append("/api/generate")
        else:
            candidate_paths = [configured_path]
            if stream:
                candidate_paths.extend(
                    [
                        "/api/chat",
                        "/v1/chat/completions",
                        "/api/generate",
                    ]
                )
            else:
                candidate_paths.extend(
                    [
                        "/api/chat",
                        "/api/generate",
                        "/v1/chat/completions",
                    ]
                )

        seen_urls: set[str] = set()
        candidates: list[dict[str, Any]] = []

        for path in candidate_paths:
            url = self._join_url(base_url, path)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            payload = self._payload_for_server_path(
                path=path,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                profile=profile,
                stream=stream,
            )
            candidates.append(
                {
                    "url": url,
                    "payload": payload,
                }
            )

        return candidates
    def _normalize_hailo_prompt_text(self, text: str) -> str:
        normalized = str(text or "")
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\n", " ").replace("\t", " ")
        return self._compact_whitespace(normalized)
    
    def _payload_for_server_path(
        self,
        *,
        path: str,
        system_prompt: str,
        user_prompt: str,
        profile: LocalLLMProfile,
        stream: bool,
    ) -> dict[str, Any]:
        normalized_path = "/" + str(path or "").lstrip("/")
        model_name = self._resolved_server_model_name()

        effective_system_prompt = str(system_prompt or "")
        effective_user_prompt = str(user_prompt or "")

        if self.runner == "hailo-ollama":
            effective_system_prompt = self._normalize_hailo_prompt_text(effective_system_prompt)
            effective_user_prompt = self._normalize_hailo_prompt_text(effective_user_prompt)

        if self.runner == "hailo-ollama" and normalized_path.endswith("/api/chat"):
            return {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": effective_system_prompt},
                    {"role": "user", "content": effective_user_prompt},
                ],
                "stream": stream,
            }

        if normalized_path.endswith("/api/generate"):
            prompt_text = " ".join(
                part
                for part in (
                    f"<|system|> {effective_system_prompt}",
                    f"<|user|> {effective_user_prompt}",
                    "<|assistant|>",
                )
                if str(part).strip()
            )
            return {
                "model": model_name,
                "prompt": prompt_text,
                "stream": stream,
                "options": self._ollama_options(profile),
            }

        if normalized_path.endswith("/v1/chat/completions") or self.server_use_openai_compat:
            return {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": effective_system_prompt},
                    {"role": "user", "content": effective_user_prompt},
                ],
                "temperature": profile.temperature,
                "top_p": profile.top_p,
                "max_tokens": profile.n_predict,
                "stream": stream,
            }

        return {
            "model": model_name,
            "messages": [
                {"role": "system", "content": effective_system_prompt},
                {"role": "user", "content": effective_user_prompt},
            ],
            "stream": stream,
            "options": self._ollama_options(profile),
        }

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