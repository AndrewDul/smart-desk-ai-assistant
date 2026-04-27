from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


SCRIPT_PATH = Path("scripts/set_voice_engine_v2_shadow_mode.py")


def _load_script_module() -> ModuleType:
    module_name = "set_voice_engine_v2_shadow_mode"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _settings() -> dict[str, object]:
    return {
        "voice_engine": {
            "enabled": False,
            "mode": "legacy",
            "command_first_enabled": False,
            "fallback_to_legacy_enabled": True,
            "shadow_mode_enabled": False,
            "shadow_log_path": "var/data/voice_engine_v2_shadow.jsonl",
        }
    }


def _write_settings(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_settings(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_status_reports_safe_shadow_enable_state(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, _settings())

    result = module.main(["--settings", str(settings_path), "--status"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Voice Engine v2 shadow mode status" in output
    assert "safe_to_enable_shadow: True" in output
    assert "voice_engine.shadow_mode_enabled: False" in output


def test_enable_shadow_mode_updates_only_shadow_flag_and_creates_backup(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    original = _settings()
    _write_settings(settings_path, original)

    result = module.main(
        [
            "--settings",
            str(settings_path),
            "--backup-dir",
            str(backup_dir),
            "--enable",
        ]
    )

    updated = _read_settings(settings_path)
    backups = list(backup_dir.glob("settings.json.*.bak"))

    assert result == 0
    assert updated["voice_engine"]["shadow_mode_enabled"] is True
    assert updated["voice_engine"]["enabled"] is False
    assert updated["voice_engine"]["mode"] == "legacy"
    assert updated["voice_engine"]["command_first_enabled"] is False
    assert len(backups) == 1


def test_disable_shadow_mode_updates_only_shadow_flag_and_creates_backup(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    payload = _settings()
    payload["voice_engine"]["shadow_mode_enabled"] = True
    _write_settings(settings_path, payload)

    result = module.main(
        [
            "--settings",
            str(settings_path),
            "--backup-dir",
            str(backup_dir),
            "--disable",
        ]
    )

    updated = _read_settings(settings_path)
    backups = list(backup_dir.glob("settings.json.*.bak"))

    assert result == 0
    assert updated["voice_engine"]["shadow_mode_enabled"] is False
    assert updated["voice_engine"]["enabled"] is False
    assert updated["voice_engine"]["mode"] == "legacy"
    assert len(backups) == 1


def test_enable_shadow_mode_refuses_when_voice_engine_enabled_is_true(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    payload = _settings()
    payload["voice_engine"]["enabled"] = True
    _write_settings(settings_path, payload)

    result = module.main(["--settings", str(settings_path), "--enable"])

    updated = _read_settings(settings_path)
    assert result == 2
    assert updated["voice_engine"]["shadow_mode_enabled"] is False


def test_enable_shadow_mode_refuses_when_mode_is_not_legacy(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    payload = _settings()
    payload["voice_engine"]["mode"] = "v2"
    _write_settings(settings_path, payload)

    result = module.main(["--settings", str(settings_path), "--enable"])

    updated = _read_settings(settings_path)
    assert result == 2
    assert updated["voice_engine"]["shadow_mode_enabled"] is False


def test_enable_shadow_mode_refuses_when_command_first_is_enabled(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    payload = _settings()
    payload["voice_engine"]["command_first_enabled"] = True
    _write_settings(settings_path, payload)

    result = module.main(["--settings", str(settings_path), "--enable"])

    updated = _read_settings(settings_path)
    assert result == 2
    assert updated["voice_engine"]["shadow_mode_enabled"] is False


def test_dry_run_does_not_change_settings_or_create_backup(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    original = _settings()
    _write_settings(settings_path, original)

    result = module.main(
        [
            "--settings",
            str(settings_path),
            "--backup-dir",
            str(backup_dir),
            "--enable",
            "--dry-run",
        ]
    )

    updated = _read_settings(settings_path)
    assert result == 0
    assert updated == original
    assert not backup_dir.exists()


def test_archive_existing_shadow_log_moves_log_before_enabling(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    shadow_log_path = tmp_path / "voice_engine_v2_shadow.jsonl"

    payload = _settings()
    payload["voice_engine"]["shadow_log_path"] = str(shadow_log_path)
    _write_settings(settings_path, payload)
    shadow_log_path.write_text('{"old": true}\n', encoding="utf-8")

    result = module.main(
        [
            "--settings",
            str(settings_path),
            "--backup-dir",
            str(backup_dir),
            "--enable",
            "--archive-existing-log",
        ]
    )

    updated = _read_settings(settings_path)
    archived_logs = list(tmp_path.glob("voice_engine_v2_shadow.*.jsonl.bak"))

    assert result == 0
    assert updated["voice_engine"]["shadow_mode_enabled"] is True
    assert not shadow_log_path.exists()
    assert len(archived_logs) == 1


def test_missing_voice_engine_section_fails_safely(tmp_path: Path) -> None:
    module = _load_script_module()
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"project": {"name": "NeXa"}})

    with pytest.raises(ValueError, match="Missing required voice_engine config section"):
        module.main(["--settings", str(settings_path), "--status"])