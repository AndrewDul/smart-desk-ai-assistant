from __future__ import annotations

import os
import shutil
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
                self._server_availability_error = (
                    f"Local LLM server is not reachable at {base_url}: {error}"
                )

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
                with urllib.request.urlopen(
                    request,
                    timeout=self.server_connect_timeout_seconds,
                ) as response:
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
            candidates.append(
                self.project_root / "third_party" / "llama.cpp" / "build" / "bin" / expanded_command
            )
            candidates.append(
                self.project_root / "llama.cpp" / "build" / "bin" / expanded_command
            )

            if expanded_command != "llama-cli":
                which_default = shutil.which("llama-cli")
                if which_default:
                    candidates.append(Path(which_default))
                candidates.append(Path.home() / ".local" / "bin" / "llama-cli")
                candidates.append(
                    self.project_root / "third_party" / "llama.cpp" / "build" / "bin" / "llama-cli"
                )
                candidates.append(
                    self.project_root / "llama.cpp" / "build" / "bin" / "llama-cli"
                )

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