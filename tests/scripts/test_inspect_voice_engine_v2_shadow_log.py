from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = Path("scripts/inspect_voice_engine_v2_shadow_log.py")


def _load_script_module() -> ModuleType:
    module_name = "inspect_voice_engine_v2_shadow_log"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
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


def _record(
    *,
    transcript: str = "show desktop",
    legacy_route: str = "action",
    voice_engine_route: str = "action",
    legacy_intent_key: str = "visual_shell.show_desktop",
    voice_engine_intent_key: str = "visual_shell.show_desktop",
    language: str = "en",
    route_path: str = "fast_lane",
    fallback_reason: str = "",
    action_executed: bool = False,
    legacy_runtime_primary: bool = True,
    dispatch_ms: float = 3.0,
    speech_end_to_action_ms: float = 50.0,
) -> dict[str, object]:
    return {
        "turn_id": "turn-001",
        "transcript": transcript,
        "legacy_route": legacy_route,
        "voice_engine_route": voice_engine_route,
        "legacy_intent_key": legacy_intent_key,
        "voice_engine_intent_key": voice_engine_intent_key,
        "language": language,
        "fallback_reason": fallback_reason,
        "action_executed": action_executed,
        "legacy_runtime_primary": legacy_runtime_primary,
        "metadata": {
            "source": "legacy_runtime_transcript_tap",
            "route_path": route_path,
            "handled": True,
            "dispatch_ms": dispatch_ms,
            "speech_end_to_action_ms": speech_end_to_action_ms,
        },
    }


def test_inspect_shadow_log_reports_safe_records(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(log_path, [_record()])

    summary = module.inspect_shadow_log(log_path)

    assert summary["safety_ok"] is True
    assert summary["total_records"] == 1
    assert summary["valid_json_records"] == 1
    assert summary["action_executed_records"] == 0
    assert summary["non_legacy_primary_records"] == 0
    assert summary["empty_transcript_records"] == 0
    assert summary["intent_mismatch_records"] == 0
    assert summary["route_mismatch_records"] == 0
    assert summary["fallback_records"] == 0
    assert summary["counts"]["language"] == {"en": 1}
    assert summary["counts"]["route_path"] == {"fast_lane": 1}
    assert summary["latency"]["dispatch_ms"]["p50"] == 3.0
    assert summary["latency"]["speech_end_to_action_ms"]["p95"] == 50.0


def test_inspect_shadow_log_counts_intent_and_route_mismatch_samples(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                voice_engine_route="fallback",
                voice_engine_intent_key="fallback.conversation",
                fallback_reason="intent_not_confident",
            )
        ],
    )

    summary = module.inspect_shadow_log(log_path)

    assert summary["safety_ok"] is True
    assert summary["intent_mismatch_records"] == 1
    assert summary["route_mismatch_records"] == 1
    assert summary["fallback_records"] == 1
    assert summary["counts"]["fallback_reason"] == {"intent_not_confident": 1}
    assert len(summary["samples"]["intent_mismatch"]) == 1
    assert len(summary["samples"]["route_mismatch"]) == 1
    assert len(summary["samples"]["fallback"]) == 1


def test_inspect_shadow_log_marks_action_execution_as_safety_failure(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(log_path, [_record(action_executed=True)])

    summary = module.inspect_shadow_log(log_path)

    assert summary["safety_ok"] is False
    assert summary["action_executed_records"] == 1
    assert len(summary["samples"]["action_executed"]) == 1


def test_inspect_shadow_log_marks_non_legacy_primary_as_safety_failure(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(log_path, [_record(legacy_runtime_primary=False)])

    summary = module.inspect_shadow_log(log_path)

    assert summary["safety_ok"] is False
    assert summary["non_legacy_primary_records"] == 1
    assert len(summary["samples"]["non_legacy_primary"]) == 1


def test_inspect_shadow_log_marks_empty_transcript_as_safety_failure(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(log_path, [_record(transcript="")])

    summary = module.inspect_shadow_log(log_path)

    assert summary["safety_ok"] is False
    assert summary["empty_transcript_records"] == 1
    assert len(summary["samples"]["empty_transcript"]) == 1


def test_inspect_shadow_log_reports_invalid_json_as_load_issue(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    log_path.write_text("{not-json}\n", encoding="utf-8")

    summary = module.inspect_shadow_log(log_path)

    assert summary["safety_ok"] is False
    assert summary["total_records"] == 1
    assert summary["valid_json_records"] == 0
    assert summary["load_issue_count"] == 1
    assert summary["load_issues"][0]["code"] == "invalid_json"


def test_inspect_shadow_log_reports_missing_file(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "missing.jsonl"

    summary = module.inspect_shadow_log(log_path)

    assert summary["safety_ok"] is False
    assert summary["total_records"] == 1
    assert summary["valid_json_records"] == 0
    assert summary["load_issue_count"] == 1
    assert summary["load_issues"][0]["code"] == "file_missing"


def test_format_report_contains_core_sections(tmp_path: Path) -> None:
    module = _load_script_module()
    log_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    _write_jsonl(log_path, [_record()])

    summary = module.inspect_shadow_log(log_path)
    report = module.format_report(summary)

    assert "Voice Engine v2 shadow telemetry inspection" in report
    assert "safety_ok: True" in report
    assert "Languages:" in report
    assert "Route paths:" in report
    assert "Top legacy intents:" in report
    assert "Top Voice Engine intents:" in report
    assert "Latency dispatch_ms:" in report
    assert "Intent mismatch samples:" in report