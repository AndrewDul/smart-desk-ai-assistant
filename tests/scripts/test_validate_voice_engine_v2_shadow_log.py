from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = Path("scripts/validate_voice_engine_v2_shadow_log.py")


def _load_script_module() -> ModuleType:
    module_name = "validate_voice_engine_v2_shadow_log"
    spec = importlib.util.spec_from_file_location(
        module_name,
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )


def _valid_record() -> dict[str, object]:
    return {
        "turn_id": "turn-001",
        "transcript": "show desktop",
        "legacy_route": "action",
        "voice_engine_route": "action",
        "legacy_intent_key": "visual_shell.show_desktop",
        "voice_engine_intent_key": "visual_shell.show_desktop",
        "fallback_reason": "",
        "action_executed": False,
        "legacy_runtime_primary": True,
        "metadata": {
            "source": "legacy_runtime_transcript_tap",
            "route_path": "fast_lane",
            "handled": True,
        },
    }


def test_validate_shadow_log_accepts_safe_records(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(log_path, [_valid_record()])

    summary = module.validate_shadow_log(log_path)

    assert summary.accepted is True
    assert summary.total_records == 1
    assert summary.valid_json_records == 1
    assert summary.action_executed_records == 0
    assert summary.non_legacy_primary_records == 0
    assert summary.intent_mismatch_records == 0
    assert summary.route_mismatch_records == 0


def test_validate_shadow_log_rejects_action_execution(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    record = _valid_record()
    record["action_executed"] = True
    _write_jsonl(log_path, [record])

    summary = module.validate_shadow_log(log_path)

    assert summary.accepted is False
    assert summary.action_executed_records == 1
    assert any(issue.code == "shadow_action_executed" for issue in summary.issues)


def test_validate_shadow_log_rejects_non_legacy_primary_record(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    record = _valid_record()
    record["legacy_runtime_primary"] = False
    _write_jsonl(log_path, [record])

    summary = module.validate_shadow_log(log_path)

    assert summary.accepted is False
    assert summary.non_legacy_primary_records == 1
    assert any(issue.code == "legacy_not_primary" for issue in summary.issues)


def test_validate_shadow_log_rejects_missing_required_fields(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    record = _valid_record()
    record["transcript"] = ""
    record["legacy_route"] = ""
    record["legacy_intent_key"] = ""
    record["voice_engine_intent_key"] = ""
    _write_jsonl(log_path, [record])

    summary = module.validate_shadow_log(log_path)

    assert summary.accepted is False
    assert summary.empty_transcript_records == 1
    assert summary.missing_legacy_route_records == 1
    assert summary.missing_legacy_intent_records == 1
    assert summary.missing_voice_engine_intent_records == 1


def test_validate_shadow_log_counts_intent_and_route_mismatches(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    record = _valid_record()
    record["voice_engine_route"] = "fallback"
    record["voice_engine_intent_key"] = "fallback.conversation"
    _write_jsonl(log_path, [record])

    summary = module.validate_shadow_log(log_path)

    assert summary.accepted is True
    assert summary.intent_mismatch_records == 1
    assert summary.route_mismatch_records == 1


def test_validate_shadow_log_rejects_invalid_json(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    log_path.write_text("{not-json}\n", encoding="utf-8")

    summary = module.validate_shadow_log(log_path)

    assert summary.accepted is False
    assert summary.total_records == 1
    assert summary.invalid_json_records == 1
    assert any(issue.code == "invalid_json" for issue in summary.issues)


def test_validate_shadow_log_reports_missing_file(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "missing.jsonl"

    summary = module.validate_shadow_log(log_path)

    assert summary.accepted is True
    assert summary.total_records == 0
    assert len(summary.issues) == 1
    assert summary.issues[0].code == "file_missing"


def test_format_summary_contains_main_counters(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(log_path, [_valid_record()])

    summary = module.validate_shadow_log(log_path)
    output = module.format_summary(summary)

    assert "Voice Engine v2 shadow telemetry validation" in output
    assert "accepted: True" in output
    assert "total_records: 1" in output
    assert "action_executed_records: 0" in output