from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


EXPECTED_HOOK = "capture_window_pre_transcription"

UNSAFE_CONTRACT_FIELDS: tuple[str, ...] = (
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
)


@dataclass(frozen=True, slots=True)
class VoskShadowReadinessReport:
    accepted: bool
    ready_for_observe_only_invocation_design: bool
    reason: str
    records: int
    contract_records: int
    enabled_contract_records: int
    waiting_contract_records: int
    observed_contract_records: int
    capture_window_contract_records: int
    non_capture_window_contract_records: int
    command_asr_bridge_records: int
    command_asr_candidate_records: int
    command_audio_segment_ready_records: int
    recognition_attempted_records: int
    recognized_records: int
    command_matched_records: int
    unsafe_contract_records: int
    raw_pcm_records: int
    reason_counts: dict[str, int] = field(default_factory=dict)
    command_asr_reason_counts: dict[str, int] = field(default_factory=dict)
    asr_reason_counts: dict[str, int] = field(default_factory=dict)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    runtime_integration_allowed: bool = False
    command_execution_allowed: bool = False
    faster_whisper_bypass_allowed: bool = False
    independent_microphone_stream_allowed: bool = False
    live_command_recognition_allowed: bool = False

    def __post_init__(self) -> None:
        if self.runtime_integration_allowed:
            raise ValueError("Vosk shadow readiness must not allow runtime integration")
        if self.command_execution_allowed:
            raise ValueError("Vosk shadow readiness must not allow command execution")
        if self.faster_whisper_bypass_allowed:
            raise ValueError("Vosk shadow readiness must not allow FasterWhisper bypass")
        if self.independent_microphone_stream_allowed:
            raise ValueError(
                "Vosk shadow readiness must not allow independent microphone stream"
            )
        if self.live_command_recognition_allowed:
            raise ValueError("Vosk shadow readiness must not allow live recognition")

        object.__setattr__(self, "reason_counts", dict(self.reason_counts))
        object.__setattr__(
            self,
            "command_asr_reason_counts",
            dict(self.command_asr_reason_counts),
        )
        object.__setattr__(self, "asr_reason_counts", dict(self.asr_reason_counts))
        object.__setattr__(self, "blockers", tuple(self.blockers))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "ready_for_observe_only_invocation_design": (
                self.ready_for_observe_only_invocation_design
            ),
            "reason": self.reason,
            "records": self.records,
            "contract_records": self.contract_records,
            "enabled_contract_records": self.enabled_contract_records,
            "waiting_contract_records": self.waiting_contract_records,
            "observed_contract_records": self.observed_contract_records,
            "capture_window_contract_records": self.capture_window_contract_records,
            "non_capture_window_contract_records": (
                self.non_capture_window_contract_records
            ),
            "command_asr_bridge_records": self.command_asr_bridge_records,
            "command_asr_candidate_records": self.command_asr_candidate_records,
            "command_audio_segment_ready_records": (
                self.command_audio_segment_ready_records
            ),
            "recognition_attempted_records": self.recognition_attempted_records,
            "recognized_records": self.recognized_records,
            "command_matched_records": self.command_matched_records,
            "unsafe_contract_records": self.unsafe_contract_records,
            "raw_pcm_records": self.raw_pcm_records,
            "reason_counts": dict(self.reason_counts),
            "command_asr_reason_counts": dict(self.command_asr_reason_counts),
            "asr_reason_counts": dict(self.asr_reason_counts),
            "blockers": list(self.blockers),
            "runtime_integration_allowed": self.runtime_integration_allowed,
            "command_execution_allowed": self.command_execution_allowed,
            "faster_whisper_bypass_allowed": self.faster_whisper_bypass_allowed,
            "independent_microphone_stream_allowed": (
                self.independent_microphone_stream_allowed
            ),
            "live_command_recognition_allowed": self.live_command_recognition_allowed,
        }


