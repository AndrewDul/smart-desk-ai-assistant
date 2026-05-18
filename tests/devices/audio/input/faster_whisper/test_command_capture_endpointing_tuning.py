from pathlib import Path


CAPTURE_SOURCE = Path("modules/devices/audio/input/faster_whisper/backend/capture_mixin.py")
CORE_SOURCE = Path("modules/devices/audio/input/faster_whisper/backend/core.py")


def test_short_command_capture_has_fast_endpointing_profile() -> None:
    source = CAPTURE_SOURCE.read_text(encoding="utf-8")

    assert "fast_endpointing = (" in source
    assert "effective_end_silence <= 0.20" in source
    assert "effective_min_speech <= 0.10" in source
    assert "effective_pre_roll <= 0.14" in source
    assert "queue_read_timeout = 0.04 if fast_endpointing else 0.08" in source
    assert "trailing_chunk_multiplier = 1 if fast_endpointing else 2" in source
    assert "low_energy_break_chunks = 1 if fast_endpointing else 2" in source


def test_capture_endpointing_stays_intent_agnostic() -> None:
    source = CAPTURE_SOURCE.read_text(encoding="utf-8")

    assert "intent ==" not in source
    assert "primary_intent" not in source
    assert "system.current_time" not in source
    assert "assistant.identity" not in source


def test_conversation_repair_profile_has_longer_endpointing() -> None:
    source = CORE_SOURCE.read_text(encoding="utf-8")

    assert '"conversation_repair": self._merge_capture_profile(' in source
    assert '"timeout_seconds": max(base_profile["timeout_seconds"], 6.8)' in source
    assert '"end_silence_seconds": max(base_profile["end_silence_seconds"], 0.65)' in source
    assert '"pre_roll_seconds": max(base_profile["pre_roll_seconds"], 0.42)' in source
