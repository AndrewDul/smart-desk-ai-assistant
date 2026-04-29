from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any, Mapping

from modules.devices.audio.command_asr.bilingual_vosk_command_recognizer import (
    BilingualVoskCommandRecognizer,
    DEFAULT_ENGLISH_VOSK_MODEL_PATH,
    DEFAULT_POLISH_VOSK_MODEL_PATH,
)
from modules.runtime.voice_engine_v2.command_asr_shadow_bridge import (
    COMMAND_ASR_SHADOW_BRIDGE_STAGE,
    COMMAND_ASR_SHADOW_BRIDGE_VERSION,
    CommandAsrShadowBridgeSettings,
    enrich_record_with_command_asr_shadow,
)
from modules.runtime.voice_engine_v2.vosk_command_asr_adapter import (
    VoskCommandAsrAdapter,
    VoskCommandAsrAdapterSettings,
)
from modules.runtime.voice_engine_v2.vad_endpointing_candidate import (
    build_vad_endpointing_candidate,
)
from modules.runtime.voice_engine_v2.vosk_live_shadow_contract import (
    VOSK_LIVE_SHADOW_CONTRACT_STAGE,
    VOSK_LIVE_SHADOW_CONTRACT_VERSION,
    VoskLiveShadowContractSettings,
    build_vosk_live_shadow_contract,
)
from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (
    VOSK_SHADOW_INVOCATION_PLAN_STAGE,
    VOSK_SHADOW_INVOCATION_PLAN_VERSION,
    VoskShadowInvocationPlanSettings,
    build_vosk_shadow_invocation_plan,
)
from modules.runtime.voice_engine_v2.vosk_shadow_pcm_reference import (
    VOSK_SHADOW_PCM_REFERENCE_STAGE,
    VOSK_SHADOW_PCM_REFERENCE_VERSION,
    VoskShadowPcmReferenceSettings,
    build_vosk_shadow_pcm_reference,
)
from modules.runtime.voice_engine_v2.vosk_shadow_asr_result import (
    VOSK_SHADOW_ASR_RESULT_STAGE,
    VOSK_SHADOW_ASR_RESULT_VERSION,
    VoskShadowAsrResultSettings,
    build_vosk_shadow_asr_result,
)
from modules.runtime.voice_engine_v2.vosk_shadow_recognition_preflight import (
    VOSK_SHADOW_RECOGNITION_PREFLIGHT_STAGE,
    VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION,
    VoskShadowRecognitionPreflightSettings,
    build_vosk_shadow_recognition_preflight,
)
from modules.runtime.voice_engine_v2.vosk_shadow_invocation_attempt import (
    VOSK_SHADOW_INVOCATION_ATTEMPT_STAGE,
    VOSK_SHADOW_INVOCATION_ATTEMPT_VERSION,
    VoskShadowInvocationAttemptSettings,
    build_vosk_shadow_invocation_attempt,
)
from modules.runtime.voice_engine_v2.vad_shadow import (
    VoiceEngineV2VadShadowObserver,
    build_voice_engine_v2_vad_shadow_observer,
)


DEFAULT_VAD_TIMING_BRIDGE_LOG_PATH = (
    "var/data/voice_engine_v2_vad_timing_bridge.jsonl"
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2VadTimingBridgeRecord:
    timestamp_utc: str
    timestamp_monotonic: float
    enabled: bool
    observed: bool
    reason: str
    hook: str
    turn_id: str
    phase: str
    capture_mode: str
    legacy_runtime_primary: bool
    action_executed: bool
    full_stt_prevented: bool
    runtime_takeover: bool
    transcript_present: bool
    vad_shadow: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    telemetry_written: bool = False

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
        if not self.hook.strip():
            raise ValueError("hook must not be empty")
        if self.action_executed:
            raise ValueError("VAD timing bridge must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("VAD timing bridge must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("VAD timing bridge must never take over runtime")

        object.__setattr__(self, "vad_shadow", dict(self.vad_shadow or {}))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def with_telemetry_written(
        self,
        telemetry_written: bool,
    ) -> VoiceEngineV2VadTimingBridgeRecord:
        return VoiceEngineV2VadTimingBridgeRecord(
            timestamp_utc=self.timestamp_utc,
            timestamp_monotonic=self.timestamp_monotonic,
            enabled=self.enabled,
            observed=self.observed,
            reason=self.reason,
            hook=self.hook,
            turn_id=self.turn_id,
            phase=self.phase,
            capture_mode=self.capture_mode,
            legacy_runtime_primary=self.legacy_runtime_primary,
            action_executed=self.action_executed,
            full_stt_prevented=self.full_stt_prevented,
            runtime_takeover=self.runtime_takeover,
            transcript_present=self.transcript_present,
            vad_shadow=self.vad_shadow,
            metadata=self.metadata,
            telemetry_written=telemetry_written,
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "timestamp_monotonic": self.timestamp_monotonic,
            "enabled": self.enabled,
            "observed": self.observed,
            "reason": self.reason,
            "hook": self.hook,
            "turn_id": self.turn_id,
            "phase": self.phase,
            "capture_mode": self.capture_mode,
            "legacy_runtime_primary": self.legacy_runtime_primary,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
            "transcript_present": self.transcript_present,
            "vad_shadow": dict(self.vad_shadow),
            "metadata": dict(self.metadata),
        }


class VoiceEngineV2VadTimingBridgeTelemetryWriter:
    def __init__(self, path: str | Path, *, enabled: bool) -> None:
        self._path = Path(path)
        self._enabled = bool(enabled)

    @property
    def path(self) -> Path:
        return self._path

    def write(self, record: VoiceEngineV2VadTimingBridgeRecord) -> bool:
        if not self._enabled:
            return False

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record.to_json_dict(), ensure_ascii=False))
            file.write("\n")

        return True

    def write_safely(self, record: VoiceEngineV2VadTimingBridgeRecord) -> bool:
        try:
            return self.write(record)
        except Exception:
            return False


