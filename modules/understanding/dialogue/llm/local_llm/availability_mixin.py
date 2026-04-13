from __future__ import annotations

import os
import shutil
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from modules.shared.config.settings import resolve_settings_path


class LocalLLMAvailabilityMixin:
    def is_available(self) -> bool:
        if not self.enabled:
            self._last_availability_error = "Local LLM is disabled in settings."
            self._log_availability_once(False)
            return False

        if self.runner in self._SERVER_RUNNERS:
            available = self._check_server_available()
            self._last_availability_error = self._server_availability_error
            return available

        if self.policy.require_persistent_backend and not self.policy.allow_cli_fallback:
            self._last_availability_error = (
                "Persistent LLM service is required, but the configured runner is not a service. "
                "Use hailo-ollama, ollama-server, llama-server, server, or openai-server."
            )
            self._log_availability_once(False)
            return False

        command_path = self._resolve_command_path()
        if not command_path:
            self._last_availability_error = (
                "Could not resolve local LLM command path. "
                "Check llm.command in settings."
            )
            self._log_availability_once(False)
            return False

        model_path = self._resolve_model_path()
        if not model_path:
            self._last_availability_error = (
                "Could not resolve local LLM model path. "
                "Check llm.model_path in settings."
            )
            self._log_availability_once(False)
            return False

        self._last_availability_error = ""
        self._server_availability_error = ""
        self._log_availability_once(True)
        return True

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

        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            self._server_availability_error = f"Invalid local LLM server URL: {base_url}"
            self._server_availability_result = False
            self._server_availability_checked_at = now
            self._log_availability_once(False)
            return False

        host = parsed.hostname or ""
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80

        if not self._tcp_port_open(host=host, port=port, timeout_seconds=self.server_connect_timeout_seconds):
            self._server_availability_error = (
                f"Local LLM server port is not reachable: {host}:{port}"
            )
            self._server_availability_result = False
            self._server_availability_checked_at = now
            self._log_availability_once(False)
            return False

        candidates = self._server_probe_candidates(base_url)
        last_error = ""

        for url in candidates:
            ok, error_text = self._probe_server_url(url)
            if ok:
                self._server_availability_error = ""
                self._server_availability_result = True
                self._server_availability_checked_at = now
                self._log_availability_once(True)
                return True
            if error_text:
                last_error = error_text

        self._server_availability_error = (
            last_error or f"Local LLM server is not reachable at {base_url}."
        )
        self._server_availability_result = False
        self._server_availability_checked_at = now
        self._log_availability_once(False)
        return False

    def _server_probe_candidates(self, base_url: str) -> list[str]:
        configured_health = str(self.server_health_path or "").strip() or "/health"
        configured_chat = str(self.server_chat_path or "").strip() or "/api/chat"

        candidate_paths = [
            configured_health,
            configured_chat,
            "/health",
            "/api/chat",
            "/api/generate",
            "/v1/chat/completions",
            "/hailo/v1/list",
            "/api/tags",
        ]

        seen: set[str] = set()
        urls: list[str] = []

        for path in candidate_paths:
            url = self._join_url(base_url, path)
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)

        return urls

    def _probe_server_url(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, f"Invalid probe URL: {url}"

        last_error = ""

        for method in ("GET", "HEAD"):
            request = urllib.request.Request(
                url,
                method=method,
                headers=self._server_headers(json_body=False),
            )
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.server_connect_timeout_seconds,
                ) as response:
                    status_code = int(getattr(response, "status", 200))
                    if 200 <= status_code < 500:
                        return True, ""
                    last_error = f"Unexpected HTTP status {status_code} at {url}"
            except urllib.error.HTTPError as error:
                status_code = int(error.code)
                if 200 <= status_code < 500:
                    return True, ""
                try:
                    body = error.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                last_error = f"HTTP {status_code} at {url}: {body[:180]}".strip()
            except urllib.error.URLError as error:
                last_error = f"URL error at {url}: {error}"
            except Exception as error:
                last_error = f"Probe failed at {url}: {error}"

        return False, last_error

    def _tcp_port_open(self, *, host: str, port: int, timeout_seconds: float) -> bool:
        if not host or not port:
            return False

        try:
            with socket.create_connection((host, int(port)), timeout=max(timeout_seconds, 0.5)):
                return True
        except Exception:
            return False

    def _resolve_command_path(self) -> str | None:
        if self._resolved_command_path:
            return self._resolved_command_path

        raw_command = str(self.command or "").strip() or "llama-cli"
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

            home_local = Path.home() / ".local" / "bin"
            candidates.append(home_local / expanded_command)

            candidates.append(
                self.project_root / "third_party" / "llama.cpp" / "build" / "bin" / expanded_command
            )
            candidates.append(
                self.project_root / "llama.cpp" / "build" / "bin" / expanded_command
            )
            candidates.append(
                self.project_root / "vendor" / "llama.cpp" / "build" / "bin" / expanded_command
            )

            if expanded_command != "llama-cli":
                default_name = "llama-cli"
                which_default = shutil.which(default_name)
                if which_default:
                    candidates.append(Path(which_default))
                candidates.append(home_local / default_name)
                candidates.append(
                    self.project_root / "third_party" / "llama.cpp" / "build" / "bin" / default_name
                )
                candidates.append(
                    self.project_root / "llama.cpp" / "build" / "bin" / default_name
                )
                candidates.append(
                    self.project_root / "vendor" / "llama.cpp" / "build" / "bin" / default_name
                )

        for candidate in self._deduplicate_paths(candidates):
            if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
                self._resolved_command_path = str(candidate)
                return self._resolved_command_path

        return None

    def _resolve_model_path(self) -> str | None:
        if self._resolved_model_path:
            return self._resolved_model_path

        raw_model = str(self.model_path or "").strip()
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
            candidates.append(self.project_root / "models" / Path(expanded_model).name)

        for candidate in self._deduplicate_paths(candidates):
            if candidate.exists() and candidate.is_file():
                self._resolved_model_path = str(candidate)
                return self._resolved_model_path

        return None