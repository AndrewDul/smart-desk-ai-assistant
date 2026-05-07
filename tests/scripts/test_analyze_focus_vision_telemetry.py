from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path("scripts/analyze_focus_vision_telemetry.py")


def _load_script_module() -> ModuleType:
    module_name = "analyze_focus_vision_telemetry"
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
    created_at: float,
    state: str,
    stable_seconds: float = 0.0,
    dry_run: bool = True,
    reminder: dict[str, object] | None = None,
    reminder_delivered: bool = False,
    last_error: str | None = None,
    latest_observation_force_refresh: bool = False,
    observation_stale: bool = False,
    evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "created_at": created_at,
        "dry_run": dry_run,
        "last_error": last_error,
        "latest_observation_force_refresh": latest_observation_force_refresh,
        "observation_stale": observation_stale,
        "reminder": reminder,
        "reminder_delivered": reminder_delivered,
        "snapshot": {
            "current_state": state,
            "stable_seconds": stable_seconds,
            "decision": {
                "reasons": [f"{state}_reason"],
                "evidence": evidence or {},
            },
        },
    }


def test_analyzer_summarizes_states_reminders_and_evidence(tmp_path: Path) -> None:
    module = _load_script_module()
    telemetry_path = tmp_path / "focus_vision.jsonl"
    _write_jsonl(
        telemetry_path,
        [
            _record(
                created_at=10.0,
                state="on_task",
                stable_seconds=1.0,
                evidence={"presence_active": True, "desk_activity_active": True},
            ),
            _record(
                created_at=11.0,
                state="phone_distraction",
                stable_seconds=10.0,
                reminder={"kind": "phone_distraction"},
                evidence={"presence_active": True, "phone_usage_active": True},
            ),
            _record(created_at=12.0, state="absent", stable_seconds=25.0, reminder={"kind": "absence"}),
        ],
    )

    analysis = module.analyze_focus_vision_telemetry(
        telemetry_path,
        require_records=True,
        require_states=("absent", "phone_distraction"),
    )
    payload = analysis.to_dict()

    assert payload["ok"] is True
    assert payload["valid_records"] == 3
    assert payload["duration_seconds"] == 2.0
    assert payload["state_counts"] == {"absent": 1, "on_task": 1, "phone_distraction": 1}
    assert payload["max_stable_seconds_by_state"] == {
        "absent": 25.0,
        "on_task": 1.0,
        "phone_distraction": 10.0,
    }
    assert payload["reminder_candidate_counts"] == {"absence": 1, "phone_distraction": 1}
    assert payload["latest_observation_force_refresh_values"] == {"false": 3}
    assert payload["observation_stale_values"] == {"false": 3}
    assert payload["evidence_true_counts"] == {
        "desk_activity_active": 1,
        "phone_usage_active": 1,
        "presence_active": 2,
    }
    assert payload["failures"] == []


def test_analyzer_fails_when_required_records_or_states_are_missing(tmp_path: Path) -> None:
    module = _load_script_module()
    telemetry_path = tmp_path / "missing.jsonl"

    analysis = module.analyze_focus_vision_telemetry(
        telemetry_path,
        require_records=True,
        require_states=("absent",),
    )
    payload = analysis.to_dict()

    assert payload["ok"] is False
    assert "No valid Focus Vision telemetry records were found." in payload["failures"]
    assert "Required Focus Vision state was not observed: absent" in payload["failures"]


def test_analyzer_flags_non_dry_run_records_by_default(tmp_path: Path) -> None:
    module = _load_script_module()
    telemetry_path = tmp_path / "focus_vision.jsonl"
    _write_jsonl(telemetry_path, [_record(created_at=1.0, state="absent", dry_run=False)])

    analysis = module.analyze_focus_vision_telemetry(telemetry_path, require_records=True)

    assert analysis.ok is False
    assert "Unexpected dry_run=false records were found." in analysis.failures


def test_analyzer_warns_about_invalid_lines_and_large_gaps(tmp_path: Path) -> None:
    module = _load_script_module()
    telemetry_path = tmp_path / "focus_vision.jsonl"
    telemetry_path.write_text(
        json.dumps(_record(created_at=1.0, state="on_task"))
        + "\nnot-json\n"
        + json.dumps(_record(created_at=10.0, state="on_task"))
        + "\n",
        encoding="utf-8",
    )

    analysis = module.analyze_focus_vision_telemetry(
        telemetry_path,
        require_records=True,
        max_expected_gap_seconds=3.0,
    )

    assert analysis.ok is True
    assert any("invalid JSONL" in warning for warning in analysis.warnings)
    assert any("Largest telemetry gap" in warning for warning in analysis.warnings)


def test_analyzer_warns_about_force_refresh_and_stale_observations(tmp_path: Path) -> None:
    module = _load_script_module()
    telemetry_path = tmp_path / "focus_vision.jsonl"
    _write_jsonl(
        telemetry_path,
        [
            _record(
                created_at=1.0,
                state="on_task",
                latest_observation_force_refresh=True,
                observation_stale=True,
            )
        ],
    )

    analysis = module.analyze_focus_vision_telemetry(telemetry_path, require_records=True)
    payload = analysis.to_dict()

    assert payload["latest_observation_force_refresh_values"] == {"true": 1}
    assert payload["observation_stale_values"] == {"true": 1}
    assert any("latest_observation_force_refresh=true" in warning for warning in payload["warnings"])
    assert any("stale observations" in warning for warning in payload["warnings"])
