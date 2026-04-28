from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from modules.runtime.voice_engine_v2.command_asr import (
    CommandAsrRecognizer,
    DisabledCommandAsrRecognizer,
    build_command_asr_candidate,
)


COMMAND_ASR_SHADOW_BRIDGE_STAGE = "command_asr_shadow_bridge"
COMMAND_ASR_SHADOW_BRIDGE_VERSION = "stage_24t_v1"

COMMAND_ASR_SHADOW_BRIDGE_DISABLED_REASON = "command_asr_shadow_bridge_disabled"
COMMAND_ASR_SHADOW_BRIDGE_OBSERVED_REASON = "command_asr_shadow_bridge_observed"

DEFAULT_BRIDGE_METADATA_KEY = "command_asr_shadow_bridge"
DEFAULT_CANDIDATE_METADATA_KEY = "command_asr_candidate"


@dataclass(frozen=True, slots=True)
class CommandAsrShadowBridgeSettings:
    enabled: bool = False
    bridge_metadata_key: str = DEFAULT_BRIDGE_METADATA_KEY
    candidate_metadata_key: str = DEFAULT_CANDIDATE_METADATA_KEY

    def __post_init__(self) -> None:
        if not self.bridge_metadata_key.strip():
            raise ValueError("bridge_metadata_key must not be empty")
        if not self.candidate_metadata_key.strip():
            raise ValueError("candidate_metadata_key must not be empty")
        if self.bridge_metadata_key == self.candidate_metadata_key:
            raise ValueError("metadata keys must be different")


@dataclass(frozen=True, slots=True)
class CommandAsrShadowBridgeResult:
    bridge_stage: str
    bridge_version: str
    enabled: bool
    observed: bool
    reason: str
    candidate_attached: bool
    command_asr_candidate_present: bool
    command_asr_reason: str
    asr_reason: str
    recognizer_name: str
    recognizer_enabled: bool
    recognition_attempted: bool
    recognized: bool
    raw_pcm_included: bool = False
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("Command ASR shadow bridge must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Command ASR shadow bridge must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Command ASR shadow bridge must never take over runtime")
        if self.raw_pcm_included:
            raise ValueError("Command ASR shadow bridge must not include raw PCM")
        if self.command_asr_candidate_present and not self.candidate_attached:
            raise ValueError("Command ASR candidate cannot be present when not attached")
        if self.recognized and not self.recognition_attempted:
            raise ValueError("Command ASR cannot be recognized without attempt")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "bridge_stage": self.bridge_stage,
            "bridge_version": self.bridge_version,
            "enabled": self.enabled,
            "observed": self.observed,
            "reason": self.reason,
            "candidate_attached": self.candidate_attached,
            "command_asr_candidate_present": self.command_asr_candidate_present,
            "command_asr_reason": self.command_asr_reason,
            "asr_reason": self.asr_reason,
            "recognizer_name": self.recognizer_name,
            "recognizer_enabled": self.recognizer_enabled,
            "recognition_attempted": self.recognition_attempted,
            "recognized": self.recognized,
            "raw_pcm_included": self.raw_pcm_included,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def enrich_record_with_command_asr_shadow(
    *,
    record: Mapping[str, Any],
    settings: CommandAsrShadowBridgeSettings | None = None,
    recognizer: CommandAsrRecognizer | None = None,
) -> dict[str, Any]:
    bridge_settings = settings or CommandAsrShadowBridgeSettings()
    payload = dict(record or {})
    metadata = _mapping(payload.get("metadata"))

    _raise_if_unsafe(payload)

    if not bridge_settings.enabled:
        bridge_result = CommandAsrShadowBridgeResult(
            bridge_stage=COMMAND_ASR_SHADOW_BRIDGE_STAGE,
            bridge_version=COMMAND_ASR_SHADOW_BRIDGE_VERSION,
            enabled=False,
            observed=False,
            reason=COMMAND_ASR_SHADOW_BRIDGE_DISABLED_REASON,
            candidate_attached=False,
            command_asr_candidate_present=False,
            command_asr_reason="",
            asr_reason="",
            recognizer_name="",
            recognizer_enabled=False,
            recognition_attempted=False,
            recognized=False,
            raw_pcm_included=False,
            action_executed=False,
            full_stt_prevented=False,
            runtime_takeover=False,
        )
        metadata[bridge_settings.bridge_metadata_key] = bridge_result.to_json_dict()
        payload["metadata"] = metadata
        return payload

    command_asr = recognizer or DisabledCommandAsrRecognizer()
    candidate = build_command_asr_candidate(
        record=payload,
        recognizer=command_asr,
    )
    candidate_payload = candidate.to_json_dict()

    bridge_result = _bridge_result_from_candidate(candidate_payload)
    metadata[bridge_settings.candidate_metadata_key] = candidate_payload
    metadata[bridge_settings.bridge_metadata_key] = bridge_result.to_json_dict()
    payload["metadata"] = metadata
    return payload


