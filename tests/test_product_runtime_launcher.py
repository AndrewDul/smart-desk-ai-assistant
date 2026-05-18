from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import signal
from scripts.start_nexa_product_runtime import (
    LLMConfig,
    LauncherConfig,
    ManagedProcess,
    ProductRuntimeLauncher,
    build_launcher_config,
)


class FakeProcess:
    _next_pid = 5000

    def __init__(self, command: list[str], *, returncode: int | None = None, **_kwargs: object) -> None:
        FakeProcess._next_pid += 1
        self.pid = FakeProcess._next_pid
        self.command = list(command)
        self.returncode = returncode
        self.stdout = None
        self.stderr = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _config(tmp_path: Path, *, llm_enabled: bool = True, llm_required: bool = False) -> LauncherConfig:
    return LauncherConfig(
        repo_root=tmp_path,
        python_executable=tmp_path / ".venv" / "bin" / "python",
        llm=LLMConfig(
            enabled=llm_enabled,
            command="llama-server",
            model_path="models/model.gguf",
            server_url="http://127.0.0.1:8000",
            server_health_path="/v1/models",
        ),
        visual_shell_command=("modules/presentation/visual_shell/bin/run_visual_shell.sh",),
        nexa_command=("python", "main.py"),
        llm_required=llm_required,
        llm_startup_timeout=0.01,
        shutdown_timeout=0.01,
    )


def test_dry_run_plan_contains_stack_commands(tmp_path: Path) -> None:
    launcher = ProductRuntimeLauncher(_config(tmp_path))

    plan = launcher.dry_run_plan()

    assert [entry["name"] for entry in plan] == ["llm", "visual-shell", "nexa"]
    assert plan[0]["health_url"] == "http://127.0.0.1:8000/v1/models"
    assert "--model" in plan[0]["command"]
    assert plan[2]["command"] == ["python", "main.py"]


def test_launcher_reuses_existing_healthy_llm(tmp_path: Path) -> None:
    started: list[list[str]] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        started.append(list(command))
        return FakeProcess(command, **kwargs)

    launcher = ProductRuntimeLauncher(
        _config(tmp_path),
        popen_factory=fake_popen,
        health_probe=lambda _url, _timeout: True,
    )

    assert launcher._ensure_llm_backend() is True
    assert started == []
    launcher.shutdown()
    assert launcher._reused_existing_llm is True


def test_launcher_starts_owned_llm_when_required_and_unhealthy(tmp_path: Path) -> None:
    started: list[list[str]] = []
    probes = iter([False, True])

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        started.append(list(command))
        return FakeProcess(command, **kwargs)

    def health_probe(_url: str, _timeout: float) -> bool:
        return next(probes)

    launcher = ProductRuntimeLauncher(
        _config(tmp_path, llm_required=True),
        popen_factory=fake_popen,
        health_probe=health_probe,
    )

    assert launcher._ensure_llm_backend() is True
    assert started == [["llama-server", "--model", "models/model.gguf", "--host", "127.0.0.1", "--port", "8000"]]


def test_launcher_reports_required_llm_startup_failure(tmp_path: Path) -> None:
    started: list[list[str]] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        started.append(list(command))
        return FakeProcess(command, returncode=1, **kwargs)

    launcher = ProductRuntimeLauncher(
        _config(tmp_path, llm_required=True),
        popen_factory=fake_popen,
        health_probe=lambda _url, _timeout: False,
    )

    assert launcher._ensure_llm_backend() is False
    assert started


def test_launcher_shutdown_targets_owned_child_process_group(tmp_path: Path, monkeypatch) -> None:
    sent: list[tuple[int, int]] = []
    process = FakeProcess(["python", "main.py"])
    launcher = ProductRuntimeLauncher(_config(tmp_path))
    launcher._children.append(
        ManagedProcess(name="nexa", command=("python", "main.py"), process=process, process_group_id=4242)
    )

    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        process.returncode = -sig

    monkeypatch.setattr("scripts.start_nexa_product_runtime.os.killpg", fake_killpg)
    monkeypatch.setattr(ProductRuntimeLauncher, "_process_group_exists", staticmethod(lambda _pgid: False))

    launcher.shutdown()

    assert sent == [(4242, 2)]


