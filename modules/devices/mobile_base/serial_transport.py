from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass
from collections.abc import Sequence

DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT_SEC = 0.2


@dataclass(frozen=True, slots=True)
class SerialPortCandidate:
    device: str
    real_path: str = ""
    description: str = "n/a"
    source: str = "unknown"

    @property
    def real_device(self) -> str:
        return self.real_path or self.device

    def as_dict(self) -> dict[str, str]:
        return {
            "device": self.device,
            "real_device": self.real_device,
            "description": self.description,
            "source": self.source,
        }


def detect_serial_ports() -> list[SerialPortCandidate]:
    candidates: list[SerialPortCandidate] = []
    seen: set[str] = set()

    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        for device in sorted(glob.glob(pattern)):
            real = os.path.realpath(device)
            key = real or device
            if key in seen:
                continue
            seen.add(key)
            candidates.append(SerialPortCandidate(device=device, real_path=real, source=f"glob:{pattern}"))

    try:
        from serial.tools import list_ports

        for item in list_ports.comports():
            real = os.path.realpath(str(item.device))
            key = real or str(item.device)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                SerialPortCandidate(
                    device=str(item.device),
                    real_path=real,
                    description=str(item.description or "n/a"),
                    source="pyserial",
                )
            )
    except Exception:
        pass

    return candidates


def list_serial_ports() -> list[SerialPortCandidate]:
    return detect_serial_ports()


def choose_serial_port(
    explicit_port: str | None = None,
    *,
    candidates: Sequence[SerialPortCandidate] | None = None,
) -> str:
    requested = str(explicit_port or "").strip()
    if requested and requested != "auto":
        return requested

    detected = list(detect_serial_ports() if candidates is None else candidates)
    if len(detected) == 1:
        return detected[0].device
    if not detected:
        raise RuntimeError("No serial ports detected. Connect the mobile base or pass --port.")

    details = ", ".join(candidate.device for candidate in detected)
    raise RuntimeError(f"Multiple serial ports detected ({details}). Pass --port explicitly.")


class DryRunSerialTransport:
    def __init__(self) -> None:
        self.written_lines: list[str] = []
        self.lines = self.written_lines
        self.opened = False
        self.closed = False
        self.is_open = False

    def __enter__(self) -> "DryRunSerialTransport":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def open(self) -> None:
        self.opened = True
        self.closed = False
        self.is_open = True

    def write_line(self, line: str) -> None:
        self.open()
        self.written_lines.append(line)
        print("[DRY-RUN]", line.strip())

    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]:
        del duration_sec
        return []

    def read_lines(self, duration_sec: float = 0.0) -> list[str]:
        return self.read_available_lines(duration_sec=duration_sec)

    def close(self) -> None:
        self.closed = True
        self.is_open = False


InMemoryLineTransport = DryRunSerialTransport


class PySerialLineTransport:
    def __init__(
        self,
        *,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout_sec = float(timeout_sec)
        self._serial = None

    def open(self) -> None:
        if self._serial is not None:
            return
        import serial

        self._serial = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout_sec)

    def write_line(self, line: str) -> None:
        self.open()
        assert self._serial is not None
        print("[WRITE]", line.strip())
        self._serial.write(line.encode("utf-8"))
        self._serial.flush()

    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]:
        self.open()
        assert self._serial is not None

        deadline = time.monotonic() + max(0.0, float(duration_sec))
        lines: list[str] = []
        while time.monotonic() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                print("[READ]", line)
                lines.append(line)
        return lines

    def read_lines(self, duration_sec: float = 0.0) -> list[str]:
        return self.read_available_lines(duration_sec=duration_sec)

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None