def _bridge_result_from_candidate(
    candidate_payload: Mapping[str, Any],
) -> CommandAsrShadowBridgeResult:
    return CommandAsrShadowBridgeResult(
        bridge_stage=COMMAND_ASR_SHADOW_BRIDGE_STAGE,
        bridge_version=COMMAND_ASR_SHADOW_BRIDGE_VERSION,
        enabled=True,
        observed=True,
        reason=COMMAND_ASR_SHADOW_BRIDGE_OBSERVED_REASON,
        candidate_attached=True,
        command_asr_candidate_present=bool(
            candidate_payload.get("candidate_present", False)
        ),
        command_asr_reason=str(candidate_payload.get("reason") or ""),
        asr_reason=str(candidate_payload.get("asr_reason") or ""),
        recognizer_name=str(candidate_payload.get("recognizer_name") or ""),
        recognizer_enabled=bool(candidate_payload.get("recognizer_enabled", False)),
        recognition_attempted=bool(
            candidate_payload.get("recognition_attempted", False)
        ),
        recognized=bool(candidate_payload.get("recognized", False)),
        raw_pcm_included=bool(candidate_payload.get("raw_pcm_included", False)),
        action_executed=bool(candidate_payload.get("action_executed", False)),
        full_stt_prevented=bool(candidate_payload.get("full_stt_prevented", False)),
        runtime_takeover=bool(candidate_payload.get("runtime_takeover", False)),
    )


def _raise_if_unsafe(payload: Mapping[str, Any]) -> None:
    metadata = _mapping(payload.get("metadata"))
    endpointing_candidate = _mapping(metadata.get("endpointing_candidate"))
    command_asr_candidate = _mapping(metadata.get(DEFAULT_CANDIDATE_METADATA_KEY))

    action_executed = (
        bool(payload.get("action_executed", False))
        or bool(endpointing_candidate.get("action_executed", False))
        or bool(command_asr_candidate.get("action_executed", False))
    )
    full_stt_prevented = (
        bool(payload.get("full_stt_prevented", False))
        or bool(endpointing_candidate.get("full_stt_prevented", False))
        or bool(command_asr_candidate.get("full_stt_prevented", False))
    )
    runtime_takeover = (
        bool(payload.get("runtime_takeover", False))
        or bool(endpointing_candidate.get("runtime_takeover", False))
        or bool(command_asr_candidate.get("runtime_takeover", False))
    )

    if action_executed:
        raise ValueError("Command ASR shadow bridge must never receive action execution")
    if full_stt_prevented:
        raise ValueError("Command ASR shadow bridge must never receive full STT prevention")
    if runtime_takeover:
        raise ValueError("Command ASR shadow bridge must never receive runtime takeover")


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


__all__ = [
    "COMMAND_ASR_SHADOW_BRIDGE_DISABLED_REASON",
    "COMMAND_ASR_SHADOW_BRIDGE_OBSERVED_REASON",
    "COMMAND_ASR_SHADOW_BRIDGE_STAGE",
    "COMMAND_ASR_SHADOW_BRIDGE_VERSION",
    "DEFAULT_BRIDGE_METADATA_KEY",
    "DEFAULT_CANDIDATE_METADATA_KEY",
    "CommandAsrShadowBridgeResult",
    "CommandAsrShadowBridgeSettings",
    "enrich_record_with_command_asr_shadow",
]