from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable


DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT_SEC = 0.2
DEFAULT_PORT_PATTERNS = (
    "/dev/serial/by-id/*",
    "/dev/ttyACM*",
    "/dev/ttyUSB*",
)


@dataclass(frozen=True, slots=True)
class SerialPortCandidate:
    """A detected serial device candidate for the mobile base."""

    device: str
    description: str = ""
    hwid: str = ""
    source: str = ""

    @property
    def real_device(self) -> str:
        return os.path.realpath(self.device)

    def as_dict(self) -> dict[str, str]:
        return {
            "device": self.device,
            "real_device": self.real_device,
            "description": self.description,
            "hwid": self.hwid,
            "source": self.source,
        }


def _candidate_sort_key(candidate: SerialPortCandidate) -> tuple[int, str]:
    # Prefer stable by-id symlinks when they point to the same real device.
    if candidate.device.startswith("/dev/serial/by-id/"):
        priority = 0
    elif candidate.device.startswith("/dev/ttyACM"):
        priority = 1
    elif candidate.device.startswith("/dev/ttyUSB"):
        priority = 2
    else:
        priority = 3
    return (priority, candidate.device)


def _deduplicate_by_real_device(
    candidates: Iterable[SerialPortCandidate],
) -> list[SerialPortCandidate]:
    selected: dict[str, SerialPortCandidate] = {}
    for candidate in sorted(candidates, key=_candidate_sort_key):
        selected.setdefault(candidate.real_device, candidate)
    return sorted(selected.values(), key=_candidate_sort_key)


def detect_serial_ports(
    *,
    patterns: Iterable[str] = DEFAULT_PORT_PATTERNS,
) -> list[SerialPortCandidate]:
    """Detect likely Linux serial ports without opening them."""

    candidates: list[SerialPortCandidate] = []

    try:
        from serial.tools import list_ports
    except Exception:
        list_ports = None

    if list_ports is not None:
        for port in list_ports.comports():
            device = str(getattr(port, "device", "") or "").strip()
            if not device:
                continue
            candidates.append(
                SerialPortCandidate(
                    device=device,
                    description=str(getattr(port, "description", "") or ""),
                    hwid=str(getattr(port, "hwid", "") or ""),
                    source="pyserial",
                )
            )

    for pattern in patterns:
        for device in glob.glob(str(pattern)):
            if os.path.exists(device):
                candidates.append(
                    SerialPortCandidate(device=device, source=f"glob:{pattern}")
                )

    return _deduplicate_by_real_device(candidates)


def choose_serial_port(
    *,
    explicit_port: str | None = None,
    candidates: Iterable[SerialPortCandidate] | None = None,
) -> str:
    """Choose one serial port or raise a clear error."""

    if explicit_port:
        return str(explicit_port)

    detected = list(candidates) if candidates is not None else detect_serial_ports()
    if not detected:
        raise RuntimeError("No serial device detected. Check /dev/ttyACM*, /dev/ttyUSB* or /dev/serial/by-id/.")
    if len(detected) > 1:
        devices = ", ".join(candidate.device for candidate in detected)
        raise RuntimeError(f"Multiple serial devices detected: {devices}. Run again with --port <device>.")
    return detected[0].device


class DryRunSerialTransport:
    """In-memory transport used by tests and dry-run smoke checks."""

    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.written_lines: list[str] = []

    def open(self) -> None:
        self.opened = True
        self.closed = False

    def write_line(self, line: str) -> None:
        if not self.opened or self.closed:
            raise RuntimeError("Dry-run serial transport is not open.")
        self.written_lines.append(str(line))

    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]:
        del duration_sec
        return []

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "DryRunSerialTransport":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class PySerialLineTransport:
    """Small pyserial line transport for STOP-only Sprint 1 smoke tests."""

    def __init__(
        self,
        *,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.timeout_sec = float(timeout_sec)
        self._serial: Any | None = None

    @property
    def is_open(self) -> bool:
        serial_obj = self._serial
        return bool(serial_obj is not None and getattr(serial_obj, "is_open", True))

    def open(self) -> None:
        if self.is_open:
            return
        try:
            import serial
        except Exception as error:
            raise RuntimeError("pyserial is required for mobile base serial smoke tests") from error

        self._serial = serial.Serial(
            self.port,
            self.baudrate,
            timeout=max(0.0, self.timeout_sec),
            write_timeout=max(0.0, self.timeout_sec),
        )

    def write_line(self, line: str) -> None:
        if not self.is_open or self._serial is None:
            raise RuntimeError("Serial transport is not open.")
        payload = str(line).encode("utf-8")
        self._serial.write(payload)
        flush = getattr(self._serial, "flush", None)
        if callable(flush):
            flush()

    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]:
        if not self.is_open or self._serial is None:
            return []
        if duration_sec <= 0.0:
            return []

        lines: list[str] = []
        deadline = time.monotonic() + float(duration_sec)
        while time.monotonic() < deadline:
            raw_line = self._serial.readline()
            if not raw_line:
                continue
            lines.append(raw_line.decode("utf-8", errors="replace").strip())
        return lines

    def close(self) -> None:
        serial_obj = self._serial
        if serial_obj is None:
            return
        close = getattr(serial_obj, "close", None)
        if callable(close):
            close()
        self._serial = None

    def __enter__(self) -> "PySerialLineTransport":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


__all__ = [
    "DEFAULT_BAUDRATE",
    "DEFAULT_PORT_PATTERNS",
    "DEFAULT_TIMEOUT_SEC",
    "DryRunSerialTransport",
    "PySerialLineTransport",
    "SerialPortCandidate",
    "choose_serial_port",
    "detect_serial_ports",
]
