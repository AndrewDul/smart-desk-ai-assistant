from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass

DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT_SEC = 0.2

@dataclass(frozen=True, slots=True)
class SerialPortCandidate:
    device: str
    real_path: str
    description: str = "n/a"
    source: str = "unknown"

def list_serial_ports() -> list[SerialPortCandidate]:
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
        from serial.tools import list_ports  # type: ignore
        for item in list_ports.comports():
            real = os.path.realpath(str(item.device))
            key = real or str(item.device)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(SerialPortCandidate(device=str(item.device), real_path=real, description=str(item.description or "n/a"), source="pyserial"))
    except Exception:
        pass
    return candidates

def choose_serial_port(port: str | None) -> str:
    requested = str(port or "").strip()
    if requested and requested != "auto":
        return requested
    candidates = list_serial_ports()
    if len(candidates) == 1:
        return candidates[0].device
    if not candidates:
        raise RuntimeError("No serial ports detected. Connect the mobile base or pass --port.")
    details = ", ".join(c.device for c in candidates)
    raise RuntimeError(f"Multiple serial ports detected ({details}). Pass --port explicitly.")

class DryRunSerialTransport:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.is_open = False
    def open(self) -> None:
        self.is_open = True
    def write_line(self, line: str) -> None:
        self.lines.append(line.rstrip("\n"))
        print("[DRY-RUN]", line.strip())
    def read_lines(self, duration_sec: float = 0.0) -> list[str]:
        return []
    def close(self) -> None:
        self.is_open = False

class PySerialLineTransport:
    def __init__(self, *, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> None:
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout_sec = float(timeout_sec)
        self._serial = None
    def open(self) -> None:
        if self._serial is not None:
            return
        import serial  # type: ignore
        self._serial = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout_sec)
    def write_line(self, line: str) -> None:
        self.open()
        assert self._serial is not None
        print("[WRITE]", line.strip())
        self._serial.write(line.encode("utf-8"))
        self._serial.flush()
    def read_lines(self, duration_sec: float = 0.0) -> list[str]:
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
    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None
