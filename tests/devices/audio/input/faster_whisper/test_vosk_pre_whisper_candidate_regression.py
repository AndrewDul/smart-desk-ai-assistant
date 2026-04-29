from __future__ import annotations

from pathlib import Path


def test_vosk_pre_whisper_transcript_result_does_not_reference_stale_local() -> None:
    source = Path(
        "modules/devices/audio/input/faster_whisper/backend/core.py"
    ).read_text(encoding="utf-8")

    function_start = source.index(
        "    def _transcript_result_from_vosk_pre_whisper_candidate("
    )

    try:
        function_end = source.index("\n    def ", function_start + 1)
    except ValueError:
        function_end = len(source)

    function_body = source[function_start:function_end]

    assert "if pre_whisper_candidate:" not in function_body
    assert "pre_whisper_candidate,\n" not in function_body
    assert 'metadata.setdefault("voice_engine_v2_pre_whisper_candidate", candidate)' in function_body
