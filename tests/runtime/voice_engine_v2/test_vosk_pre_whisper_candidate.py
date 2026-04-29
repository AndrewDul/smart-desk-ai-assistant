from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from modules.runtime.voice_engine_v2.vosk_pre_whisper_candidate import (
    VoiceEngineV2VoskPreWhisperCandidateAdapter,
)


def _settings(*, runtime_candidates_enabled: bool = True, pre_whisper_enabled: bool = True) -> dict[str, object]:
    return {
        "voice_engine": {
            "enabled": False,
            "version": "v2",
            "mode": "legacy",
            "command_first_enabled": False,
            "fallback_to_legacy_enabled": True,
            "runtime_candidates_enabled": runtime_candidates_enabled,
            "vosk_pre_whisper_candidate_enabled": pre_whisper_enabled,
            "runtime_candidate_intent_allowlist": [
                "assistant.identity",
                "system.current_time",
            ],
            "vosk_command_model_paths": {
                "en": "var/models/vosk/vosk-model-small-en-us-0.15",
                "pl": "var/models/vosk/vosk-model-small-pl-0.22",
            },
            "vosk_command_sample_rate": 16000,
        }
    }


class _FakeCommandAsrAdapter:
    def __init__(
        self,
        *,
        recognized: bool = True,
        transcript: str = "która jest godzina",
        normalized_text: str = "ktora jest godzina",
        language: str = "pl",
        confidence: float = 1.0,
    ) -> None:
        self.recognized = recognized
        self.transcript = transcript
        self.normalized_text = normalized_text
        self.language = language
        self.confidence = confidence
        self.segments = []

    def recognize(self, *, segment):
        self.segments.append(segment)
        return SimpleNamespace(
            recognizer_name="vosk_command_asr",
            recognizer_enabled=True,
            recognition_attempted=True,
            recognized=self.recognized,
            reason="vosk_command_asr_recognized"
            if self.recognized
            else "vosk_command_asr_not_recognized:no_match",
            transcript=self.transcript,
            normalized_text=self.normalized_text,
            language=self.language,
            confidence=self.confidence,
            alternatives=(),
        )


class _FakeRuntimeCandidateAdapter:
    def __init__(self, *, accepted: bool = True, reason: str = "accepted") -> None:
        self.accepted = accepted
        self.reason = reason
        self.calls = []

    def process_vosk_shadow_result(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            accepted=self.accepted,
            reason=self.reason,
        )


def test_vosk_pre_whisper_candidate_accepts_safe_polish_command() -> None:
    command_asr = _FakeCommandAsrAdapter()
    runtime_candidate = _FakeRuntimeCandidateAdapter(accepted=True)

    adapter = VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=_settings(),
        runtime_candidate_adapter=runtime_candidate,
        command_asr_adapter=command_asr,
    )

    decision = adapter.try_process_capture_window(
        audio=np.zeros(1600, dtype=np.float32),
        turn_id="turn-polish-time",
        sample_rate=16000,
        started_monotonic=1.0,
        speech_end_monotonic=1.1,
        capture_window_shadow_tap={
            "published": True,
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "published_frame_count": 2,
        },
        request_metadata={"source": "unit_test"},
    )

    assert decision.attempted is True
    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.language == "pl"
    assert decision.transcript == "która jest godzina"
    assert decision.normalized_text == "ktora jest godzina"
    assert command_asr.segments[0].raw_pcm_included is False
    assert command_asr.segments[0].action_executed is False
    assert command_asr.segments[0].runtime_takeover is False

    result_metadata = runtime_candidate.calls[0]["result_metadata"]
    assert result_metadata["raw_pcm_included"] is False
    assert result_metadata["action_executed"] is False
    assert result_metadata["runtime_takeover"] is False
    assert result_metadata["recognized"] is True
    assert result_metadata["command_matched"] is True


def test_vosk_pre_whisper_candidate_rejects_without_blocking_fallback() -> None:
    command_asr = _FakeCommandAsrAdapter(
        recognized=False,
        transcript="is | czas",
        normalized_text="is czas",
        language="unknown",
        confidence=0.0,
    )
    runtime_candidate = _FakeRuntimeCandidateAdapter(
        accepted=False,
        reason="vosk_shadow_result_not_recognized",
    )

    adapter = VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=_settings(),
        runtime_candidate_adapter=runtime_candidate,
        command_asr_adapter=command_asr,
    )

    decision = adapter.try_process_capture_window(
        audio=np.zeros(1600, dtype=np.float32),
        turn_id="turn-unknown",
        sample_rate=16000,
        started_monotonic=1.0,
        speech_end_monotonic=1.1,
    )

    assert decision.attempted is True
    assert decision.accepted is False
    assert decision.reason == "vosk_shadow_result_not_recognized"


def test_vosk_pre_whisper_candidate_stays_disabled_when_runtime_candidates_disabled() -> None:
    adapter = VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=_settings(runtime_candidates_enabled=False),
        runtime_candidate_adapter=_FakeRuntimeCandidateAdapter(),
        command_asr_adapter=_FakeCommandAsrAdapter(),
    )

    decision = adapter.try_process_capture_window(
        audio=np.zeros(1600, dtype=np.float32),
        turn_id="turn-disabled",
        sample_rate=16000,
        started_monotonic=1.0,
        speech_end_monotonic=1.1,
    )

    assert decision.attempted is False
    assert decision.accepted is False
    assert decision.reason == "not_safe:runtime_candidates_disabled"

def test_vosk_pre_whisper_candidate_stays_disabled_when_pre_whisper_flag_disabled() -> None:
    adapter = VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=_settings(pre_whisper_enabled=False),
        runtime_candidate_adapter=_FakeRuntimeCandidateAdapter(),
        command_asr_adapter=_FakeCommandAsrAdapter(),
    )

    decision = adapter.try_process_capture_window(
        audio=np.zeros(1600, dtype=np.float32),
        turn_id="turn-pre-whisper-disabled",
        sample_rate=16000,
        started_monotonic=1.0,
        speech_end_monotonic=1.1,
    )

    assert decision.attempted is False
    assert decision.accepted is False
    assert decision.reason == "not_safe:vosk_pre_whisper_candidate_disabled"

