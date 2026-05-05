from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/run_vision_tracking_single_pan_tilt_step.py")


class _FakeSerialPort:
    def __init__(self, writes: list[str]) -> None:
        self._writes = writes

    def __enter__(self) -> "_FakeSerialPort":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def reset_input_buffer(self) -> None:
        return None

    def write(self, payload: bytes) -> int:
        text = payload.decode("utf-8")
        self._writes.append(text)
        return len(payload)

    def flush(self) -> None:
        return None

    def readline(self) -> bytes:
        return b""


class _FakeSerialFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.writes: list[str] = []

    def __call__(self, port: str, baudrate: int, *, timeout: float) -> _FakeSerialPort:
        self.calls.append(
            {
                "port": port,
                "baudrate": baudrate,
                "timeout": timeout,
            }
        )
        return _FakeSerialPort(self.writes)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_vision_tracking_single_pan_tilt_step",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_state(path: Path, *, port: str | None = None, x: float = 0.0, y: float = 0.0) -> None:
    path.write_text(
        json.dumps(
            {
                "port": port or "/dev/serial0",
                "baudrate": 115200,
                "x": x,
                "y": y,
                "marked_limits": {
                    "pan_left_x": -15.0,
                    "pan_right_x": 15.0,
                    "tilt_min_y": -8.0,
                    "tilt_max_y": 8.0,
                },
            }
        ),
        encoding="utf-8",
    )


def test_single_tracking_step_preview_does_not_open_serial(tmp_path, capsys) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    status_path = tmp_path / "single_step_status.json"
    _write_state(state_path)

    exit_code = module.main(
        [
            "--settings",
            "config/settings.json",
            "--state",
            str(state_path),
            "--status-path",
            str(status_path),
            "--pan-delta",
            "0.25",
            "--tilt-delta",
            "0.0",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PREVIEW ONLY" in captured.out
    assert "backend_command_executed=False" in captured.out
    assert status_path.exists()

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["event"] == "vision_tracking_plan"
    assert payload["last_plan"]["pan_delta_degrees"] == 0.25
    assert payload["last_pan_tilt_adapter_result"]["backend_command_executed"] is False


def test_single_tracking_step_rejects_delta_above_single_step_limit(tmp_path) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path)

    try:
        module.main(
            [
                "--settings",
                "config/settings.json",
                "--state",
                str(state_path),
                "--pan-delta",
                "0.75",
            ]
        )
    except SystemExit as error:
        assert "Maximum single-step pan delta" in str(error)
    else:
        raise AssertionError("Expected SystemExit for unsafe pan delta.")


def test_single_tracking_step_execute_requires_env_confirmation(tmp_path, monkeypatch) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path)
    monkeypatch.delenv(module.CONFIRM_ENV_NAME, raising=False)

    try:
        module.main(
            [
                "--settings",
                "config/settings.json",
                "--state",
                str(state_path),
                "--pan-delta",
                "0.25",
                "--execute",
                "--i-understand-this-moves-hardware",
                "--confirm-text",
                module.CONFIRM_VALUE,
            ]
        )
    except SystemExit as error:
        assert module.CONFIRM_ENV_NAME in str(error)
    else:
        raise AssertionError("Expected SystemExit without confirmation env var.")


def test_single_tracking_step_executes_full_chain_with_fake_serial(tmp_path, monkeypatch) -> None:
    module = _load_module()
    device_path = tmp_path / "serial0"
    device_path.touch()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    status_path = tmp_path / "single_step_status.json"
    _write_state(state_path, port=str(device_path))
    monkeypatch.setenv(module.CONFIRM_ENV_NAME, module.CONFIRM_VALUE)

    fake_serial = _FakeSerialFactory()
    result = module.run_single_tracking_step(
        settings_path=Path("config/settings.json"),
        state_path=state_path,
        status_path=status_path,
        port=str(device_path),
        baudrate=115200,
        pan_delta=0.25,
        tilt_delta=0.0,
        speed=45,
        acceleration=45,
        serial_warmup_seconds=0.0,
        read_after_write_seconds=0.0,
        execute=True,
        understand=True,
        confirm_text=module.CONFIRM_VALUE,
        serial_factory=fake_serial,
    )

    assert result["ok"] is True
    assert result["execute"] is True
    assert result["plan"]["pan_delta_degrees"] == 0.25
    assert result["execution_result"]["would_move_pan_tilt"] is True
    assert result["pan_tilt_adapter_result"]["status"] == "backend_command_executed"
    assert result["pan_tilt_adapter_result"]["backend_command_executed"] is True
    assert fake_serial.calls == [
        {
            "port": str(device_path),
            "baudrate": 115200,
            "timeout": 0.2,
        }
    ]

    sent_commands = [json.loads(line) for line in fake_serial.writes]
    assert sent_commands[:5] == [
        {"T": 135},
        {"T": 137, "s": 0, "y": 0},
        {"T": 4, "cmd": 2},
        {"T": 210, "cmd": 1},
        {"T": 133, "X": 0, "Y": 0, "SPD": 45, "ACC": 45},
    ]
    assert sent_commands[5] == {
        "T": 133,
        "X": 0.25,
        "Y": 0,
        "SPD": 45,
        "ACC": 45,
    }


def test_single_tracking_step_execute_rejects_non_centered_state(tmp_path, monkeypatch) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path, x=0.0, y=80.0)
    monkeypatch.setenv(module.CONFIRM_ENV_NAME, module.CONFIRM_VALUE)

    try:
        module.run_single_tracking_step(
            settings_path=Path("config/settings.json"),
            state_path=state_path,
            status_path=tmp_path / "single_step_status.json",
            port=None,
            baudrate=None,
            pan_delta=0.25,
            tilt_delta=0.0,
            speed=45,
            acceleration=45,
            serial_warmup_seconds=0.0,
            read_after_write_seconds=0.0,
            execute=True,
            understand=True,
            confirm_text=module.CONFIRM_VALUE,
            serial_factory=_FakeSerialFactory(),
        )
    except SystemExit as error:
        assert "calibration state is not near center" in str(error)
        assert "Y=80.0" in str(error)
    else:
        raise AssertionError("Expected SystemExit for non-centered calibration state.")
