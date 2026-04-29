from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from modules.runtime.health.voice_checks import HealthVoiceChecks


class _VoiceHealthProbe(HealthVoiceChecks):
    def __init__(self, *, allow_espeak_fallback: bool) -> None:
        self.settings = {
            "voice_output": {
                "enabled": True,
                "engine": "piper",
                "allow_espeak_fallback": allow_espeak_fallback,
                "piper_models": {
                    "pl": {
                        "model": "missing/pl.onnx",
                        "config": "missing/pl.onnx.json",
                    },
                    "en": {
                        "model": "missing/en.onnx",
                        "config": "missing/en.onnx.json",
                    },
                },
            }
        }

    @staticmethod
    def _module_exists(module_name: str) -> bool:
        del module_name
        return True

    def _resolve_local_path(self, raw_path: str) -> Path:
        del raw_path
        return Path("/tmp/nexa_missing_piper_file_for_test")


def _fake_which(command: str) -> str | None:
    if command in {"espeak-ng", "espeak"}:
        return "/usr/bin/espeak-ng"
    if command in {"aplay", "python", "python3"}:
        return f"/usr/bin/{command}"
    return None


def test_voice_output_health_rejects_espeak_fallback_by_default() -> None:
    probe = _VoiceHealthProbe(allow_espeak_fallback=False)

    with patch("modules.runtime.health.voice_checks.shutil.which", side_effect=_fake_which):
        result = probe._check_voice_output()

    assert result.ok is False
    assert "eSpeak fallback disabled" in result.details


def test_voice_output_health_allows_espeak_only_when_explicitly_enabled() -> None:
    probe = _VoiceHealthProbe(allow_espeak_fallback=True)

    with patch("modules.runtime.health.voice_checks.shutil.which", side_effect=_fake_which):
        result = probe._check_voice_output()

    assert result.ok is True
    assert result.is_warning is True
    assert "eSpeak fallback available" in result.details