@dataclass(frozen=True, slots=True)
class _VadTimingBridgeArmState:
    turn_id: str
    phase: str
    capture_mode: str
    capture_handoff: dict[str, Any]
    armed_at_monotonic: float
    arm_snapshot: dict[str, Any]


class VoiceEngineV2VadTimingBridgeAdapter:
    """Observe-only VAD bridge around legacy capture.

    The bridge arms a dedicated VAD observer before legacy capture starts, then
    observes it after capture finishes. This measures frames published by the
    existing FasterWhisper audio bus tap without starting a second microphone
    stream and without running VAD inference inside the PortAudio callback.
    """

    def __init__(
        self,
        *,
        settings: Mapping[str, Any],
        vad_observer: VoiceEngineV2VadShadowObserver | None = None,
        telemetry_writer: VoiceEngineV2VadTimingBridgeTelemetryWriter | None = None,
    ) -> None:
        self._settings = settings
        self._vad_observer = vad_observer or build_voice_engine_v2_vad_shadow_observer(
            settings
        )
        self._telemetry_writer = telemetry_writer
        self._arm_state: _VadTimingBridgeArmState | None = None

    @property
    def enabled(self) -> bool:
        return bool(
            _voice_engine_config(self._settings).get(
                "vad_timing_bridge_enabled",
                False,
            )
        )

    @property
    def telemetry_path(self) -> str:
        if self._telemetry_writer is None:
            return ""
        return str(self._telemetry_writer.path)

    def arm(
        self,
        *,
        owner: Any,
        turn_id: str,
        phase: str,
        capture_mode: str,
        capture_handoff: Mapping[str, Any] | None = None,
    ) -> bool:
        if not self.enabled:
            self._arm_state = None
            return False

        safe, _reason = _safe_to_run_bridge(self._settings)
        if not safe:
            self._arm_state = None
            return False

        try:
            snapshot = self._vad_observer.arm(
                owner,
                subscription_name="voice_engine_v2_vad_timing_bridge",
                start_at_latest=True,
            )
        except Exception:
            self._arm_state = None
            return False

        to_json_dict = getattr(snapshot, "to_json_dict", None)
        arm_snapshot = dict(to_json_dict()) if callable(to_json_dict) else {}

        self._arm_state = _VadTimingBridgeArmState(
            turn_id=str(turn_id or "").strip(),
            phase=str(phase or "command").strip() or "command",
            capture_mode=str(capture_mode or "command").strip() or "command",
            capture_handoff=dict(capture_handoff or {}),
            armed_at_monotonic=time.monotonic(),
            arm_snapshot=arm_snapshot,
        )
        return bool(arm_snapshot.get("observed", False))

    def observe_after_capture(
        self,
        *,
        owner: Any,
        turn_id: str,
        phase: str,
        capture_mode: str,
        transcript_present: bool,
        transcript_metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2VadTimingBridgeRecord:
        if not self.enabled:
            return self._record(
                observed=False,
                reason="vad_timing_bridge_disabled",
                hook="post_capture",
                turn_id=turn_id,
                phase=phase,
                capture_mode=capture_mode,
                transcript_present=transcript_present,
                vad_shadow={},
                metadata={},
                write_telemetry=False,
            )

        safe, safety_reason = _safe_to_run_bridge(self._settings)
        if not safe:
            return self._record(
                observed=False,
                reason=f"vad_timing_bridge_not_safe:{safety_reason}",
                hook="post_capture",
                turn_id=turn_id,
                phase=phase,
                capture_mode=capture_mode,
                transcript_present=transcript_present,
                vad_shadow={},
                metadata={
                    "transcript_metadata": dict(transcript_metadata or {}),
                },
                write_telemetry=True,
            )

        arm_state = self._arm_state
        if arm_state is None:
            return self._record(
                observed=False,
                reason="vad_timing_bridge_not_armed",
                hook="post_capture",
                turn_id=turn_id,
                phase=phase,
                capture_mode=capture_mode,
                transcript_present=transcript_present,
                vad_shadow={},
                metadata={
                    "transcript_metadata": dict(transcript_metadata or {}),
                },
                write_telemetry=True,
            )

        try:
            snapshot = self._vad_observer.observe(owner)
            to_json_dict = getattr(snapshot, "to_json_dict", None)
            vad_shadow = dict(to_json_dict()) if callable(to_json_dict) else {}
            frames_processed = _positive_int(vad_shadow.get("frames_processed"))
            reason = (
                "vad_timing_bridge_observed_audio"
                if frames_processed > 0
                else "vad_timing_bridge_no_new_audio"
            )
            observed = bool(vad_shadow.get("observed", False))
        except Exception as error:
            vad_shadow = {
                "enabled": True,
                "observed": False,
                "reason": f"vad_timing_bridge_vad_failed:{type(error).__name__}",
                "error": str(error),
                "action_executed": False,
                "full_stt_prevented": False,
                "runtime_takeover": False,
            }
            reason = f"vad_timing_bridge_failed:{type(error).__name__}"
            observed = False

        record = self._record(
            owner=owner,
            observed=observed,
            reason=reason,
            hook="post_capture",
            turn_id=turn_id or arm_state.turn_id,
            phase=phase or arm_state.phase,
            capture_mode=capture_mode or arm_state.capture_mode,
            transcript_present=transcript_present,
            vad_shadow=vad_shadow,
            metadata={
                "armed_at_monotonic": arm_state.armed_at_monotonic,
                "capture_handoff": dict(arm_state.capture_handoff),
                "arm_snapshot": dict(arm_state.arm_snapshot),
                "transcript_metadata": dict(transcript_metadata or {}),
            },
            write_telemetry=True,
        )
        self._arm_state = None
        return record

    def observe_after_capture_window_publish(
        self,
        *,
        owner: Any,
        capture_window_metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2VadTimingBridgeRecord:
        if not self.enabled:
            return self._record(
                observed=False,
                reason="vad_timing_bridge_disabled",
                hook="capture_window_pre_transcription",
                turn_id="",
                phase="command",
                capture_mode="command",
                transcript_present=False,
                vad_shadow={},
                metadata={
                    "capture_window_shadow_tap": dict(
                        capture_window_metadata or {}
                    ),
                },
                write_telemetry=False,
            )

        safe, safety_reason = _safe_to_run_bridge(self._settings)
        if not safe:
            return self._record(
                observed=False,
                reason=f"vad_timing_bridge_not_safe:{safety_reason}",
                hook="capture_window_pre_transcription",
                turn_id="",
                phase="command",
                capture_mode="command",
                transcript_present=False,
                vad_shadow={},
                metadata={
                    "capture_window_shadow_tap": dict(
                        capture_window_metadata or {}
                    ),
                },
                write_telemetry=True,
            )

        arm_state = self._arm_state
        if arm_state is None:
            return self._record(
                observed=False,
                reason="vad_timing_bridge_not_armed",
                hook="capture_window_pre_transcription",
                turn_id="",
                phase="command",
                capture_mode="command",
                transcript_present=False,
                vad_shadow={},
                metadata={
                    "capture_window_shadow_tap": dict(
                        capture_window_metadata or {}
                    ),
                },
                write_telemetry=True,
            )

        try:
            snapshot = self._vad_observer.observe(owner)
            to_json_dict = getattr(snapshot, "to_json_dict", None)
            vad_shadow = dict(to_json_dict()) if callable(to_json_dict) else {}
            frames_processed = _positive_int(vad_shadow.get("frames_processed"))
            reason = (
                "vad_timing_bridge_pre_transcription_observed_audio"
                if frames_processed > 0
                else "vad_timing_bridge_pre_transcription_no_new_audio"
            )
            observed = bool(vad_shadow.get("observed", False))
        except Exception as error:
            vad_shadow = {
                "enabled": True,
                "observed": False,
                "reason": (
                    "vad_timing_bridge_pre_transcription_vad_failed:"
                    f"{type(error).__name__}"
                ),
                "error": str(error),
                "action_executed": False,
                "full_stt_prevented": False,
                "runtime_takeover": False,
            }
            reason = (
                "vad_timing_bridge_pre_transcription_failed:"
                f"{type(error).__name__}"
            )
            observed = False

        capture_window_shadow_tap = dict(capture_window_metadata or {})
        endpointing_candidate = build_vad_endpointing_candidate(
            hook="capture_window_pre_transcription",
            vad_shadow=vad_shadow,
            capture_window_metadata=capture_window_shadow_tap,
            observed_at_monotonic=time.monotonic(),
        )

        return self._record(
            owner=owner,
            observed=observed,
            reason=reason,
            hook="capture_window_pre_transcription",
            turn_id=arm_state.turn_id,
            phase=arm_state.phase,
            capture_mode=arm_state.capture_mode,
            transcript_present=False,
            vad_shadow=vad_shadow,
            metadata={
                "armed_at_monotonic": arm_state.armed_at_monotonic,
                "capture_handoff": dict(arm_state.capture_handoff),
                "arm_snapshot": dict(arm_state.arm_snapshot),
                "capture_window_shadow_tap": capture_window_shadow_tap,
                "endpointing_candidate": endpointing_candidate.to_json_dict(),
            },
            write_telemetry=True,
        )

    def _record(
        self,
        *,
        owner: Any | None = None,
        observed: bool,
        reason: str,
        hook: str,
        turn_id: str,
        phase: str,
        capture_mode: str,
        transcript_present: bool,
        vad_shadow: dict[str, Any],
        metadata: dict[str, Any],
        write_telemetry: bool,
    ) -> VoiceEngineV2VadTimingBridgeRecord:
        timestamp_utc = datetime.now(UTC).isoformat()
        timestamp_monotonic = time.monotonic()
        normalized_turn_id = str(turn_id or "").strip()
        normalized_phase = str(phase or "command").strip() or "command"
        normalized_capture_mode = (
            str(capture_mode or "command").strip() or "command"
        )
        safe_vad_shadow = dict(vad_shadow or {})
        safe_metadata = dict(metadata or {})
        safe_metadata = _maybe_attach_command_asr_shadow(
            settings=self._settings,
            owner=owner,
            timestamp_utc=timestamp_utc,
            timestamp_monotonic=timestamp_monotonic,
            enabled=self.enabled,
            observed=observed,
            reason=reason,
            hook=hook,
            turn_id=normalized_turn_id,
            phase=normalized_phase,
            capture_mode=normalized_capture_mode,
            transcript_present=transcript_present,
            vad_shadow=safe_vad_shadow,
            metadata=safe_metadata,
        )
        safe_metadata = _maybe_attach_vosk_live_shadow_contract(
            settings=self._settings,
            hook=hook,
            metadata=safe_metadata,
        )
        safe_metadata = _maybe_attach_vosk_shadow_invocation_plan(
            settings=self._settings,
            hook=hook,
            metadata=safe_metadata,
        )
        safe_metadata = _maybe_attach_vosk_shadow_pcm_reference(
            settings=self._settings,
            hook=hook,
            metadata=safe_metadata,
        )
        safe_metadata = _maybe_attach_vosk_shadow_asr_result(
            settings=self._settings,
            hook=hook,
            metadata=safe_metadata,
        )
        safe_metadata = _maybe_attach_vosk_shadow_recognition_preflight(
            settings=self._settings,
            hook=hook,
            metadata=safe_metadata,
        )
        safe_metadata = _maybe_attach_vosk_shadow_invocation_attempt(
            settings=self._settings,
            hook=hook,
            metadata=safe_metadata,
        )

        record = VoiceEngineV2VadTimingBridgeRecord(
            timestamp_utc=timestamp_utc,
            timestamp_monotonic=timestamp_monotonic,
            enabled=self.enabled,
            observed=observed,
            reason=reason,
            hook=hook,
            turn_id=normalized_turn_id,
            phase=normalized_phase,
            capture_mode=normalized_capture_mode,
            legacy_runtime_primary=True,
            action_executed=False,
            full_stt_prevented=False,
            runtime_takeover=False,
            transcript_present=bool(transcript_present),
            vad_shadow=safe_vad_shadow,
            metadata=safe_metadata,
        )

        if not write_telemetry or self._telemetry_writer is None:
            return record

        return record.with_telemetry_written(
            self._telemetry_writer.write_safely(record)
        )


def _maybe_attach_command_asr_shadow(
    *,
    settings: Mapping[str, Any],
    owner: Any | None,
    timestamp_utc: str,
    timestamp_monotonic: float,
    enabled: bool,
    observed: bool,
    reason: str,
    hook: str,
    turn_id: str,
    phase: str,
    capture_mode: str,
    transcript_present: bool,
    vad_shadow: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    voice_engine = _voice_engine_config(settings)

    if not bool(voice_engine.get("command_asr_shadow_bridge_enabled", False)):
        return safe_metadata

    if hook != "capture_window_pre_transcription":
        return safe_metadata

    record_payload = {
        "timestamp_utc": timestamp_utc,
        "timestamp_monotonic": timestamp_monotonic,
        "enabled": bool(enabled),
        "observed": bool(observed),
        "reason": str(reason or ""),
        "hook": str(hook or ""),
        "turn_id": str(turn_id or ""),
        "phase": str(phase or "command"),
        "capture_mode": str(capture_mode or "command"),
        "legacy_runtime_primary": True,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "transcript_present": bool(transcript_present),
        "vad_shadow": dict(vad_shadow or {}),
        "metadata": safe_metadata,
    }

    try:
        enriched_payload = enrich_record_with_command_asr_shadow(
            record=record_payload,
            settings=CommandAsrShadowBridgeSettings(enabled=True),
            recognizer=_build_controlled_bilingual_command_asr(
                voice_engine=voice_engine,
                owner=owner,
            ),
        )
    except Exception as error:
        safe_metadata["command_asr_shadow_bridge"] = {
            "bridge_stage": COMMAND_ASR_SHADOW_BRIDGE_STAGE,
            "bridge_version": COMMAND_ASR_SHADOW_BRIDGE_VERSION,
            "enabled": True,
            "observed": False,
            "reason": f"command_asr_shadow_bridge_failed:{type(error).__name__}",
            "candidate_attached": False,
            "command_asr_candidate_present": False,
            "command_asr_reason": "",
            "asr_reason": "",
            "recognizer_name": "",
            "recognizer_enabled": False,
            "recognition_attempted": False,
            "recognized": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        }
        return safe_metadata

    enriched_metadata = enriched_payload.get("metadata")
    if isinstance(enriched_metadata, Mapping):
        return dict(enriched_metadata)

    return safe_metadata


def _build_controlled_bilingual_command_asr(
    *,
    voice_engine: Mapping[str, Any],
    owner: Any | None,
) -> VoskCommandAsrAdapter | None:
    if not _controlled_vosk_recognition_enabled(voice_engine):
        return None

    model_paths = _mapping(voice_engine.get("vosk_command_model_paths"))
    english_model_path = str(
        model_paths.get("en") or DEFAULT_ENGLISH_VOSK_MODEL_PATH
    )
    polish_model_path = str(
        model_paths.get("pl") or DEFAULT_POLISH_VOSK_MODEL_PATH
    )
    sample_rate = _positive_int(
        voice_engine.get("vosk_command_sample_rate"),
        fallback=16_000,
    )

    recognizer = BilingualVoskCommandRecognizer(
        english_model_path=english_model_path,
        polish_model_path=polish_model_path,
        sample_rate=sample_rate,
    )

    return VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(enabled=True),
        recognizer=recognizer,
        segment_pcm_provider=lambda segment: _capture_window_pcm_from_owner(owner),
    )


def _controlled_vosk_recognition_enabled(
    voice_engine: Mapping[str, Any],
) -> bool:
    return bool(
        voice_engine.get("vosk_shadow_controlled_recognition_enabled", False)
        and voice_engine.get("vosk_shadow_controlled_recognition_dry_run_enabled", False)
        and voice_engine.get("vosk_shadow_controlled_recognition_result_enabled", False)
    )


def _capture_window_pcm_from_owner(owner: Any | None) -> bytes | None:
    if owner is None:
        return None

    pcm = getattr(
        owner,
        "_realtime_audio_bus_capture_window_shadow_tap_last_pcm",
        b"",
    )
    if isinstance(pcm, bytes) and pcm:
        return pcm

    return None


def _maybe_attach_vosk_live_shadow_contract(
    *,
    settings: Mapping[str, Any],
    hook: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    voice_engine = _voice_engine_config(settings)

    if not bool(voice_engine.get("vosk_live_shadow_contract_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("command_asr_shadow_bridge_enabled", False)):
        return safe_metadata

    if hook != "capture_window_pre_transcription":
        return safe_metadata

    command_asr_shadow_raw = safe_metadata.get("command_asr_shadow_bridge")
    command_asr_shadow = (
        dict(command_asr_shadow_raw)
        if isinstance(command_asr_shadow_raw, Mapping)
        else {}
    )
    if not command_asr_shadow:
        return safe_metadata

    try:
        contract = build_vosk_live_shadow_contract(
            settings=VoskLiveShadowContractSettings(enabled=True),
        )
        safe_metadata[contract.metadata_key] = contract.to_json_dict()
    except Exception as error:
        safe_metadata["vosk_live_shadow"] = {
            "contract_stage": VOSK_LIVE_SHADOW_CONTRACT_STAGE,
            "contract_version": VOSK_LIVE_SHADOW_CONTRACT_VERSION,
            "enabled": True,
            "observed": False,
            "reason": f"vosk_live_shadow_contract_failed:{type(error).__name__}",
            "metadata_key": "vosk_live_shadow",
            "input_source": "existing_command_audio_segment",
            "recognizer_name": "vosk_command_asr_shadow",
            "recognizer_enabled": False,
            "recognition_attempted": False,
            "recognized": False,
            "transcript": "",
            "normalized_text": "",
            "language": None,
            "confidence": None,
            "alternatives": [],
            "command_matched": False,
            "command_intent_key": None,
            "command_language": None,
            "command_matched_phrase": None,
            "command_confidence": None,
            "command_alternatives": [],
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        }

    return safe_metadata


def _maybe_attach_vosk_shadow_invocation_plan(
    *,
    settings: Mapping[str, Any],
    hook: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    voice_engine = _voice_engine_config(settings)

    if not bool(voice_engine.get("vosk_shadow_invocation_plan_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("command_asr_shadow_bridge_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_live_shadow_contract_enabled", False)):
        return safe_metadata

    if hook != "capture_window_pre_transcription":
        return safe_metadata

    if "command_asr_shadow_bridge" not in safe_metadata:
        return safe_metadata

    if "command_asr_candidate" not in safe_metadata:
        return safe_metadata

    if "vosk_live_shadow" not in safe_metadata:
        return safe_metadata

    try:
        plan = build_vosk_shadow_invocation_plan(
            hook=hook,
            metadata=safe_metadata,
            settings=VoskShadowInvocationPlanSettings(enabled=True),
        )
        safe_metadata[plan.metadata_key] = plan.to_json_dict()
    except Exception as error:
        safe_metadata["vosk_shadow_invocation_plan"] = {
            "plan_stage": VOSK_SHADOW_INVOCATION_PLAN_STAGE,
            "plan_version": VOSK_SHADOW_INVOCATION_PLAN_VERSION,
            "enabled": True,
            "plan_ready": False,
            "reason": f"vosk_shadow_invocation_plan_failed:{type(error).__name__}",
            "metadata_key": "vosk_shadow_invocation_plan",
            "hook": str(hook or ""),
            "input_source": "existing_command_audio_segment_metadata_only",
            "recognizer_name": "vosk_command_asr",
            "command_asr_bridge_present": False,
            "command_asr_candidate_present": False,
            "vosk_live_shadow_contract_present": False,
            "segment_present": False,
            "segment_reason": "",
            "segment_audio_duration_ms": None,
            "segment_audio_sample_count": 0,
            "segment_published_byte_count": 0,
            "segment_sample_rate": None,
            "segment_pcm_encoding": "",
            "recognition_invocation_performed": False,
            "recognition_attempted": False,
            "recognized": False,
            "command_matched": False,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        }

    return safe_metadata


def _maybe_attach_vosk_shadow_pcm_reference(
    *,
    settings: Mapping[str, Any],
    hook: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    voice_engine = _voice_engine_config(settings)

    if not bool(voice_engine.get("vosk_shadow_pcm_reference_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("command_asr_shadow_bridge_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_live_shadow_contract_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_invocation_plan_enabled", False)):
        return safe_metadata

    if hook != "capture_window_pre_transcription":
        return safe_metadata

    if "command_asr_candidate" not in safe_metadata:
        return safe_metadata

    if "vosk_shadow_invocation_plan" not in safe_metadata:
        return safe_metadata

    try:
        reference = build_vosk_shadow_pcm_reference(
            hook=hook,
            metadata=safe_metadata,
            settings=VoskShadowPcmReferenceSettings(enabled=True),
        )
        safe_metadata[reference.metadata_key] = reference.to_json_dict()
    except Exception as error:
        safe_metadata["vosk_shadow_pcm_reference"] = {
            "reference_stage": VOSK_SHADOW_PCM_REFERENCE_STAGE,
            "reference_version": VOSK_SHADOW_PCM_REFERENCE_VERSION,
            "enabled": True,
            "reference_ready": False,
            "reason": f"vosk_shadow_pcm_reference_failed:{type(error).__name__}",
            "metadata_key": "vosk_shadow_pcm_reference",
            "hook": str(hook or ""),
            "retrieval_strategy": "existing_capture_window_audio_bus_snapshot",
            "source": "",
            "publish_stage": "",
            "pcm_encoding": "",
            "sample_rate": None,
            "channels": None,
            "sample_width_bytes": None,
            "audio_sample_count": 0,
            "audio_duration_ms": None,
            "published_frame_count": 0,
            "published_byte_count": 0,
            "segment_present": False,
            "invocation_plan_present": False,
            "invocation_plan_ready": False,
            "command_asr_candidate_present": False,
            "raw_pcm_included": False,
            "pcm_retrieval_performed": False,
            "recognition_invocation_performed": False,
            "recognition_attempted": False,
            "recognized": False,
            "command_matched": False,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        }

    return safe_metadata


def _maybe_attach_vosk_shadow_asr_result(
    *,
    settings: Mapping[str, Any],
    hook: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    voice_engine = _voice_engine_config(settings)

    if not bool(voice_engine.get("vosk_shadow_asr_result_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("command_asr_shadow_bridge_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_live_shadow_contract_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_invocation_plan_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_pcm_reference_enabled", False)):
        return safe_metadata

    if hook != "capture_window_pre_transcription":
        return safe_metadata

    if "command_asr_shadow_bridge" not in safe_metadata:
        return safe_metadata

    if "vosk_live_shadow" not in safe_metadata:
        return safe_metadata

    if "vosk_shadow_invocation_plan" not in safe_metadata:
        return safe_metadata

    if "vosk_shadow_pcm_reference" not in safe_metadata:
        return safe_metadata

    command_asr_candidate = safe_metadata.get("command_asr_candidate")
    if not isinstance(command_asr_candidate, Mapping):
        return safe_metadata

    try:
        result = build_vosk_shadow_asr_result(
            candidate=command_asr_candidate,
            settings=VoskShadowAsrResultSettings(enabled=True),
        )
        safe_metadata[result.metadata_key] = result.to_json_dict()
    except Exception as error:
        safe_metadata["vosk_shadow_asr_result"] = {
            "result_stage": VOSK_SHADOW_ASR_RESULT_STAGE,
            "result_version": VOSK_SHADOW_ASR_RESULT_VERSION,
            "enabled": True,
            "result_present": False,
            "reason": f"vosk_shadow_asr_result_failed:{type(error).__name__}",
            "metadata_key": "vosk_shadow_asr_result",
            "recognizer_name": "vosk_command_asr",
            "recognizer_enabled": False,
            "recognition_invocation_performed": False,
            "recognition_attempted": False,
            "recognized": False,
            "command_matched": False,
            "transcript": "",
            "normalized_text": "",
            "language": None,
            "confidence": None,
            "alternatives": [],
            "turn_id": "",
            "hook": str(hook or ""),
            "source": "",
            "publish_stage": "",
            "segment_present": False,
            "segment_reason": "",
            "segment_audio_duration_ms": None,
            "segment_audio_sample_count": 0,
            "segment_published_byte_count": 0,
            "segment_sample_rate": None,
            "segment_pcm_encoding": "",
            "pcm_retrieval_performed": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        }

    return safe_metadata


def _maybe_attach_vosk_shadow_recognition_preflight(
    *,
    settings: Mapping[str, Any],
    hook: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    voice_engine = _voice_engine_config(settings)

    if not bool(voice_engine.get("vosk_shadow_recognition_preflight_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("command_asr_shadow_bridge_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_live_shadow_contract_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_invocation_plan_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_pcm_reference_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_asr_result_enabled", False)):
        return safe_metadata

    if hook != "capture_window_pre_transcription":
        return safe_metadata

    if "command_asr_shadow_bridge" not in safe_metadata:
        return safe_metadata

    if "vosk_live_shadow" not in safe_metadata:
        return safe_metadata

    if "vosk_shadow_invocation_plan" not in safe_metadata:
        return safe_metadata

    if "vosk_shadow_pcm_reference" not in safe_metadata:
        return safe_metadata

    if "vosk_shadow_asr_result" not in safe_metadata:
        return safe_metadata

    try:
        preflight = build_vosk_shadow_recognition_preflight(
            hook=hook,
            metadata=safe_metadata,
            settings=VoskShadowRecognitionPreflightSettings(enabled=True),
        )
        safe_metadata[preflight.metadata_key] = preflight.to_json_dict()
    except Exception as error:
        safe_metadata["vosk_shadow_recognition_preflight"] = {
            "preflight_stage": VOSK_SHADOW_RECOGNITION_PREFLIGHT_STAGE,
            "preflight_version": VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION,
            "enabled": True,
            "preflight_ready": False,
            "recognition_allowed": False,
            "recognition_blocked": True,
            "reason": (
                "vosk_shadow_recognition_preflight_failed:"
                f"{type(error).__name__}"
            ),
            "metadata_key": "vosk_shadow_recognition_preflight",
            "hook": str(hook or ""),
            "source": "",
            "publish_stage": "",
            "recognizer_name": "vosk_command_asr",
            "live_shadow_present": False,
            "invocation_plan_present": False,
            "invocation_plan_ready": False,
            "pcm_reference_present": False,
            "pcm_reference_ready": False,
            "asr_result_present": False,
            "asr_result_not_attempted": False,
            "audio_sample_count": 0,
            "published_byte_count": 0,
            "sample_rate": None,
            "pcm_encoding": "",
            "pcm_retrieval_allowed": False,
            "pcm_retrieval_performed": False,
            "recognition_invocation_allowed": False,
            "recognition_invocation_performed": False,
            "recognition_attempted": False,
            "result_present": False,
            "recognized": False,
            "command_matched": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        }

    return safe_metadata

def _maybe_attach_vosk_shadow_invocation_attempt(
    *,
    settings: Mapping[str, Any],
    hook: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    voice_engine = _voice_engine_config(settings)

    if not bool(voice_engine.get("vosk_shadow_invocation_attempt_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("command_asr_shadow_bridge_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_live_shadow_contract_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_invocation_plan_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_pcm_reference_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_asr_result_enabled", False)):
        return safe_metadata

    if not bool(voice_engine.get("vosk_shadow_recognition_preflight_enabled", False)):
        return safe_metadata

    if hook != "capture_window_pre_transcription":
        return safe_metadata

    if "vosk_shadow_recognition_preflight" not in safe_metadata:
        return safe_metadata

    try:
        attempt = build_vosk_shadow_invocation_attempt(
            hook=hook,
            metadata=safe_metadata,
            settings=VoskShadowInvocationAttemptSettings(enabled=True),
        )
        safe_metadata[attempt.metadata_key] = attempt.to_json_dict()
    except Exception as error:
        safe_metadata["vosk_shadow_invocation_attempt"] = {
            "attempt_stage": VOSK_SHADOW_INVOCATION_ATTEMPT_STAGE,
            "attempt_version": VOSK_SHADOW_INVOCATION_ATTEMPT_VERSION,
            "enabled": True,
            "attempt_ready": False,
            "invocation_allowed": False,
            "invocation_blocked": True,
            "reason": f"vosk_shadow_invocation_attempt_failed:{type(error).__name__}",
            "metadata_key": "vosk_shadow_invocation_attempt",
            "hook": str(hook or ""),
            "source": "",
            "publish_stage": "",
            "recognizer_name": "vosk_command_asr",
            "preflight_present": False,
            "preflight_ready": False,
            "preflight_recognition_blocked": False,
            "preflight_reason": "",
            "audio_sample_count": 0,
            "published_byte_count": 0,
            "sample_rate": None,
            "pcm_encoding": "",
            "pcm_retrieval_allowed": False,
            "pcm_retrieval_performed": False,
            "recognition_allowed": False,
            "recognition_invocation_allowed": False,
            "recognition_invocation_performed": False,
            "recognition_attempted": False,
            "result_present": False,
            "recognized": False,
            "command_matched": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        }

    return safe_metadata


def build_voice_engine_v2_vad_timing_bridge_adapter(
    settings: Mapping[str, Any],
) -> VoiceEngineV2VadTimingBridgeAdapter:
    voice_engine_cfg = _voice_engine_config(settings)
    log_path = str(
        voice_engine_cfg.get(
            "vad_timing_bridge_log_path",
            DEFAULT_VAD_TIMING_BRIDGE_LOG_PATH,
        )
        or DEFAULT_VAD_TIMING_BRIDGE_LOG_PATH
    )
    return VoiceEngineV2VadTimingBridgeAdapter(
        settings=settings,
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )


def _voice_engine_config(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    voice_engine_cfg = settings.get("voice_engine", {})
    if isinstance(voice_engine_cfg, Mapping):
        return voice_engine_cfg
    return {}


def _safe_to_run_bridge(settings: Mapping[str, Any]) -> tuple[bool, str]:
    voice_engine = _voice_engine_config(settings)

    if bool(voice_engine.get("enabled", False)):
        return False, "voice_engine_enabled_must_remain_false"
    if str(voice_engine.get("mode", "legacy") or "legacy") != "legacy":
        return False, "voice_engine_mode_must_remain_legacy"
    if bool(voice_engine.get("command_first_enabled", False)):
        return False, "command_first_enabled_must_remain_false"
    if not bool(voice_engine.get("fallback_to_legacy_enabled", True)):
        return False, "fallback_to_legacy_enabled_must_remain_true"
    if bool(voice_engine.get("runtime_candidates_enabled", False)):
        return False, "runtime_candidates_enabled_must_remain_false"
    if not bool(voice_engine.get("pre_stt_shadow_enabled", False)):
        return False, "pre_stt_shadow_enabled_must_be_true"
    if not bool(voice_engine.get("faster_whisper_audio_bus_tap_enabled", False)):
        return False, "audio_bus_tap_enabled_must_be_true"
    if not bool(voice_engine.get("vad_shadow_enabled", False)):
        return False, "vad_shadow_enabled_must_be_true"

    return True, "safe"


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _positive_int(raw_value: Any, *, fallback: int = 0) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        try:
            value = int(fallback)
        except (TypeError, ValueError):
            return 0
    return value if value > 0 else 0


__all__ = [
    "DEFAULT_VAD_TIMING_BRIDGE_LOG_PATH",
    "VoiceEngineV2VadTimingBridgeAdapter",
    "VoiceEngineV2VadTimingBridgeRecord",
    "VoiceEngineV2VadTimingBridgeTelemetryWriter",
    "build_voice_engine_v2_vad_timing_bridge_adapter",
]