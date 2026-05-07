from __future__ import annotations

from scripts.mobile_base_usb_smoke_test import main


def test_usb_smoke_dry_run_sends_stop_only(capsys) -> None:
    exit_code = main(["--dry-run", "--stop-repeat", "2", "--stop-interval-sec", "0"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.count('{"T":13,"X":0.0,"Z":0.0}') == 2
    assert "[DRY-RUN]" in captured.out


def test_usb_smoke_refuses_hardware_without_stop_flag(capsys) -> None:
    exit_code = main([])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--send-stop-only" in captured.out
