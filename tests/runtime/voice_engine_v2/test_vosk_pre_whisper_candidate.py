from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from modules.devices.audio.command_asr import CommandLanguage
from modules.devices.audio.command_asr.command_result import CommandRecognitionResult
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


class _FakeBilingualVoskCommandRecognizer:
    instances = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.pcm_calls = []
        self.__class__.instances.append(self)

    def recognize_pcm(self, pcm: bytes) -> CommandRecognitionResult:
        self.pcm_calls.append(pcm)
        first_sample = int.from_bytes(pcm[:2], byteorder="little", signed=True)
        if first_sample < 5_000:
            transcript = "what time is it"
            intent_key = "system.current_time"
        else:
            transcript = "what is the date"
            intent_key = "system.current_date"

        return CommandRecognitionResult.matched(
            transcript=transcript,
            normalized_transcript=transcript,
            language=CommandLanguage.ENGLISH,
            confidence=1.0,
            intent_key=intent_key,
            matched_phrase=transcript,
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


def test_vosk_pre_whisper_candidate_caches_default_command_asr_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.devices.audio.command_asr.bilingual_vosk_command_recognizer as bilingual_module

    _FakeBilingualVoskCommandRecognizer.instances = []
    monkeypatch.setattr(
        bilingual_module,
        "BilingualVoskCommandRecognizer",
        _FakeBilingualVoskCommandRecognizer,
    )
    runtime_candidate = _FakeRuntimeCandidateAdapter(accepted=True)
    adapter = VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=_settings(),
        runtime_candidate_adapter=runtime_candidate,
    )

    first = adapter.try_process_capture_window(
        audio=np.full(1600, 0.1, dtype=np.float32),
        turn_id="turn-first",
        sample_rate=16000,
        started_monotonic=1.0,
        speech_end_monotonic=1.1,
    )
    second = adapter.try_process_capture_window(
        audio=np.full(1600, 0.2, dtype=np.float32),
        turn_id="turn-second",
        sample_rate=16000,
        started_monotonic=2.0,
        speech_end_monotonic=2.1,
    )

    assert first.accepted is True
    assert first.transcript == "what time is it"
    assert second.accepted is True
    assert second.transcript == "what is the date"
    assert len(_FakeBilingualVoskCommandRecognizer.instances) == 1
    recognizer = _FakeBilingualVoskCommandRecognizer.instances[0]
    assert len(recognizer.pcm_calls) == 2
    assert recognizer.pcm_calls[0] != recognizer.pcm_calls[1]
    assert adapter._current_pcm is None


def test_vosk_pre_whisper_candidate_uses_injected_command_asr_adapter_without_cache() -> None:
    command_asr = _FakeCommandAsrAdapter()
    adapter = VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=_settings(),
        runtime_candidate_adapter=_FakeRuntimeCandidateAdapter(),
        command_asr_adapter=command_asr,
    )

    decision = adapter.try_process_capture_window(
        audio=np.zeros(1600, dtype=np.float32),
        turn_id="turn-injected",
        sample_rate=16000,
        started_monotonic=1.0,
        speech_end_monotonic=1.1,
    )

    assert decision.accepted is True
    assert len(command_asr.segments) == 1
    assert adapter._cached_command_asr_adapter is None
    assert adapter._current_pcm is None


def test_vosk_pre_whisper_candidate_fails_open_when_default_stack_build_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.devices.audio.command_asr.bilingual_vosk_command_recognizer as bilingual_module

    class BrokenBilingualVoskCommandRecognizer:
        def __init__(self, **kwargs) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        bilingual_module,
        "BilingualVoskCommandRecognizer",
        BrokenBilingualVoskCommandRecognizer,
    )
    adapter = VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=_settings(),
        runtime_candidate_adapter=_FakeRuntimeCandidateAdapter(),
    )

    decision = adapter.try_process_capture_window(
        audio=np.zeros(1600, dtype=np.float32),
        turn_id="turn-fail-open",
        sample_rate=16000,
        started_monotonic=1.0,
        speech_end_monotonic=1.1,
    )

    assert decision.attempted is False
    assert decision.accepted is False
    assert decision.reason == "vosk_command_asr_failed:RuntimeError"
    assert decision.metadata["error"] == "boom"
    assert adapter._current_pcm is None


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
