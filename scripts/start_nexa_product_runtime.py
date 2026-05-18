#!/usr/bin/env python3
"""Start the full local NeXa product runtime stack."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence


DEFAULT_LLM_HEALTH_URL = "http://127.0.0.1:8000/v1/models"
DEFAULT_SHUTDOWN_TIMEOUT = 8.0
DEFAULT_LLM_STARTUP_TIMEOUT = 45.0


HealthProbe = Callable[[str, float], bool]
TcpProbe = Callable[[str, int, float], bool]
PopenFactory = Callable[..., subprocess.Popen]


@dataclass(frozen=True, slots=True)
class LLMConfig:
    enabled: bool
    command: str
    model_path: str
    server_url: str
    server_health_path: str
    ctx_size: int | None = None
    threads: int | None = None

    @property
    def health_url(self) -> str:
        return _join_url(self.server_url, self.server_health_path)


@dataclass(frozen=True, slots=True)
class LauncherConfig:
    repo_root: Path
    python_executable: Path | str
    llm: LLMConfig
    visual_shell_command: tuple[str, ...]
    nexa_command: tuple[str, ...]
    visual_shell_host: str = "127.0.0.1"
    visual_shell_port: int = 8765
    no_llm: bool = False
    no_visual_shell: bool = False
    llm_required: bool = False
    shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT
    llm_startup_timeout: float = DEFAULT_LLM_STARTUP_TIMEOUT
    dry_run: bool = False


@dataclass(slots=True)
class ManagedProcess:
    name: str
    command: tuple[str, ...]
    process: subprocess.Popen
    owned: bool = True
    process_group_id: int | None = None
    _reader_threads: list[threading.Thread] = field(default_factory=list)

    def start_output_threads(self) -> None:
        for stream_name, stream in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=_stream_output,
                args=(self.name, stream_name, stream),
                name=f"nexa-launcher-{self.name}-{stream_name}",
                daemon=True,
            )
            thread.start()
            self._reader_threads.append(thread)

    def poll(self) -> int | None:
        return self.process.poll()


class ProductRuntimeLauncher:
    def __init__(
        self,
        config: LauncherConfig,
        *,
        popen_factory: PopenFactory = subprocess.Popen,
        health_probe: HealthProbe = None,
        tcp_probe: TcpProbe = None,
    ) -> None:
        self.config = config
        self._popen_factory = popen_factory
        self._health_probe = health_probe or probe_http_health
        self._tcp_probe = tcp_probe or probe_tcp_port
        self._children: list[ManagedProcess] = []
        self._shutdown_requested = threading.Event()
        self._signal_installed = False
        self._reused_existing_llm = False

    def dry_run_plan(self) -> list[dict[str, object]]:
        plan: list[dict[str, object]] = []
        if self._should_use_llm():
            plan.append(
                {
                    "name": "llm",
                    "command": list(self._build_llm_command()),
                    "health_url": self.config.llm.health_url,
                    "required": self._llm_is_required(),
                }
            )
        if not self.config.no_visual_shell:
            plan.append(
                {
                    "name": "visual-shell",
                    "command": list(self.config.visual_shell_command),
                    "tcp": f"{self.config.visual_shell_host}:{self.config.visual_shell_port}",
                }
            )
        plan.append({"name": "nexa", "command": list(self.config.nexa_command)})
        return plan

    def run(self) -> int:
        if self.config.dry_run:
            print(json.dumps({"action": "dry_run", "plan": self.dry_run_plan()}, indent=2))
            return 0

        self._install_signal_handlers()
        try:
            if not self._ensure_llm_backend():
                return 2
            if not self.config.no_visual_shell:
                self._ensure_visual_shell()
            nexa = self._start_child("nexa", self.config.nexa_command)
            return self._watch(nexa)
        except KeyboardInterrupt:
            print("[launcher] shutdown requested by KeyboardInterrupt")
            return 130
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._shutdown_requested.is_set():
            return
        print("[launcher] shutdown requested")
        self._shutdown_requested.set()
        for child in reversed(self._children):
            self._terminate_child(child)
        for child in reversed(self._children):
            if child.owned:
                self._wait_reader_threads(child)
        if self._reused_existing_llm:
            print("[launcher] reused existing llm, not stopping it")

    def _install_signal_handlers(self) -> None:
        if self._signal_installed:
            return

        def _handle_signal(signum: int, _frame: object) -> None:
            print(f"[launcher] shutdown requested by signal {signum}")
            self.shutdown()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        self._signal_installed = True

    def _watch(self, nexa: ManagedProcess) -> int:
        while not self._shutdown_requested.is_set():
            nexa_code = nexa.poll()
            if nexa_code is not None:
                print(f"[launcher] NeXa runtime exited with code {nexa_code}; shutting down stack")
                return int(nexa_code)

            for child in self._children:
                if child is nexa:
                    continue
                code = child.poll()
                if code is not None:
                    if child.name == "visual-shell":
                        if int(code) == 0:
                            print("[launcher] Visual Shell launcher exited cleanly; continuing runtime")
                            self._children.remove(child)
                            continue
                        print(f"[launcher] Visual Shell exited early with code {code}; shutting down stack")
                        return int(code)
                    if child.name == "llm":
                        print(f"[launcher] owned LLM backend exited early with code {code}; shutting down stack")
                        return int(code) if code else 1
            time.sleep(0.2)
        return 130

    def _ensure_llm_backend(self) -> bool:
        if not self._should_use_llm():
            print("[launcher] LLM disabled for this launch")
            return True

        health_url = self.config.llm.health_url
        if self._health_probe(health_url, 1.0):
            self._reused_existing_llm = True
            print(f"[launcher] existing LLM backend is healthy: {health_url}")
            return True

        command = self._build_llm_command()
        if not command:
            if self._llm_is_required():
                print("[launcher] LLM is required but no llama-server command is configured")
                return False
            return True

        llm = self._start_child("llm", command)
        deadline = time.monotonic() + max(0.1, self.config.llm_startup_timeout)
        while time.monotonic() < deadline and not self._shutdown_requested.is_set():
            if llm.poll() is not None:
                print(f"[launcher] llama-server exited before becoming ready with code {llm.poll()}")
                return False
            if self._health_probe(health_url, 1.0):
                print(f"[launcher] LLM backend is ready: {health_url}")
                return True
            time.sleep(0.5)

        print(f"[launcher] LLM backend did not become ready before timeout: {health_url}")
        return not self._llm_is_required()

    def _ensure_visual_shell(self) -> bool:
        if self._tcp_probe(self.config.visual_shell_host, self.config.visual_shell_port, 0.2):
            print(
                "[launcher] existing Visual Shell TCP receiver detected; "
                "reusing it and not starting another Visual Shell"
            )
            return True
        self._start_child("visual-shell", self.config.visual_shell_command)
        return True

    def _start_child(self, name: str, command: Sequence[str]) -> ManagedProcess:
        print(f"[launcher] starting {name}: {shlex.join([str(part) for part in command])}")
        process = self._popen_factory(
            [str(part) for part in command],
            cwd=str(self.config.repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        pgid = self._process_group_id(process.pid)
        child = ManagedProcess(
            name=name,
            command=tuple(str(part) for part in command),
            process=process,
            process_group_id=pgid,
        )
        child.start_output_threads()
        self._children.append(child)
        return child

    def _terminate_child(self, child: ManagedProcess) -> None:
        if not child.owned:
            print(f"[launcher] reused existing {child.name}; not stopping it")
            return
        pgid = child.process_group_id or child.process.pid
        if child.poll() is not None and not self._process_group_exists(pgid):
            return
        print(f"[launcher] stopping {child.name} pgid={pgid}")
        self._send_group_signal(pgid, signal.SIGINT, child)
        time.sleep(0.15)
        if child.poll() is not None and not self._process_group_exists(pgid):
            print(f"[launcher] terminated {child.name}")
            return
        self._send_group_signal(pgid, signal.SIGTERM, child)

        deadline = time.monotonic() + max(0.1, self.config.shutdown_timeout)
        while time.monotonic() < deadline:
            if child.poll() is not None and not self._process_group_exists(pgid):
                print(f"[launcher] terminated {child.name}")
                return
            time.sleep(0.1)

        if child.poll() is not None and not self._process_group_exists(pgid):
            print(f"[launcher] terminated {child.name}")
            return
        print(f"[launcher] killed after timeout: {child.name} pgid={pgid}")
        self._send_group_signal(pgid, signal.SIGKILL, child)
        time.sleep(0.1)
        if child.poll() is not None and not self._process_group_exists(pgid):
            print(f"[launcher] terminated {child.name}")

    @staticmethod
    def _process_group_id(pid: int) -> int:
        try:
            return os.getpgid(pid)
        except ProcessLookupError:
            return pid
        except OSError:
            return pid

    @staticmethod
    def _process_group_exists(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

    @staticmethod
    def _send_group_signal(pgid: int, sig: int, child: ManagedProcess) -> None:
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        except OSError:
            if sig == signal.SIGKILL:
                child.process.kill()
            else:
                child.process.terminate()

    @staticmethod
    def _wait_reader_threads(child: ManagedProcess) -> None:
        for thread in child._reader_threads:
            if thread.is_alive():
                thread.join(timeout=0.2)

    def _should_use_llm(self) -> bool:
        return not self.config.no_llm and (self.config.llm.enabled or self.config.llm_required)

    def _llm_is_required(self) -> bool:
        return bool(self.config.llm_required)

    def _build_llm_command(self) -> tuple[str, ...]:
        llm = self.config.llm
        command = llm.command or "llama-server"
        parts = shlex.split(command) if isinstance(command, str) else [str(command)]
        if not parts:
            parts = ["llama-server"]

        model_path = llm.model_path
        if model_path:
            parts.extend(["--model", model_path])

        parsed = urllib.parse.urlparse(llm.server_url or "")
        if parsed.hostname:
            parts.extend(["--host", parsed.hostname])
        if parsed.port:
            parts.extend(["--port", str(parsed.port)])
        if llm.ctx_size:
            parts.extend(["--ctx-size", str(llm.ctx_size)])
        if llm.threads:
            parts.extend(["--threads", str(llm.threads)])
        return tuple(parts)


def probe_http_health(url: str, timeout: float) -> bool:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def probe_tcp_port(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def build_launcher_config(args: argparse.Namespace) -> LauncherConfig:
    repo_root = find_repo_root(Path(args.repo_root).expanduser().resolve() if args.repo_root else Path(__file__).resolve())
    settings = load_settings(repo_root)
    llm_settings = dict(settings.get("llm", {}) if isinstance(settings.get("llm"), dict) else {})
    visual_settings = dict(
        settings.get("visual_shell", {}) if isinstance(settings.get("visual_shell"), dict) else {}
    )

    llm_model = str(args.llm_model or llm_settings.get("model_path") or "").strip()
    llm_server_url = str(args.llm_server_url or llm_settings.get("server_url") or "http://127.0.0.1:8000").strip()
    llm = LLMConfig(
        enabled=bool(llm_settings.get("enabled", False)),
        command=str(llm_settings.get("command") or llm_settings.get("runner") or "llama-server"),
        model_path=llm_model,
        server_url=llm_server_url,
        server_health_path=str(llm_settings.get("server_health_path") or "/v1/models"),
        ctx_size=_optional_int(llm_settings.get("ctx_size")),
        threads=_optional_int(llm_settings.get("threads")),
    )

    python_executable = repo_root / ".venv" / "bin" / "python"
    if not python_executable.exists():
        python_executable = Path(sys.executable)

    visual_command = _configured_command(
        visual_settings.get("autostart", {}).get("launch_command")
        if isinstance(visual_settings.get("autostart"), dict)
        else None,
        default=("modules/presentation/visual_shell/bin/run_visual_shell.sh",),
    )
    transport_settings = visual_settings.get("transport", {}) if isinstance(visual_settings.get("transport"), dict) else {}

    return LauncherConfig(
        repo_root=repo_root,
        python_executable=python_executable,
        llm=llm,
        visual_shell_command=visual_command,
        nexa_command=(str(python_executable), "main.py"),
        visual_shell_host=str(transport_settings.get("host") or "127.0.0.1"),
        visual_shell_port=_optional_int(transport_settings.get("port")) or 8765,
        no_llm=bool(args.no_llm),
        no_visual_shell=bool(args.no_visual_shell),
        llm_required=bool(args.llm_required),
        shutdown_timeout=float(args.shutdown_timeout),
        llm_startup_timeout=float(args.llm_startup_timeout),
        dry_run=bool(args.dry_run),
    )


def load_settings(repo_root: Path) -> dict:
    path = repo_root / "config" / "settings.json"
    if not path.exists():
        path = repo_root / "config" / "settings.example.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def find_repo_root(start: Path) -> Path:
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        if (candidate / "main.py").is_file() and (candidate / "modules").is_dir():
            return candidate
    return Path.cwd()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the local NeXa product runtime stack.",
    )
    parser.add_argument("--no-llm", action="store_true", help="Do not check or start the local LLM backend.")
    parser.add_argument("--no-visual-shell", action="store_true", help="Do not start the Visual Shell.")
    parser.add_argument("--llm-required", action="store_true", help="Fail startup if the local LLM backend is not ready.")
    parser.add_argument("--llm-model", metavar="PATH", help="Override the GGUF model path passed to llama-server.")
    parser.add_argument("--llm-server-url", metavar="URL", help="Override the local LLM server URL.")
    parser.add_argument("--dry-run", action="store_true", help="Print the launch plan without starting processes.")
    parser.add_argument("--shutdown-timeout", type=float, default=DEFAULT_SHUTDOWN_TIMEOUT)
    parser.add_argument("--llm-startup-timeout", type=float, default=DEFAULT_LLM_STARTUP_TIMEOUT)
    parser.add_argument("--repo-root", metavar="PATH", help="Repository root. Auto-detected by default.")
    return parser


def _configured_command(value: object, *, default: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return tuple(shlex.split(value))
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        parts = tuple(str(part) for part in value if str(part).strip())
        if parts:
            return parts
    return tuple(default)


def _optional_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _join_url(base: str, path: str) -> str:
    base = str(base or "http://127.0.0.1:8000").rstrip("/")
    path = str(path or "/v1/models").strip()
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _stream_output(name: str, stream_name: str, stream: object) -> None:
    prefix = f"[{name}]"
    try:
        for line in stream:
            text = str(line).rstrip()
            if text:
                print(f"{prefix} {text}", flush=True)
    except Exception as error:
        print(f"[launcher] stopped reading {name} {stream_name}: {error}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = build_launcher_config(args)
    return ProductRuntimeLauncher(config).run()


if __name__ == "__main__":
    raise SystemExit(main())
