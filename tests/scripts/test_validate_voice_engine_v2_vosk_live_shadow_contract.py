from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_live_shadow_contract import (
    main,
    run_vosk_live_shadow_contract_validation,
)


def test_run_vosk_live_shadow_contract_validation_writes_disabled_contract(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "contract.json"

    result = run_vosk_live_shadow_contract_validation(output_path=output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["accepted"] is True
    assert result["action"] == "validate_vosk_live_shadow_contract"
    assert result["result"]["enabled"] is False
    assert result["result"]["recognition_attempted"] is False
    assert payload["accepted"] is True
    assert payload["runtime_integration"] is False
    assert payload["command_execution_enabled"] is False
    assert payload["microphone_stream_started"] is False
    assert payload["independent_microphone_stream_started"] is False
    assert payload["live_command_recognition_enabled"] is False


def test_run_vosk_live_shadow_contract_validation_can_check_enabled_shape(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "contract.json"

    result = run_vosk_live_shadow_contract_validation(
        enabled_contract=True,
        output_path=output_path,
    )

    assert result["accepted"] is True
    assert result["result"]["enabled"] is True
    assert result["result"]["observed"] is False
    assert result["result"]["recognition_attempted"] is False
    assert result["result"]["recognized"] is False
    assert result["result"]["microphone_stream_started"] is False


def test_cli_returns_zero_for_disabled_contract(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "contract.json"

    exit_code = main(["--output-path", str(output_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["output_path"] == str(output_path)
    assert output_path.exists()


def test_cli_returns_zero_for_enabled_contract_without_output(capsys) -> None:
    exit_code = main(["--enabled-contract", "--no-output"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["output_path"] == ""
    assert payload["result"]["enabled"] is True
    assert payload["result"]["recognition_attempted"] is False