def test_launcher_cleanup_targets_visual_shell_group_even_if_parent_exited(tmp_path: Path, monkeypatch) -> None:
    sent: list[tuple[int, int]] = []
    process = FakeProcess(["visual-shell"], returncode=0)
    group_exists = iter([True, True, False])
    launcher = ProductRuntimeLauncher(_config(tmp_path))
    launcher._children.append(
        ManagedProcess(name="visual-shell", command=("visual-shell",), process=process, process_group_id=6001)
    )

    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))

    def fake_group_exists(_pgid: int) -> bool:
        return next(group_exists)

    monkeypatch.setattr("scripts.start_nexa_product_runtime.os.killpg", fake_killpg)
    monkeypatch.setattr(ProductRuntimeLauncher, "_process_group_exists", staticmethod(fake_group_exists))

    launcher.shutdown()

    assert sent == [(6001, 2), (6001, 15)]


def test_launcher_keyboard_interrupt_path_shuts_down_children(tmp_path: Path, monkeypatch) -> None:
    sent: list[tuple[int, int]] = []
    process = FakeProcess(["python", "main.py"])
    config = _config(tmp_path, llm_enabled=False)
    config = LauncherConfig(
        repo_root=config.repo_root,
        python_executable=config.python_executable,
        llm=config.llm,
        visual_shell_command=config.visual_shell_command,
        nexa_command=config.nexa_command,
        no_llm=True,
        no_visual_shell=True,
        shutdown_timeout=0.01,
    )
    launcher = ProductRuntimeLauncher(config, popen_factory=lambda _cmd, **_kw: process)

    def fake_watch(_nexa: ManagedProcess) -> int:
        raise KeyboardInterrupt

    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        process.returncode = -sig

    monkeypatch.setattr(launcher, "_watch", fake_watch)
    monkeypatch.setattr("scripts.start_nexa_product_runtime.os.killpg", fake_killpg)
    monkeypatch.setattr(ProductRuntimeLauncher, "_process_group_id", staticmethod(lambda _pid: 7001))
    monkeypatch.setattr(ProductRuntimeLauncher, "_process_group_exists", staticmethod(lambda _pgid: False))

    assert launcher.run() == 130
    assert sent == [(7001, signal.SIGINT)]


def test_launcher_signal_handler_requests_shutdown(tmp_path: Path, monkeypatch) -> None:
    registered = {}
    launcher = ProductRuntimeLauncher(_config(tmp_path))
    shutdown_calls: list[bool] = []

    def fake_signal(sig: int, handler) -> None:
        registered[sig] = handler

    def fake_shutdown() -> None:
        shutdown_calls.append(True)

    monkeypatch.setattr("scripts.start_nexa_product_runtime.signal.signal", fake_signal)
    monkeypatch.setattr(launcher, "shutdown", fake_shutdown)

    launcher._install_signal_handlers()
    registered[signal.SIGINT](signal.SIGINT, None)

    assert shutdown_calls == [True]


def test_launcher_reuses_existing_visual_shell_receiver(tmp_path: Path) -> None:
    started: list[list[str]] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        started.append(list(command))
        return FakeProcess(command, **kwargs)

    launcher = ProductRuntimeLauncher(
        _config(tmp_path),
        popen_factory=fake_popen,
        tcp_probe=lambda _host, _port, _timeout: True,
    )

    assert launcher._ensure_visual_shell() is True
    assert started == []


def test_build_launcher_config_uses_venv_python_when_present(tmp_path: Path) -> None:
    (tmp_path / "modules").mkdir()
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.write_text("", encoding="utf-8")
    (tmp_path / "config" / "settings.json").write_text(
        """
        {
          "llm": {
            "enabled": true,
            "command": "llama-server",
            "model_path": "models/qwen.gguf",
            "server_url": "http://127.0.0.1:9000",
            "server_health_path": "/v1/models"
          },
          "visual_shell": {
            "transport": {
              "host": "127.0.0.1",
              "port": 9001
            },
            "autostart": {
              "launch_command": ["visual-shell-test"]
            }
          }
        }
        """,
        encoding="utf-8",
    )

    config = build_launcher_config(
        Namespace(
            repo_root=str(tmp_path),
            llm_model=None,
            llm_server_url=None,
            no_llm=False,
            no_visual_shell=False,
            llm_required=False,
            shutdown_timeout=1.0,
            llm_startup_timeout=1.0,
            dry_run=True,
        )
    )

    assert config.python_executable == venv_python
    assert config.nexa_command == (str(venv_python), "main.py")
    assert config.visual_shell_command == ("visual-shell-test",)
    assert config.visual_shell_host == "127.0.0.1"
    assert config.visual_shell_port == 9001
    assert config.llm.health_url == "http://127.0.0.1:9000/v1/models"
