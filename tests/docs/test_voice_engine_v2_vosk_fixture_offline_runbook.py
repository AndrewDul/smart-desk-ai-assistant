from __future__ import annotations

from pathlib import Path


RUNBOOK_PATH = Path(
    "docs/validation/voice-engine-v2-vosk-fixture-offline-acceptance-runbook.md"
)


def test_vosk_fixture_offline_runbook_exists() -> None:
    assert RUNBOOK_PATH.exists()
    assert RUNBOOK_PATH.is_file()


def test_vosk_fixture_offline_runbook_documents_required_commands() -> None:
    content = RUNBOOK_PATH.read_text(encoding="utf-8")

    required_commands = [
        "scripts/manage_voice_engine_v2_command_fixtures.py validate",
        "scripts/run_voice_engine_v2_vosk_fixture_matrix.py",
        "scripts/check_voice_engine_v2_vosk_fixture_matrix_quality.py",
        "pytest -q tests/runtime/voice_engine_v2/test_vosk_fixture_quality_gate.py",
        "git check-ignore -v var/data/stage24ah_vosk_fixture_quality_gate.json",
    ]

    for command in required_commands:
        assert command in content


def test_vosk_fixture_offline_runbook_documents_safe_runtime_defaults() -> None:
    content = RUNBOOK_PATH.read_text(encoding="utf-8")

    required_safe_defaults = [
        "voice_engine.enabled=false",
        "voice_engine.mode=legacy",
        "voice_engine.command_first_enabled=false",
        "voice_engine.fallback_to_legacy_enabled=true",
        "voice_engine.runtime_candidates_enabled=false",
        "voice_engine.pre_stt_shadow_enabled=false",
        "voice_engine.faster_whisper_audio_bus_tap_enabled=false",
        "voice_engine.vad_shadow_enabled=false",
        "voice_engine.vad_timing_bridge_enabled=false",
        "voice_engine.command_asr_shadow_bridge_enabled=false",
    ]

    for setting in required_safe_defaults:
        assert setting in content


def test_vosk_fixture_offline_runbook_documents_safety_boundaries() -> None:
    content = RUNBOOK_PATH.read_text(encoding="utf-8")

    forbidden_runtime_actions = [
        "execute commands",
        "bypass FasterWhisper",
        "start live Voice Engine v2 microphone recognition",
        "change wake word",
        "change audio input",
        "change TTS",
        "change Visual Shell",
        "enable Voice Engine v2 runtime takeover",
        "connect Vosk recognition to live runtime",
    ]

    for action in forbidden_runtime_actions:
        assert action in content


def test_vosk_fixture_offline_runbook_documents_acceptance_criteria() -> None:
    content = RUNBOOK_PATH.read_text(encoding="utf-8")

    required_acceptance_markers = [
        "fixture inventory accepted=true",
        "matrix accepted=true",
        "quality gate accepted=true",
        "issues=[]",
        "tests passed",
        "cleanup checks confirm generated assets are ignored",
        "docs/architecture_notes.md updated",
    ]

    for marker in required_acceptance_markers:
        assert marker in content