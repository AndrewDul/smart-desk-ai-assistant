from __future__ import annotations

from scripts import mobile_base_stop


def test_stop_script_dry_run(capsys) -> None:
    exit_code = mobile_base_stop.main(["--dry-run", "--stop-repeat", "1"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '[DRY-RUN] {"T":13,"X":0.0,"Z":0.0}' in captured.out
    assert "[OK] Mobile base STOP completed." in captured.out


def test_stop_script_refuses_hardware_without_env_gate(monkeypatch, capsys) -> None:
    monkeypatch.delenv("CONFIRM_NEXA_MOBILE_BASE_TEST", raising=False)

    exit_code = mobile_base_stop.main(["--port", "/dev/ttyACM0"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Hardware gate is closed" in captured.out
