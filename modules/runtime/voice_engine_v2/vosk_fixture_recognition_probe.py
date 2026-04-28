from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import time
import wave
from typing import Any

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
    normalize_command_text,
)
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)


VOSK_FIXTURE_RECOGNITION_PROBE_STAGE = "vosk_fixture_recognition_probe"
VOSK_FIXTURE_RECOGNITION_PROBE_VERSION = "stage_24ab_v1"

EXPECTED_SAMPLE_RATE = 16_000
EXPECTED_CHANNELS = 1
EXPECTED_SAMPLE_WIDTH_BYTES = 2

REQUIRED_MODEL_MARKERS: tuple[str, ...] = (
    "am/final.mdl",
    "conf/model.conf",
)

FixtureTranscriptProvider = Callable[[bytes, int, tuple[str, ...]], str]


@dataclass(frozen=True, slots=True)
class WavPcmFixture:
    wav_path: str
    sample_rate: int
    channels: int
    sample_width_bytes: int
    frame_count: int
    duration_ms: float
    pcm_byte_count: int
    pcm: bytes

    def metadata(self) -> dict[str, Any]:
        return {
            "wav_path": self.wav_path,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "frame_count": self.frame_count,
            "duration_ms": self.duration_ms,
            "pcm_byte_count": self.pcm_byte_count,
            "raw_pcm_included": False,
        }