def load_vad_timing_records(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []

    records: list[dict[str, Any]] = []
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue

        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            records.append(payload)

    return records


def build_vosk_shadow_readiness_report(
    records: Iterable[Mapping[str, Any]],
) -> VoskShadowReadinessReport:
    record_count = 0
    contract_records = 0
    enabled_contract_records = 0
    waiting_contract_records = 0
    observed_contract_records = 0
    capture_window_contract_records = 0
    non_capture_window_contract_records = 0
    command_asr_bridge_records = 0
    command_asr_candidate_records = 0
    command_audio_segment_ready_records = 0
    recognition_attempted_records = 0
    recognized_records = 0
    command_matched_records = 0
    unsafe_contract_records = 0
    raw_pcm_records = 0

    reason_counts: Counter[str] = Counter()
    command_asr_reason_counts: Counter[str] = Counter()
    asr_reason_counts: Counter[str] = Counter()
    blockers: list[str] = []

    for record in records:
        record_payload = dict(record or {})
        record_count += 1

        metadata = _mapping(record_payload.get("metadata"))
        contract = _mapping(metadata.get("vosk_live_shadow"))
        if not contract:
            continue

        contract_records += 1

        hook = str(record_payload.get("hook") or "")
        if hook == EXPECTED_HOOK:
            capture_window_contract_records += 1
        else:
            non_capture_window_contract_records += 1

        reason = str(contract.get("reason") or "")
        if reason:
            reason_counts[reason] += 1

        if contract.get("enabled") is True:
            enabled_contract_records += 1

        if contract.get("observed") is True:
            observed_contract_records += 1
        else:
            waiting_contract_records += 1

        if contract.get("recognition_attempted") is True:
            recognition_attempted_records += 1

        if contract.get("recognized") is True:
            recognized_records += 1

        if contract.get("command_matched") is True:
            command_matched_records += 1

        if contract.get("raw_pcm_included") is not False:
            raw_pcm_records += 1

        if _contract_has_unsafe_values(contract):
            unsafe_contract_records += 1

        bridge = _mapping(metadata.get("command_asr_shadow_bridge"))
        if bridge:
            command_asr_bridge_records += 1
            command_asr_reason = str(bridge.get("command_asr_reason") or "")
            asr_reason = str(bridge.get("asr_reason") or "")
            if command_asr_reason:
                command_asr_reason_counts[command_asr_reason] += 1
            if asr_reason:
                asr_reason_counts[asr_reason] += 1

        candidate = _mapping(metadata.get("command_asr_candidate"))
        if candidate:
            command_asr_candidate_records += 1
            if candidate.get("segment_present") is True:
                command_audio_segment_ready_records += 1

    if record_count <= 0:
        blockers.append("records_missing")
    if contract_records <= 0:
        blockers.append("vosk_live_shadow_contract_records_missing")
    if enabled_contract_records <= 0:
        blockers.append("enabled_vosk_live_shadow_contract_records_missing")
    if non_capture_window_contract_records > 0:
        blockers.append("non_capture_window_contract_records_present")
    if command_asr_bridge_records <= 0:
        blockers.append("command_asr_shadow_bridge_records_missing")
    if command_asr_candidate_records <= 0:
        blockers.append("command_asr_candidate_records_missing")
    if command_audio_segment_ready_records <= 0:
        blockers.append("command_audio_segment_ready_records_missing")
    if observed_contract_records > 0:
        blockers.append("contract_observed_before_recognizer_invocation_stage")
    if recognition_attempted_records > 0:
        blockers.append("recognition_attempted_before_recognizer_invocation_stage")
    if recognized_records > 0:
        blockers.append("recognized_before_recognizer_invocation_stage")
    if command_matched_records > 0:
        blockers.append("command_matched_before_resolver_stage")
    if unsafe_contract_records > 0:
        blockers.append("unsafe_contract_records_present")
    if raw_pcm_records > 0:
        blockers.append("raw_pcm_included_in_telemetry")

    accepted = (
        record_count > 0
        and contract_records > 0
        and enabled_contract_records > 0
        and non_capture_window_contract_records == 0
        and observed_contract_records == 0
        and recognition_attempted_records == 0
        and recognized_records == 0
        and command_matched_records == 0
        and unsafe_contract_records == 0
        and raw_pcm_records == 0
    )

    ready_for_design = (
        accepted
        and command_asr_bridge_records > 0
        and command_asr_candidate_records > 0
        and command_audio_segment_ready_records > 0
    )

    reason = (
        "ready_for_observe_only_invocation_design"
        if ready_for_design
        else "not_ready_for_observe_only_invocation_design"
    )

    return VoskShadowReadinessReport(
        accepted=accepted,
        ready_for_observe_only_invocation_design=ready_for_design,
        reason=reason,
        records=record_count,
        contract_records=contract_records,
        enabled_contract_records=enabled_contract_records,
        waiting_contract_records=waiting_contract_records,
        observed_contract_records=observed_contract_records,
        capture_window_contract_records=capture_window_contract_records,
        non_capture_window_contract_records=non_capture_window_contract_records,
        command_asr_bridge_records=command_asr_bridge_records,
        command_asr_candidate_records=command_asr_candidate_records,
        command_audio_segment_ready_records=command_audio_segment_ready_records,
        recognition_attempted_records=recognition_attempted_records,
        recognized_records=recognized_records,
        command_matched_records=command_matched_records,
        unsafe_contract_records=unsafe_contract_records,
        raw_pcm_records=raw_pcm_records,
        reason_counts=dict(reason_counts),
        command_asr_reason_counts=dict(command_asr_reason_counts),
        asr_reason_counts=dict(asr_reason_counts),
        blockers=tuple(blockers),
        runtime_integration_allowed=False,
        command_execution_allowed=False,
        faster_whisper_bypass_allowed=False,
        independent_microphone_stream_allowed=False,
        live_command_recognition_allowed=False,
    )


def _contract_has_unsafe_values(contract: Mapping[str, Any]) -> bool:
    for field_name in UNSAFE_CONTRACT_FIELDS:
        if contract.get(field_name) is not False:
            return True
    return False


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


__all__ = [
    "EXPECTED_HOOK",
    "UNSAFE_CONTRACT_FIELDS",
    "VoskShadowReadinessReport",
    "build_vosk_shadow_readiness_report",
    "load_vad_timing_records",
]