from __future__ import annotations

import pytest

from modules.devices.mobile_base.serial_transport import (
    DryRunSerialTransport,
    SerialPortCandidate,
    choose_serial_port,
)


def test_dry_run_transport_records_lines() -> None:
    transport = DryRunSerialTransport()

    with transport:
        transport.write_line('{"T":13,"X":0.0,"Z":0.0}\n')

    assert transport.written_lines == ['{"T":13,"X":0.0,"Z":0.0}\n']
    assert transport.closed is True


def test_choose_serial_port_uses_explicit_port() -> None:
    assert choose_serial_port(explicit_port="/dev/ttyACM0", candidates=[]) == "/dev/ttyACM0"


def test_choose_serial_port_requires_single_auto_detected_candidate() -> None:
    assert choose_serial_port(
        candidates=[SerialPortCandidate(device="/dev/ttyACM0")]
    ) == "/dev/ttyACM0"

    with pytest.raises(RuntimeError):
        choose_serial_port(candidates=[])

    with pytest.raises(RuntimeError):
        choose_serial_port(
            candidates=[
                SerialPortCandidate(device="/dev/ttyACM0"),
                SerialPortCandidate(device="/dev/ttyUSB0"),
            ]
        )
