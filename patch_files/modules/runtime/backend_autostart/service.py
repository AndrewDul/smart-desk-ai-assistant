"""
Probe the configured LLM HTTP endpoint, and if it is not already responding,
launch a configured command to bring it up. Wait until it answers, then
return a structured result.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class BackendAutostartResult:
    attempted: bool = False
    already_running: bool = False
    launched: bool = False
    ready: bool = False
    pid: int | None = None
    elapsed_seconds: float = 0.0
    detail: str = ""
    command: list[str] = field(default_factory=list)
    health_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "already_running": self.already_running,
            "launched": self.launched,
            "ready": self.ready,
            "pid": self.pid,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "detail": self.detail,
            "command": list(self.command),
            "health_url": self.health_url,
        }


class BackendAutostartService:
    """Auto-start external HTTP services that NEXA depends on.

    Configuration shape (settings.json):

        "llm": {
            "enabled": true,
            "runner": "hailo-ollama",
            "server_url": "http://127.0.0.1:8000",
            "server_health_path": "/hailo/v1/list",
            "autostart": {
                "enabled": true,
                "launch_command": ["bash", "-lc", "ollama serve"],
                "ready_timeout_seconds": 30.0,
                "ready_poll_interval_seconds": 0.5,
                "log_path": "var/data/llm_backend_autostart.log"
            }
        }

    If the health URL already responds (200), nothing is launched and
    `already_running=True` is returned. Otherwise the launch_command is
    spawned in the background and the service polls the health URL until
    it answers or `ready_timeout_seconds` elapses.
    """

    def __init__(self, *, settings: dict[str, Any]) -> None:
        self._settings = settings or {}

    def start_llm_backend(self) -> BackendAutostartResult:
        result = BackendAutostartResult()
        result.attempted = True

        llm_cfg = dict(self._settings.get("llm", {}) or {})
        if not bool(llm_cfg.get("enabled", False)):
            result.detail = "llm disabled in config"
            return result

        autostart_cfg = dict(llm_cfg.get("autostart", {}) or {})
        if not bool(autostart_cfg.get("enabled", False)):
            result.detail = "llm.autostart disabled"
            return result

        server_url = str(llm_cfg.get("server_url", "")).strip().rstrip("/")
        if not server_url:
            result.detail = "llm.server_url missing"
            return result

        health_path = str(llm_cfg.get("server_health_path", "/")).strip() or "/"
        if not health_path.startswith("/"):
            health_path = "/" + health_path
        health_url = server_url + health_path
        result.health_url = health_url

        ready_timeout = float(autostart_cfg.get("ready_timeout_seconds", 30.0))
        poll_interval = max(0.1, float(autostart_cfg.get("ready_poll_interval_seconds", 0.5)))
        connect_timeout = max(0.5, float(autostart_cfg.get("probe_timeout_seconds", 1.5)))

        # Phase 1: is it already up?
        if self._probe(health_url, timeout=connect_timeout):
            result.already_running = True
            result.ready = True
            result.detail = f"llm backend already running at {health_url}"
            LOGGER.info("LLM backend already running. health_url=%s", health_url)
            return result

        # Phase 2: launch.
        raw_command = autostart_cfg.get("launch_command")
        command = self._normalize_command(raw_command)
        if not command:
            result.detail = "llm.autostart.launch_command missing or invalid"
            LOGGER.warning("BackendAutostartService: %s", result.detail)
            return result
        result.command = list(command)

        log_path = autostart_cfg.get("log_path") or "var/data/llm_backend_autostart.log"
        log_file = self._open_log_file(str(log_path))

        env = dict(os.environ)
        # Allow callers to inject env (e.g., HAILO_PCIE_DRIVER, OLLAMA_HOST):
        extra_env = autostart_cfg.get("environment") or {}
        if isinstance(extra_env, dict):
            for key, value in extra_env.items():
                env[str(key)] = str(value)

        try:
            proc = subprocess.Popen(  # noqa: S603 - intentional autostart
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
        except FileNotFoundError as error:
            result.detail = f"launch command not found: {error}"
            LOGGER.warning("BackendAutostartService: %s", result.detail)
            return result
        except Exception as error:
            result.detail = f"launch failed: {error}"
            LOGGER.warning("BackendAutostartService: %s", result.detail)
            return result

        result.launched = True
        result.pid = int(proc.pid)
        LOGGER.info(
            "LLM backend launched. pid=%d command=%s log=%s",
            proc.pid,
            " ".join(shlex.quote(c) for c in command),
            log_path,
        )

        # Phase 3: wait for readiness.
        deadline = time.monotonic() + ready_timeout
        started_at = time.monotonic()
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                # Process died before becoming ready.
                result.detail = (
                    f"launch process exited prematurely with code {proc.returncode}"
                )
                LOGGER.warning("BackendAutostartService: %s", result.detail)
                result.elapsed_seconds = time.monotonic() - started_at
                return result

            if self._probe(health_url, timeout=connect_timeout):
                result.ready = True
                result.elapsed_seconds = time.monotonic() - started_at
                result.detail = (
                    f"llm backend ready in {result.elapsed_seconds:.2f}s at {health_url}"
                )
                LOGGER.info("LLM backend ready. %s", result.detail)
                return result

            time.sleep(poll_interval)

        result.elapsed_seconds = time.monotonic() - started_at
        result.detail = (
            f"llm backend did not become ready within {ready_timeout:.1f}s "
            f"(health_url={health_url})"
        )
        LOGGER.warning("BackendAutostartService: %s", result.detail)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _probe(url: str, *, timeout: float) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                code = int(getattr(response, "status", 200) or 200)
                return 200 <= code < 500  # any non-server-error response means listening
        except urllib.error.HTTPError as error:
            # The server IS listening — it just doesn't like our path. That's OK.
            return 200 <= int(getattr(error, "code", 500) or 500) < 600
        except Exception:
            return False

    @staticmethod
    def _normalize_command(raw: Any) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            return shlex.split(raw)
        if isinstance(raw, (list, tuple)):
            return [str(part) for part in raw if str(part).strip()]
        return []

    @staticmethod
    def _open_log_file(path: str) -> Any:
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            return open(target, "ab")  # noqa: SIM115 - intentional file handle
        except Exception:
            return subprocess.DEVNULL


__all__ = ["BackendAutostartService", "BackendAutostartResult"]
