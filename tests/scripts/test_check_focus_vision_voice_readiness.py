from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = Path("scripts/check_focus_vision_voice_readiness.py")


def _load_script_module() -> ModuleType:
    module_name = "check_focus_vision_voice_readiness"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_settings(path: Path, focus_vision: dict[str, object]) -> None:
    path.write_text(json.dumps({"focus_vision": focus_vision}, sort_keys=True), encoding="utf-8")


def test_voice_readiness_passes_for_phone_only_voice(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {
            "enabled": True,
            "dry_run": False,
            "voice_warnings_enabled": True,
            "pan_tilt_scan_enabled": False,
            "enabled_reminder_kinds": ["phone_distraction"],
        },
    )

    summary = module.inspect_focus_vision_voice_readiness(settings_path=settings_path)

    assert summary["ok"] is True
    assert summary["failures"] == []
    assert summary["focus_vision"]["enabled_reminder_kinds"] == ["phone_distraction"]


def test_voice_readiness_blocks_absence_voice_by_default(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {
            "enabled": True,
            "dry_run": False,
            "voice_warnings_enabled": True,
            "pan_tilt_scan_enabled": False,
            "enabled_reminder_kinds": ["absence", "phone_distraction"],
        },
    )

    summary = module.inspect_focus_vision_voice_readiness(settings_path=settings_path)

    assert summary["ok"] is False
    assert any("absence" in failure for failure in summary["failures"])


def test_voice_readiness_blocks_pan_tilt_during_sprint_7(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {
            "enabled": True,
            "dry_run": False,
            "voice_warnings_enabled": True,
            "pan_tilt_scan_enabled": True,
            "enabled_reminder_kinds": ["phone_distraction"],
        },
    )

    summary = module.inspect_focus_vision_voice_readiness(settings_path=settings_path)

    assert summary["ok"] is False
    assert any("pan_tilt_scan_enabled" in failure for failure in summary["failures"])
