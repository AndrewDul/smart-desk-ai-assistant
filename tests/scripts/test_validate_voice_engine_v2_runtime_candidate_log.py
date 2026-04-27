from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_runtime_candidate_log import (
    main,
    validate_runtime_candidate_log,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _accepted_record(
    *,
    intent: str = "system.current_time",
    primary_intent: str = "ask_time",
    transcript: str = "what time is it",
) -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-27T20:40:00+00:00",
        "turn_id": f"turn-{intent}",
        "transcript": transcript,
        "accepted": True,
        "reason": "accepted",
        "legacy_runtime_primary": True,
        "voice_engine_route": "command",
        "voice_engine_intent": intent,
        "voice_engine_action": "report_current_time"
        if intent == "system.current_time"
        else "introduce_self",
        "language": "en",
        "fallback_reason": "",
        "route_kind": "action",
        "primary_intent": primary_intent,
        "llm_prevented": True,
        "metrics": {
            "speech_end_to_finish_ms": 50.0,
            "fallback_used": False,
            "fallback_reason": "",
        },
        "metadata": {
            "source": "unit_test",
        },
    }


def _rejected_record() -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-27T20:40:01+00:00",
        "turn_id": "turn-ambiguous",
        "transcript": "So shall.",
        "accepted": False,
        "reason": "fallback_required:no_match",
        "legacy_runtime_primary": True,
        "voice_engine_route": "fallback",
        "voice_engine_intent": "",
        "voice_engine_action": "",
        "language": "en",
        "fallback_reason": "no_match",
        "route_kind": "",
        "primary_intent": "",
        "llm_prevented": False,
        "metrics": {
            "fallback_used": True,
            "fallback_reason": "no_match",
        },
        "metadata": {},
    }


def test_validator_accepts_safe_identity_and_time_records(tmp_path: Path) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    _write_jsonl(
        path,
        [
            _accepted_record(
                intent="assistant.identity",
                primary_intent="introduce_self",
                transcript="what is your name",
            ),
            _accepted_record(
                intent="system.current_time",
                primary_intent="ask_time",
                transcript="what time is it",
            ),
            _rejected_record(),
        ],
    )

    result = validate_runtime_candidate_log(
        path,
        required_accepted_intents=(
            "assistant.identity",
            "system.current_time",
        ),
    )

    assert result.accepted is True
    assert result.total_lines == 3
    assert result.valid_json_records == 3
    assert result.accepted_records == 2
    assert result.rejected_records == 1
    assert result.accepted_intents == {
        "assistant.identity": 1,
        "system.current_time": 1,
    }
    assert result.primary_intents == {
        "ask_time": 1,
        "introduce_self": 1,
    }


def test_validator_rejects_accepted_system_exit(tmp_path: Path) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    _write_jsonl(
        path,
        [
            _accepted_record(
                intent="system.exit",
                primary_intent="exit",
                transcript="exit",
            )
        ],
    )

    result = validate_runtime_candidate_log(path)

    assert result.accepted is False
    assert result.issues
    assert result.issues[0].code == "accepted_intent_not_allowed"


def test_validator_rejects_wrong_primary_intent_mapping(tmp_path: Path) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    _write_jsonl(
        path,
        [
            _accepted_record(
                intent="system.current_time",
                primary_intent="introduce_self",
            )
        ],
    )

    result = validate_runtime_candidate_log(path)

    assert result.accepted is False
    assert any(issue.code == "primary_intent_mismatch" for issue in result.issues)


def test_validator_rejects_accepted_record_without_llm_prevention(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    record = _accepted_record()
    record["llm_prevented"] = False
    _write_jsonl(path, [record])

    result = validate_runtime_candidate_log(path)

    assert result.accepted is False
    assert any(issue.code == "llm_not_prevented" for issue in result.issues)


def test_validator_rejects_accepted_record_without_legacy_primary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    record = _accepted_record()
    record["legacy_runtime_primary"] = False
    _write_jsonl(path, [record])

    result = validate_runtime_candidate_log(path)

    assert result.accepted is False
    assert any(issue.code == "legacy_runtime_not_primary" for issue in result.issues)


def test_validator_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    result = validate_runtime_candidate_log(path)

    assert result.accepted is False
    assert any(issue.code == "invalid_json" for issue in result.issues)


def test_validator_rejects_missing_required_intent(tmp_path: Path) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    _write_jsonl(
        path,
        [
            _accepted_record(
                intent="system.current_time",
                primary_intent="ask_time",
            )
        ],
    )

    result = validate_runtime_candidate_log(
        path,
        required_accepted_intents=(
            "assistant.identity",
            "system.current_time",
        ),
    )

    assert result.accepted is False
    assert result.missing_required_intents == ("assistant.identity",)
    assert any(
        issue.code == "missing_required_accepted_intent"
        for issue in result.issues
    )


def test_validator_allows_empty_log_when_requested(tmp_path: Path) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    path.write_text("", encoding="utf-8")

    result = validate_runtime_candidate_log(path, require_records=False)

    assert result.accepted is True
    assert result.valid_json_records == 0


def test_cli_returns_zero_for_valid_log(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    _write_jsonl(
        path,
        [
            _accepted_record(
                intent="assistant.identity",
                primary_intent="introduce_self",
                transcript="what is your name",
            )
        ],
    )

    exit_code = main(
        [
            "--log-path",
            str(path),
            "--require-accepted-intent",
            "assistant.identity",
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["accepted"] is True
    assert output["accepted_intents"] == {"assistant.identity": 1}


def test_cli_returns_one_for_invalid_log(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "runtime_candidates.jsonl"
    _write_jsonl(
        path,
        [
            _accepted_record(
                intent="system.exit",
                primary_intent="exit",
                transcript="exit",
            )
        ],
    )

    exit_code = main(["--log-path", str(path)])

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["accepted"] is False
    assert output["issues"][0]["code"] == "accepted_intent_not_allowed"