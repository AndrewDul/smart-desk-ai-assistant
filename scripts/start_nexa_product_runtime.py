#!/usr/bin/env python3
"""Start the full local NeXa product runtime stack."""
from __future__ import annotations

import argparse
import json
import os
import shutil
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
DEFAULT_VISUAL_SHELL_STARTUP_TIMEOUT = 8.0
DEFAULT_NEXA_STARTUP_GRACE_SECONDS = 1.0
DEFAULT_STACK_STATE_DIR = "var/run/nexa_stack"


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
    visual_shell_startup_timeout: float = DEFAULT_VISUAL_SHELL_STARTUP_TIMEOUT
    nexa_startup_grace_seconds: float = DEFAULT_NEXA_STARTUP_GRACE_SECONDS
    nexa_voice_readiness_timeout: float = 45.0
    state_dir: Path | None = None
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
        self._reused_existing_visual_shell = False

    def dry_run_plan(self) -> list[dict[str, object]]:
        plan: list[dict[str, object]] = []
        if self._should_use_llm():
            command = self._build_llm_command()
            plan.append(
                {
                    "name": "llm",
                    "command": list(command) if command else [],
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

        self._prepare_state_dir()
        self._install_signal_handlers()
        try:
            if not self._ensure_llm_backend():
                return 2
            if not self.config.no_visual_shell:
                if not self._ensure_visual_shell():
                    return 3
            nexa = self._start_child("nexa", self.config.nexa_command)
            if not self._confirm_nexa_started(nexa):
                return 3
            if not self._confirm_nexa_voice_ready(nexa):
                return 3
            print("[launcher] Full NeXa stack is ready")
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
        self._cleanup_state_dir()

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
            if self._shutdown_request_file().exists():
                print(f"[launcher] shutdown request detected: {self._shutdown_request_file()}")
                return 0

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
                        if self._tcp_probe(self.config.visual_shell_host, self.config.visual_shell_port, 0.2):
                            print(
                                "[launcher] Visual Shell launcher exited, but TCP receiver is reachable; "
                                "continuing runtime"
                            )
                            self._children.remove(child)
                            continue
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
            self._write_state()
            return True

        command = self._build_llm_command()
        if not command:
            return False

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
            self._reused_existing_visual_shell = True
            print(
                "[launcher] existing Visual Shell TCP receiver detected; "
                "reusing it and not starting another Visual Shell"
            )
            self._write_state()
            return True
        visual_shell = self._start_child("visual-shell", self.config.visual_shell_command)
        return self._confirm_visual_shell_ready(visual_shell)

    def _start_child(self, name: str, command: Sequence[str]) -> ManagedProcess:
        print(f"[launcher] starting {name}: {shlex.join([str(part) for part in command])}")
        env = os.environ.copy()
        if name == "nexa":
            env["PYTHONUNBUFFERED"] = "1"
            env["NEXA_REQUIRE_REAL_VOICE_INPUT"] = env.get("NEXA_REQUIRE_REAL_VOICE_INPUT", "1")
            env["NEXA_REQUIRE_REAL_WAKE_GATE"] = env.get("NEXA_REQUIRE_REAL_WAKE_GATE", "1")
            env["NEXA_RUNTIME_MODE"] = env.get("NEXA_RUNTIME_MODE", "voice_stack_runtime")
            env["NEXA_STACK_STATE_DIR"] = str(self._state_dir())
        process = self._popen_factory(
            [str(part) for part in command],
            cwd=str(self.config.repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        pgid = self._process_group_id(process.pid)
        print(f"[launcher] started {name}: pid={process.pid} pgid={pgid} owned=true")
        child = ManagedProcess(
            name=name,
            command=tuple(str(part) for part in command),
            process=process,
            process_group_id=pgid,
        )
        child.start_output_threads()
        self._children.append(child)
        self._write_state()
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

    def _state_dir(self) -> Path:
        return self.config.state_dir or (self.config.repo_root / DEFAULT_STACK_STATE_DIR)

    def _shutdown_request_file(self) -> Path:
        return self._state_dir() / "shutdown.request"

    def _prepare_state_dir(self) -> None:
        state_dir = self._state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        for stale_file in (self._shutdown_request_file(), self._voice_ready_file()):
            try:
                stale_file.unlink()
            except FileNotFoundError:
                pass
        self._write_state()
        print(f"[launcher] stack state directory: {state_dir}")

    def _write_state(self) -> None:
        state_dir = self._state_dir()
        try:
            state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            print(f"[launcher] failed to create state directory {state_dir}: {error}")
            return

        children: list[dict[str, object]] = []
        for child in self._children:
            entry = {
                "name": child.name,
                "pid": int(child.process.pid),
                "pgid": int(child.process_group_id or child.process.pid),
                "owned": bool(child.owned),
                "command": list(child.command),
            }
            if child.name == "llm":
                entry["started_by_stack"] = bool(child.owned)
            children.append(entry)
            self._write_pid_file(state_dir / f"{child.name}.pid", child.process.pid)

        state = {
            "launcher_pid": os.getpid(),
            "state_dir": str(state_dir),
            "shutdown_request_file": str(self._shutdown_request_file()),
            "llm": {
                "health_url": self.config.llm.health_url,
                "started_by_stack": any(child.name == "llm" and child.owned for child in self._children),
                "reused_existing": bool(self._reused_existing_llm),
            },
            "visual_shell": {
                "reused_existing": bool(self._reused_existing_visual_shell),
                "tcp": f"{self.config.visual_shell_host}:{self.config.visual_shell_port}",
            },
            "children": children,
        }
        self._write_pid_file(state_dir / "launcher.pid", os.getpid())
        tmp_path = state_dir / "state.json.tmp"
        target_path = state_dir / "state.json"
        try:
            tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
            tmp_path.replace(target_path)
        except OSError as error:
            print(f"[launcher] failed to write stack state {target_path}: {error}")

    @staticmethod
    def _write_pid_file(path: Path, pid: int) -> None:
        try:
            path.write_text(f"{int(pid)}\n", encoding="utf-8")
        except OSError as error:
            print(f"[launcher] failed to write pid file {path}: {error}")

    def _cleanup_state_dir(self) -> None:
        state_dir = self._state_dir()
        if not state_dir.exists():
            return
        for path in state_dir.iterdir():
            try:
                path.unlink()
            except IsADirectoryError:
                continue
            except OSError as error:
                print(f"[launcher] failed to remove state file {path}: {error}")
        try:
            state_dir.rmdir()
            print(f"[launcher] cleaned stack state directory: {state_dir}")
        except OSError:
            print(f"[launcher] stack state directory left for inspection: {state_dir}")
            return

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

        executable = self._resolve_llm_executable(parts[0])
        if executable is None:
            print(f"[launcher] LLM executable not found: {parts[0]}")
            print(
                "[launcher] Set NEXA_LLM_SERVER_BIN=/absolute/path/to/llama-server "
                "or build llama.cpp under ./llama.cpp/build/bin/llama-server"
            )
            return ()
        parts[0] = executable
        print(f"[launcher] resolved LLM executable: {executable}")

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

    def _resolve_llm_executable(self, executable: str) -> str | None:
        env_override = os.environ.get("NEXA_LLM_SERVER_BIN", "").strip()
        if env_override:
            candidate = Path(env_override).expanduser()
            if candidate.is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
            return None

        raw = str(executable or "").strip()
        if not raw:
            raw = "llama-server"

        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
            return None

        if raw == "llama-server":
            resolved = shutil.which(raw)
            if resolved:
                return resolved

            repo_local = self.config.repo_root / "llama.cpp" / "build" / "bin" / "llama-server"
            if repo_local.is_file() and os.access(repo_local, os.X_OK):
                return str(repo_local)
            return None

        return raw

    def _confirm_visual_shell_ready(self, visual_shell: ManagedProcess) -> bool:
        deadline = time.monotonic() + max(0.1, self.config.visual_shell_startup_timeout)
        while time.monotonic() < deadline and not self._shutdown_requested.is_set():
            if self._tcp_probe(self.config.visual_shell_host, self.config.visual_shell_port, 0.2):
                print("[launcher] Visual Shell started and TCP receiver is reachable")
                return True
            code = visual_shell.poll()
            if code is not None:
                if self._tcp_probe(self.config.visual_shell_host, self.config.visual_shell_port, 0.2):
                    print("[launcher] Visual Shell started and TCP receiver is reachable")
                    return True
                if int(code) == 0:
                    print("[launcher] Visual Shell launcher exited cleanly before TCP readiness")
                    return False
                print(f"[launcher] Visual Shell exited before TCP readiness with code {code}")
                return False
            time.sleep(0.2)

        if visual_shell.poll() is None:
            print(
                "[launcher] warning: Visual Shell process is still alive, "
                "but TCP receiver is not ready yet"
            )
            return True
        return False

    def _confirm_nexa_started(self, nexa: ManagedProcess) -> bool:
        deadline = time.monotonic() + max(0.0, self.config.nexa_startup_grace_seconds)
        while time.monotonic() < deadline:
            code = nexa.poll()
            if code is not None:
                print(f"[launcher] NeXa runtime exited during startup with code {code}")
                return False
            time.sleep(0.1)
        print("[launcher] NeXa runtime started and still running")
        return True

    def _voice_ready_file(self) -> Path:
        return self._state_dir() / "voice_ready.json"

    def _confirm_nexa_voice_ready(self, nexa: ManagedProcess) -> bool:
        deadline = time.monotonic() + max(0.1, self.config.nexa_voice_readiness_timeout)
        ready_path = self._voice_ready_file()
        while time.monotonic() < deadline and not self._shutdown_requested.is_set():
            code = nexa.poll()
            if code is not None:
                print(f"[launcher] NeXa runtime exited before voice readiness with code {code}")
                return False

            if ready_path.exists():
                try:
                    payload = json.loads(ready_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    print(f"[launcher] warning: could not read voice readiness file: {error}")
                    return False

                if bool(payload.get("ready", False)):
                    print("[launcher] NeXa voice runtime is ready")
                    return True

                issues = list(payload.get("issues", []) or [])
                issue_text = " | ".join(str(item) for item in issues) if issues else "unknown voice readiness failure"
                print(f"[launcher] NeXa voice runtime is not ready: {issue_text}")
                print(
                    "[launcher] Check config/settings.json voice_input.device_index, "
                    "voice_input.device_name_contains, wake_model_path, and Vosk model paths."
                )
                return False
            time.sleep(0.2)

        print("[launcher] NeXa voice runtime readiness was not reported before timeout")
        print(
            "[launcher] Check that main.py reaches the voice startup sequence and that child output is unbuffered."
        )
        return False


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
    python_command = (str(python_executable), "-u", "main.py")

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
        nexa_command=python_command,
        visual_shell_host=str(transport_settings.get("host") or "127.0.0.1"),
        visual_shell_port=_optional_int(transport_settings.get("port")) or 8765,
        no_llm=bool(args.no_llm),
        no_visual_shell=bool(args.no_visual_shell),
        llm_required=bool(args.llm_required),
        shutdown_timeout=float(args.shutdown_timeout),
        llm_startup_timeout=float(args.llm_startup_timeout),
        visual_shell_startup_timeout=float(args.visual_shell_startup_timeout),
        nexa_startup_grace_seconds=float(args.nexa_startup_grace_seconds),
        nexa_voice_readiness_timeout=float(args.nexa_voice_readiness_timeout),
        state_dir=Path(args.state_dir).expanduser().resolve() if getattr(args, "state_dir", "") else None,
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
    parser.add_argument("--visual-shell-startup-timeout", type=float, default=DEFAULT_VISUAL_SHELL_STARTUP_TIMEOUT)
    parser.add_argument("--nexa-startup-grace-seconds", type=float, default=DEFAULT_NEXA_STARTUP_GRACE_SECONDS)
    parser.add_argument("--nexa-voice-readiness-timeout", type=float, default=45.0)
    parser.add_argument(
        "--state-dir",
        metavar="PATH",
        default=os.environ.get("NEXA_STACK_STATE_DIR", ""),
        help="Runtime stack state directory. Defaults to var/run/nexa_stack under the repo root.",
    )
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
