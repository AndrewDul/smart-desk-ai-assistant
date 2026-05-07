from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = Path("scripts/check_focus_vision_dry_run_readiness.py")


def _load_script_module() -> ModuleType:
    module_name = "check_focus_vision_dry_run_readiness"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_settings(path: Path, focus_vision: dict[str, object]) -> None:
    path.write_text(json.dumps({"focus_vision": focus_vision}, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )


def test_readiness_passes_for_safe_dry_run_focus_vision(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    telemetry_path = tmp_path / "focus_vision.jsonl"
    _write_settings(
        settings_path,
        {
            "enabled": True,
            "dry_run": True,
            "voice_warnings_enabled": False,
            "pan_tilt_scan_enabled": False,
            "observation_interval_seconds": 1.0,
            "telemetry_path": str(telemetry_path),
        },
    )

    summary = module.inspect_focus_vision_dry_run_readiness(
        settings_path=settings_path,
        telemetry_path=telemetry_path,
    )

    assert summary["ok"] is True
    assert summary["failures"] == []
    assert summary["focus_vision"]["enabled"] is True
    assert summary["telemetry"]["exists"] is False


def test_readiness_fails_if_voice_or_pan_tilt_are_active(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    telemetry_path = tmp_path / "focus_vision.jsonl"
    _write_settings(
        settings_path,
        {
            "enabled": True,
            "dry_run": True,
            "voice_warnings_enabled": True,
            "pan_tilt_scan_enabled": True,
            "observation_interval_seconds": 1.0,
        },
    )

    summary = module.inspect_focus_vision_dry_run_readiness(
        settings_path=settings_path,
        telemetry_path=telemetry_path,
    )

    assert summary["ok"] is False
    assert any("voice_warnings_enabled" in failure for failure in summary["failures"])
    assert any("pan_tilt_scan_enabled" in failure for failure in summary["failures"])


def test_readiness_summarizes_focus_vision_telemetry(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    telemetry_path = tmp_path / "focus_vision.jsonl"
    _write_settings(
        settings_path,
        {
            "enabled": True,
            "dry_run": True,
            "voice_warnings_enabled": False,
            "pan_tilt_scan_enabled": False,
            "observation_interval_seconds": 1.0,
        },
    )
    _write_jsonl(
        telemetry_path,
        [
            {"snapshot": {"current_state": "on_task"}, "reminder": None},
            {
                "snapshot": {"current_state": "phone_distraction"},
                "reminder": {"kind": "phone_distraction"},
                "reminder_delivered": False,
            },
        ],
    )

    summary = module.inspect_focus_vision_dry_run_readiness(
        settings_path=settings_path,
        telemetry_path=telemetry_path,
        require_telemetry=True,
    )

    assert summary["ok"] is True
    assert summary["telemetry"]["valid_json_records"] == 2
    assert summary["telemetry"]["latest_state"] == "phone_distraction"
    assert summary["telemetry"]["reminder_candidate_count"] == 1
    assert summary["telemetry"]["states"] == {"on_task": 1, "phone_distraction": 1}
