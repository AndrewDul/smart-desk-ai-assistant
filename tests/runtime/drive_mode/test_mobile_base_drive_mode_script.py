from __future__ import annotations

from scripts.mobile_base_drive_mode import (
    DEFAULT_ANGULAR_SPEED_RAD_S,
    DEFAULT_LINEAR_SPEED_MPS,
    MAX_ANGULAR_SPEED_RAD_S,
    MAX_LINEAR_SPEED_MPS,
    _build_controller,
    build_parser,
    main,
)
from modules.runtime.drive_mode import DriveModeService


def test_drive_mode_parser_defaults_to_localhost() -> None:
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.http_port == 8768
    assert args.enable_movement is False
    assert args.linear_speed_mps == DEFAULT_LINEAR_SPEED_MPS
    assert args.angular_speed_rad_s == DEFAULT_ANGULAR_SPEED_RAD_S


def test_drive_mode_self_test_runs_without_hardware(capsys) -> None:
    exit_code = main(["--self-test"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "[OK] Drive mode self-test completed." in captured.out


def test_drive_mode_clamps_cli_speed_requests_to_hard_caps() -> None:
    args = build_parser().parse_args([
        "--self-test",
        "--linear-speed-mps",
        "0.99",
        "--angular-speed-rad-s",
        "0.99",
    ])
    controller, _selected_port, _is_dry_run = _build_controller(args)
    service = DriveModeService(controller=controller)
    controller.open()
    try:
        forward = service.handle_keyboard_event(event="down", key="w")
        assert forward.command == f'{{"T":13,"X":{MAX_LINEAR_SPEED_MPS},"Z":0.0}}'

        rotate = service.handle_keyboard_event(event="down", key="a")
        assert rotate.command == f'{{"T":13,"X":0.0,"Z":{MAX_ANGULAR_SPEED_RAD_S}}}'
    finally:
        controller.close()


def test_drive_mode_web_panel_wires_click_hold_buttons_after_repair() -> None:
    from scripts.mobile_base_drive_mode import HTML_PAGE

    assert "NeXa click-hold drive buttons patch" in HTML_PAGE
    assert "pointerdown" in HTML_PAGE
    assert "pointerup" in HTML_PAGE
    assert "touchstart" in HTML_PAGE
    assert "pressPanelDriveKey" in HTML_PAGE
    assert "releasePanelDriveKey" in HTML_PAGE
    assert "cursor: pointer" in HTML_PAGE
    assert "touch-action: none" in HTML_PAGE