@dataclass(frozen=True, slots=True)
class VoskFixtureRecognitionProbeResult:
    model_path: str
    wav_path: str
    model_exists: bool
    model_structure_ready: bool
    model_marker_status: dict[str, bool]
    wav_exists: bool
    wav_valid: bool
    wav_sample_rate: int | None
    wav_channels: int | None
    wav_sample_width_bytes: int | None
    wav_duration_ms: float | None
    wav_pcm_byte_count: int
    vocabulary_size: int
    fixture_recognition_attempted: bool
    fixture_recognition_success: bool
    transcript: str
    normalized_text: str
    command_matched: bool
    command_status: str
    command_language: str
    command_confidence: float
    command_intent_key: str | None
    command_matched_phrase: str | None
    command_alternatives: tuple[str, ...]
    elapsed_ms: float | None
    reason: str
    error: str = ""
    runtime_integration: bool = False
    command_execution_enabled: bool = False
    faster_whisper_bypass_enabled: bool = False
    microphone_stream_started: bool = False
    live_command_recognition_enabled: bool = False
    raw_pcm_included: bool = False
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.runtime_integration:
            raise ValueError("Fixture probe must never integrate with runtime")
        if self.command_execution_enabled or self.action_executed:
            raise ValueError("Fixture probe must never execute commands")
        if self.faster_whisper_bypass_enabled or self.full_stt_prevented:
            raise ValueError("Fixture probe must never bypass FasterWhisper")
        if self.microphone_stream_started:
            raise ValueError("Fixture probe must never start a microphone stream")
        if self.live_command_recognition_enabled:
            raise ValueError("Fixture probe must never enable live command recognition")
        if self.raw_pcm_included:
            raise ValueError("Fixture probe telemetry must not include raw PCM")
        if self.runtime_takeover:
            raise ValueError("Fixture probe must never take over runtime")
        object.__setattr__(self, "model_marker_status", dict(self.model_marker_status))
        object.__setattr__(
            self,
            "command_alternatives",
            tuple(self.command_alternatives),
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "wav_path": self.wav_path,
            "model_exists": self.model_exists,
            "model_structure_ready": self.model_structure_ready,
            "model_marker_status": dict(self.model_marker_status),
            "wav_exists": self.wav_exists,
            "wav_valid": self.wav_valid,
            "wav_sample_rate": self.wav_sample_rate,
            "wav_channels": self.wav_channels,
            "wav_sample_width_bytes": self.wav_sample_width_bytes,
            "wav_duration_ms": self.wav_duration_ms,
            "wav_pcm_byte_count": self.wav_pcm_byte_count,
            "vocabulary_size": self.vocabulary_size,
            "fixture_recognition_attempted": self.fixture_recognition_attempted,
            "fixture_recognition_success": self.fixture_recognition_success,
            "transcript": self.transcript,
            "normalized_text": self.normalized_text,
            "command_matched": self.command_matched,
            "command_status": self.command_status,
            "command_language": self.command_language,
            "command_confidence": self.command_confidence,
            "command_intent_key": self.command_intent_key,
            "command_matched_phrase": self.command_matched_phrase,
            "command_alternatives": list(self.command_alternatives),
            "elapsed_ms": self.elapsed_ms,
            "reason": self.reason,
            "error": self.error,
            "runtime_integration": self.runtime_integration,
            "command_execution_enabled": self.command_execution_enabled,
            "faster_whisper_bypass_enabled": self.faster_whisper_bypass_enabled,
            "microphone_stream_started": self.microphone_stream_started,
            "live_command_recognition_enabled": self.live_command_recognition_enabled,
            "raw_pcm_included": self.raw_pcm_included,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def probe_vosk_fixture_recognition(
    *,
    model_path: Path,
    wav_path: Path,
    transcript_provider: FixtureTranscriptProvider | None = None,
) -> VoskFixtureRecognitionProbeResult:
    started = time.perf_counter()

    grammar = build_default_command_grammar()
    vocabulary = grammar.to_vosk_vocabulary()

    model_path = Path(model_path)
    wav_path = Path(wav_path)

    model_exists, model_marker_status, model_structure_ready = _model_status(model_path)

    if not model_exists:
        return _result(
            model_path=model_path,
            wav_path=wav_path,
            model_exists=False,
            model_marker_status=model_marker_status,
            model_structure_ready=False,
            vocabulary_size=len(vocabulary),
            reason="model_path_missing",
            started=started,
        )

    if not model_structure_ready:
        return _result(
            model_path=model_path,
            wav_path=wav_path,
            model_exists=True,
            model_marker_status=model_marker_status,
            model_structure_ready=False,
            vocabulary_size=len(vocabulary),
            reason="model_structure_incomplete",
            started=started,
        )

    fixture_result = _load_wav_pcm_fixture(wav_path)
    if isinstance(fixture_result, VoskFixtureRecognitionProbeResult):
        return fixture_result

    fixture = fixture_result

    try:
        transcript = (
            transcript_provider(fixture.pcm, fixture.sample_rate, vocabulary)
            if transcript_provider is not None
            else _recognize_fixture_with_vosk(
                model_path=model_path,
                fixture=fixture,
                vocabulary=vocabulary,
            )
        )
    except Exception as error:
        return _result(
            model_path=model_path,
            wav_path=wav_path,
            model_exists=True,
            model_marker_status=model_marker_status,
            model_structure_ready=True,
            wav_exists=True,
            wav_valid=True,
            wav_sample_rate=fixture.sample_rate,
            wav_channels=fixture.channels,
            wav_sample_width_bytes=fixture.sample_width_bytes,
            wav_duration_ms=fixture.duration_ms,
            wav_pcm_byte_count=fixture.pcm_byte_count,
            vocabulary_size=len(vocabulary),
            fixture_recognition_attempted=True,
            reason="fixture_recognition_failed",
            error=f"{type(error).__name__}:{error}",
            started=started,
        )

    normalized = normalize_command_text(transcript)
    command_result = grammar.match(transcript)

    return _result_from_command_match(
        model_path=model_path,
        wav_path=wav_path,
        model_marker_status=model_marker_status,
        fixture=fixture,
        vocabulary_size=len(vocabulary),
        transcript=transcript,
        normalized=normalized,
        command_result=command_result,
        started=started,
    )


def validate_vosk_fixture_recognition_result(
    *,
    result: VoskFixtureRecognitionProbeResult,
    require_command_match: bool = False,
) -> dict[str, Any]:
    payload = result.to_json_dict()
    issues: list[str] = []

    if not payload["model_exists"]:
        issues.append("model_path_missing")
    if not payload["model_structure_ready"]:
        issues.append("model_structure_not_ready")
    if not payload["wav_exists"]:
        issues.append("wav_path_missing")
    if not payload["wav_valid"]:
        issues.append("wav_not_valid_for_fixture_probe")
    if not payload["fixture_recognition_attempted"]:
        issues.append("fixture_recognition_not_attempted")
    if require_command_match and not payload["command_matched"]:
        issues.append("command_match_missing")

    _append_if_true(issues, payload, "runtime_integration")
    _append_if_true(issues, payload, "command_execution_enabled")
    _append_if_true(issues, payload, "faster_whisper_bypass_enabled")
    _append_if_true(issues, payload, "microphone_stream_started")
    _append_if_true(issues, payload, "live_command_recognition_enabled")
    _append_if_true(issues, payload, "raw_pcm_included")
    _append_if_true(issues, payload, "action_executed")
    _append_if_true(issues, payload, "full_stt_prevented")
    _append_if_true(issues, payload, "runtime_takeover")

    return {
        "accepted": not issues,
        "probe_stage": VOSK_FIXTURE_RECOGNITION_PROBE_STAGE,
        "probe_version": VOSK_FIXTURE_RECOGNITION_PROBE_VERSION,
        "require_command_match": require_command_match,
        "issues": issues,
        "result": payload,
    }


def _model_status(model_path: Path) -> tuple[bool, dict[str, bool], bool]:
    exists = model_path.exists() and model_path.is_dir()
    marker_status = {
        marker: (model_path / marker).exists()
        for marker in REQUIRED_MODEL_MARKERS
    }
    return exists, marker_status, bool(exists and all(marker_status.values()))


def _load_wav_pcm_fixture(
    wav_path: Path,
) -> WavPcmFixture | VoskFixtureRecognitionProbeResult:
    if not wav_path.exists() or not wav_path.is_file():
        return _result(
            model_path=Path(""),
            wav_path=wav_path,
            model_exists=True,
            model_structure_ready=True,
            model_marker_status={},
            wav_exists=False,
            reason="wav_path_missing",
        )

    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()

            if channels != EXPECTED_CHANNELS:
                return _invalid_wav_result(
                    wav_path=wav_path,
                    channels=channels,
                    sample_width=sample_width,
                    sample_rate=sample_rate,
                    frame_count=frame_count,
                    reason="wav_not_mono",
                )

            if sample_width != EXPECTED_SAMPLE_WIDTH_BYTES:
                return _invalid_wav_result(
                    wav_path=wav_path,
                    channels=channels,
                    sample_width=sample_width,
                    sample_rate=sample_rate,
                    frame_count=frame_count,
                    reason="wav_not_pcm16",
                )

            if sample_rate != EXPECTED_SAMPLE_RATE:
                return _invalid_wav_result(
                    wav_path=wav_path,
                    channels=channels,
                    sample_width=sample_width,
                    sample_rate=sample_rate,
                    frame_count=frame_count,
                    reason="wav_sample_rate_unsupported",
                )

            if frame_count <= 0:
                return _invalid_wav_result(
                    wav_path=wav_path,
                    channels=channels,
                    sample_width=sample_width,
                    sample_rate=sample_rate,
                    frame_count=frame_count,
                    reason="wav_empty",
                )

            pcm = wav_file.readframes(frame_count)

    except wave.Error as error:
        return _result(
            model_path=Path(""),
            wav_path=wav_path,
            model_exists=True,
            model_structure_ready=True,
            model_marker_status={},
            wav_exists=True,
            wav_valid=False,
            reason="wav_read_failed",
            error=f"WaveError:{error}",
        )

    duration_ms = (frame_count / sample_rate) * 1000.0

    return WavPcmFixture(
        wav_path=str(wav_path),
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
        frame_count=frame_count,
        duration_ms=round(duration_ms, 3),
        pcm_byte_count=len(pcm),
        pcm=pcm,
    )


def _recognize_fixture_with_vosk(
    *,
    model_path: Path,
    fixture: WavPcmFixture,
    vocabulary: tuple[str, ...],
) -> str:
    vosk_module = importlib.import_module("vosk")

    set_log_level = getattr(vosk_module, "SetLogLevel", None)
    if callable(set_log_level):
        set_log_level(-1)

    model_class = getattr(vosk_module, "Model", None)
    recognizer_class = getattr(vosk_module, "KaldiRecognizer", None)

    if model_class is None:
        raise RuntimeError("vosk_model_class_missing")
    if recognizer_class is None:
        raise RuntimeError("vosk_kaldi_recognizer_class_missing")

    model = model_class(str(model_path))
    recognizer = recognizer_class(
        model,
        fixture.sample_rate,
        json.dumps(list(vocabulary), ensure_ascii=False),
    )

    chunk_size = 4000
    for offset in range(0, len(fixture.pcm), chunk_size):
        recognizer.AcceptWaveform(fixture.pcm[offset : offset + chunk_size])

    raw_result = recognizer.FinalResult()
    parsed = json.loads(raw_result)
    transcript = parsed.get("text", "")
    return str(transcript or "").strip()


def _result_from_command_match(
    *,
    model_path: Path,
    wav_path: Path,
    model_marker_status: dict[str, bool],
    fixture: WavPcmFixture,
    vocabulary_size: int,
    transcript: str,
    normalized: str,
    command_result: CommandRecognitionResult,
    started: float,
) -> VoskFixtureRecognitionProbeResult:
    command_matched = command_result.status is CommandRecognitionStatus.MATCHED
    reason = "command_matched" if command_matched else "command_not_matched"

    return _result(
        model_path=model_path,
        wav_path=wav_path,
        model_exists=True,
        model_marker_status=model_marker_status,
        model_structure_ready=True,
        wav_exists=True,
        wav_valid=True,
        wav_sample_rate=fixture.sample_rate,
        wav_channels=fixture.channels,
        wav_sample_width_bytes=fixture.sample_width_bytes,
        wav_duration_ms=fixture.duration_ms,
        wav_pcm_byte_count=fixture.pcm_byte_count,
        vocabulary_size=vocabulary_size,
        fixture_recognition_attempted=True,
        fixture_recognition_success=bool(transcript.strip()),
        transcript=transcript,
        normalized_text=normalized,
        command_matched=command_matched,
        command_status=command_result.status.value,
        command_language=command_result.language.value,
        command_confidence=command_result.confidence,
        command_intent_key=command_result.intent_key,
        command_matched_phrase=command_result.matched_phrase,
        command_alternatives=command_result.alternatives,
        reason=reason,
        started=started,
    )


def _invalid_wav_result(
    *,
    wav_path: Path,
    channels: int,
    sample_width: int,
    sample_rate: int,
    frame_count: int,
    reason: str,
) -> VoskFixtureRecognitionProbeResult:
    duration_ms = (frame_count / sample_rate) * 1000.0 if sample_rate > 0 else None

    return _result(
        model_path=Path(""),
        wav_path=wav_path,
        model_exists=True,
        model_structure_ready=True,
        model_marker_status={},
        wav_exists=True,
        wav_valid=False,
        wav_sample_rate=sample_rate,
        wav_channels=channels,
        wav_sample_width_bytes=sample_width,
        wav_duration_ms=round(duration_ms, 3) if duration_ms is not None else None,
        reason=reason,
    )


def _result(
    *,
    model_path: Path,
    wav_path: Path,
    model_exists: bool,
    model_structure_ready: bool,
    model_marker_status: dict[str, bool],
    reason: str,
    started: float | None = None,
    wav_exists: bool = False,
    wav_valid: bool = False,
    wav_sample_rate: int | None = None,
    wav_channels: int | None = None,
    wav_sample_width_bytes: int | None = None,
    wav_duration_ms: float | None = None,
    wav_pcm_byte_count: int = 0,
    vocabulary_size: int = 0,
    fixture_recognition_attempted: bool = False,
    fixture_recognition_success: bool = False,
    transcript: str = "",
    normalized_text: str = "",
    command_matched: bool = False,
    command_status: str = "not_attempted",
    command_language: str = "unknown",
    command_confidence: float = 0.0,
    command_intent_key: str | None = None,
    command_matched_phrase: str | None = None,
    command_alternatives: tuple[str, ...] = (),
    error: str = "",
) -> VoskFixtureRecognitionProbeResult:
    elapsed_ms = (
        round((time.perf_counter() - started) * 1000.0, 3)
        if started is not None
        else None
    )

    return VoskFixtureRecognitionProbeResult(
        model_path=str(model_path),
        wav_path=str(wav_path),
        model_exists=model_exists,
        model_structure_ready=model_structure_ready,
        model_marker_status=model_marker_status,
        wav_exists=wav_exists,
        wav_valid=wav_valid,
        wav_sample_rate=wav_sample_rate,
        wav_channels=wav_channels,
        wav_sample_width_bytes=wav_sample_width_bytes,
        wav_duration_ms=wav_duration_ms,
        wav_pcm_byte_count=wav_pcm_byte_count,
        vocabulary_size=vocabulary_size,
        fixture_recognition_attempted=fixture_recognition_attempted,
        fixture_recognition_success=fixture_recognition_success,
        transcript=transcript,
        normalized_text=normalized_text,
        command_matched=command_matched,
        command_status=command_status,
        command_language=command_language,
        command_confidence=command_confidence,
        command_intent_key=command_intent_key,
        command_matched_phrase=command_matched_phrase,
        command_alternatives=command_alternatives,
        elapsed_ms=elapsed_ms,
        reason=reason,
        error=error,
    )


def _append_if_true(
    issues: list[str],
    payload: dict[str, Any],
    field_name: str,
) -> None:
    if bool(payload.get(field_name, False)):
        issues.append(f"{field_name}_must_be_false")


__all__ = [
    "EXPECTED_CHANNELS",
    "EXPECTED_SAMPLE_RATE",
    "EXPECTED_SAMPLE_WIDTH_BYTES",
    "FixtureTranscriptProvider",
    "REQUIRED_MODEL_MARKERS",
    "VOSK_FIXTURE_RECOGNITION_PROBE_STAGE",
    "VOSK_FIXTURE_RECOGNITION_PROBE_VERSION",
    "VoskFixtureRecognitionProbeResult",
    "WavPcmFixture",
    "probe_vosk_fixture_recognition",
    "validate_vosk_fixture_recognition_result",
]