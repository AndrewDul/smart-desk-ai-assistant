from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_pre_stt_shadow_log import (
    main,
    validate_pre_stt_shadow_log,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _record(
    *,
    observed: bool = True,
    reason: str = "audio_bus_unavailable_observe_only",
    legacy_runtime_primary: bool = True,
    action_executed: bool = False,
    full_stt_prevented: bool = False,
) -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-27T21:30:00+00:00",
        "timestamp_monotonic": 123.45,
        "enabled": True,
        "observed": observed,
        "reason": reason,
        "legacy_runtime_primary": legacy_runtime_primary,
        "action_executed": action_executed,
        "full_stt_prevented": full_stt_prevented,
        "turn_id": "turn-pre-stt",
        "phase": "command",
        "capture_mode": "command",
        "input_owner": "voice_input",
        "source": "active_window",
        "audio_bus_available": False,
        "metadata": {
            "stage": "21C",
        },
    }


def test_validator_accepts_safe_observe_only_record(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record()])

    result = validate_pre_stt_shadow_log(
        path,
        require_observed=True,
    )

    assert result.accepted is True
    assert result.total_lines == 1
    assert result.valid_json_records == 1
    assert result.observed_records == 1
    assert result.not_observed_records == 0
    assert result.reasons == {"audio_bus_unavailable_observe_only": 1}
    assert result.phases == {"command": 1}
    assert result.capture_modes == {"command": 1}
    assert result.issues == ()


def test_validator_accepts_audio_bus_available_observe_only_record(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(
        path,
        [
            _record(
                reason="audio_bus_available_observe_only",
            )
        ],
    )

    result = validate_pre_stt_shadow_log(
        path,
        require_observed=True,
    )

    assert result.accepted is True
    assert result.reasons == {"audio_bus_available_observe_only": 1}


def test_validator_rejects_action_execution(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record(action_executed=True)])

    result = validate_pre_stt_shadow_log(path)

    assert result.accepted is False
    assert any(issue.code == "action_executed" for issue in result.issues)


def test_validator_rejects_full_stt_prevention(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record(full_stt_prevented=True)])

    result = validate_pre_stt_shadow_log(path)

    assert result.accepted is False
    assert any(issue.code == "full_stt_prevented" for issue in result.issues)


def test_validator_rejects_non_legacy_primary_record(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record(legacy_runtime_primary=False)])

    result = validate_pre_stt_shadow_log(path)

    assert result.accepted is False
    assert any(issue.code == "legacy_runtime_not_primary" for issue in result.issues)


def test_validator_rejects_disallowed_reason(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record(reason="pre_stt_shadow_not_safe")])

    result = validate_pre_stt_shadow_log(path)

    assert result.accepted is False
    assert any(issue.code == "reason_not_allowed" for issue in result.issues)


def test_validator_rejects_missing_required_field(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    record = _record()
    record.pop("full_stt_prevented")
    _write_jsonl(path, [record])

    result = validate_pre_stt_shadow_log(path)

    assert result.accepted is False
    assert any(issue.code == "missing_required_field" for issue in result.issues)


def test_validator_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    result = validate_pre_stt_shadow_log(path)

    assert result.accepted is False
    assert any(issue.code == "invalid_json" for issue in result.issues)


def test_validator_rejects_empty_log_by_default(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    path.write_text("", encoding="utf-8")

    result = validate_pre_stt_shadow_log(path)

    assert result.accepted is False
    assert any(issue.code == "no_records" for issue in result.issues)


def test_validator_allows_empty_log_when_requested(tmp_path: Path) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    path.write_text("", encoding="utf-8")

    result = validate_pre_stt_shadow_log(path, require_records=False)

    assert result.accepted is True
    assert result.valid_json_records == 0


def test_validator_rejects_when_observed_is_required_but_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record(observed=False)])

    result = validate_pre_stt_shadow_log(
        path,
        require_observed=True,
    )

    assert result.accepted is False
    assert any(issue.code == "no_observed_records" for issue in result.issues)


def test_cli_returns_zero_for_valid_log(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record()])

    exit_code = main(
        [
            "--log-path",
            str(path),
            "--require-observed",
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["accepted"] is True
    assert output["observed_records"] == 1


def test_cli_returns_one_for_invalid_log(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "pre_stt_shadow.jsonl"
    _write_jsonl(path, [_record(action_executed=True)])

    exit_code = main(["--log-path", str(path)])

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["accepted"] is False
    assert output["issues"][0]["code"] == "action_executed"