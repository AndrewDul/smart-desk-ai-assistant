from __future__ import annotations

import json
import runpy
from pathlib import Path


def _settings_payload(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _defaults_payload() -> dict:
    namespace = runpy.run_path("modules/shared/config/settings_core/defaults.py")
    for value in namespace.values():
        if isinstance(value, dict) and "voice_input" in value:
            return value
    raise AssertionError("Could not find settings defaults dictionary.")


def _assert_safe_barge_in_defaults(payload: dict) -> None:
    voice_input = payload["voice_input"]

    assert voice_input["wake_barge_in_enabled"] is False
    assert voice_input["wake_barge_in_timeout_seconds"] == 0.35
    assert voice_input["wake_barge_in_min_output_age_seconds"] == 0.75
    assert voice_input["wake_barge_in_resume_timeout_seconds"] == 1.5
    assert voice_input["wake_barge_in_refractory_seconds"] == 1.5


def test_runtime_settings_disable_wake_barge_in_by_default() -> None:
    _assert_safe_barge_in_defaults(_settings_payload("config/settings.json"))


def test_example_settings_disable_wake_barge_in_by_default() -> None:
    _assert_safe_barge_in_defaults(_settings_payload("config/settings.example.json"))


def test_code_defaults_disable_wake_barge_in_by_default() -> None:
    _assert_safe_barge_in_defaults(_defaults_payload())
