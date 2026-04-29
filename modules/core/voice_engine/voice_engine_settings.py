from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_DEFAULT_RUNTIME_CANDIDATE_INTENT_ALLOWLIST = (
    "assistant.identity",
    "system.current_time",
)

_DEFAULT_ENGLISH_VOSK_MODEL_PATH = "var/models/vosk/vosk-model-small-en-us-0.15"
_DEFAULT_POLISH_VOSK_MODEL_PATH = "var/models/vosk/vosk-model-small-pl-0.22"
_DEFAULT_VOSK_SAMPLE_RATE = 16_000


@dataclass(frozen=True, slots=True)
class VoiceEngineSettings:
    """Voice Engine v2 feature-gate settings."""

    enabled: bool = False
    version: str = "v2"
    mode: str = "legacy"

    realtime_audio_bus_enabled: bool = False
    faster_whisper_audio_bus_tap_enabled: bool = False
    faster_whisper_audio_bus_tap_max_duration_seconds: float = 3.0

    vad_endpointing_enabled: bool = False
    vad_shadow_enabled: bool = False
    vad_shadow_max_frames_per_observation: int = 96
    vad_shadow_speech_threshold: float = 0.5
    vad_shadow_min_speech_ms: int = 120
    vad_shadow_min_silence_ms: int = 250
    vad_timing_bridge_enabled: bool = False
    vad_timing_bridge_log_path: str = "var/data/voice_engine_v2_vad_timing_bridge.jsonl"

    command_first_enabled: bool = False
    command_asr_shadow_bridge_enabled: bool = False

    vosk_live_shadow_contract_enabled: bool = False
    vosk_shadow_invocation_plan_enabled: bool = False
    vosk_shadow_pcm_reference_enabled: bool = False
    vosk_shadow_asr_result_enabled: bool = False
    vosk_shadow_recognition_preflight_enabled: bool = False
    vosk_shadow_invocation_attempt_enabled: bool = False
    vosk_shadow_controlled_recognition_enabled: bool = False
    vosk_shadow_controlled_recognition_dry_run_enabled: bool = False
    vosk_shadow_controlled_recognition_result_enabled: bool = False
    vosk_shadow_candidate_comparison_enabled: bool = False
    vosk_command_english_model_path: str = _DEFAULT_ENGLISH_VOSK_MODEL_PATH
    vosk_command_polish_model_path: str = _DEFAULT_POLISH_VOSK_MODEL_PATH
    vosk_command_sample_rate: int = _DEFAULT_VOSK_SAMPLE_RATE

    fallback_to_legacy_enabled: bool = True
    metrics_enabled: bool = True

    shadow_mode_enabled: bool = False
    shadow_log_path: str = "var/data/voice_engine_v2_shadow.jsonl"

    runtime_candidates_enabled: bool = False
    runtime_candidate_intent_allowlist: tuple[str, ...] = (
        _DEFAULT_RUNTIME_CANDIDATE_INTENT_ALLOWLIST
    )
    runtime_candidate_log_path: str = (
        "var/data/voice_engine_v2_runtime_candidates.jsonl"
    )

    pre_stt_shadow_enabled: bool = False
    pre_stt_shadow_log_path: str = (
        "var/data/voice_engine_v2_pre_stt_shadow.jsonl"
    )

    legacy_removal_stage: str = "after_voice_engine_v2_runtime_acceptance"

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")
        if self.version != "v2":
            raise ValueError("only Voice Engine v2 settings are supported")
        if not self.mode.strip():
            raise ValueError("mode must not be empty")

        if self.faster_whisper_audio_bus_tap_max_duration_seconds <= 0:
            raise ValueError(
                "faster_whisper_audio_bus_tap_max_duration_seconds must be positive"
            )

        if self.vad_shadow_max_frames_per_observation <= 0:
            raise ValueError("vad_shadow_max_frames_per_observation must be positive")
        if not 0.0 <= self.vad_shadow_speech_threshold <= 1.0:
            raise ValueError("vad_shadow_speech_threshold must be between 0.0 and 1.0")
        if self.vad_shadow_min_speech_ms < 0:
            raise ValueError("vad_shadow_min_speech_ms must not be negative")
        if self.vad_shadow_min_silence_ms < 0:
            raise ValueError("vad_shadow_min_silence_ms must not be negative")
        if not self.vad_timing_bridge_log_path.strip():
            raise ValueError("vad_timing_bridge_log_path must not be empty")

        if not self.vosk_command_english_model_path.strip():
            raise ValueError("vosk_command_english_model_path must not be empty")
        if not self.vosk_command_polish_model_path.strip():
            raise ValueError("vosk_command_polish_model_path must not be empty")
        if self.vosk_command_sample_rate <= 0:
            raise ValueError("vosk_command_sample_rate must be positive")

        if not self.shadow_log_path.strip():
            raise ValueError("shadow_log_path must not be empty")
        if not self.runtime_candidate_log_path.strip():
            raise ValueError("runtime_candidate_log_path must not be empty")
        if not self.pre_stt_shadow_log_path.strip():
            raise ValueError("pre_stt_shadow_log_path must not be empty")
        if not self.legacy_removal_stage.strip():
            raise ValueError("legacy_removal_stage must not be empty")

        object.__setattr__(
            self,
            "runtime_candidate_intent_allowlist",
            self._normalize_intent_allowlist(self.runtime_candidate_intent_allowlist),
        )

        object.__setattr__(
            self,
            "vosk_command_english_model_path",
            self.vosk_command_english_model_path.strip(),
        )
        object.__setattr__(
            self,
            "vosk_command_polish_model_path",
            self.vosk_command_polish_model_path.strip(),
        )

    @property
    def command_pipeline_can_run(self) -> bool:
        """Return whether Voice Engine v2 may be used as the live command path."""

        return (
            self.enabled
            and self.mode == "v2"
            and self.command_first_enabled
        )

    @property
    def shadow_mode_can_run(self) -> bool:
        """Return whether shadow comparison may observe legacy transcripts."""

        return self.shadow_mode_enabled and self.fallback_to_legacy_enabled

    @property
    def audio_bus_observe_can_run(self) -> bool:
        """Return whether the legacy audio-bus tap may observe safely."""

        return (
            self.faster_whisper_audio_bus_tap_enabled
            and not self.enabled
            and self.mode == "legacy"
            and not self.command_first_enabled
            and self.fallback_to_legacy_enabled
        )

    @property
    def vad_shadow_can_run(self) -> bool:
        """Return whether VAD shadow observation may run without taking over audio."""

        return (
            self.vad_shadow_enabled
            and not self.enabled
            and self.mode == "legacy"
            and not self.vad_endpointing_enabled
            and not self.command_first_enabled
            and self.fallback_to_legacy_enabled
        )

    @property
    def vad_timing_bridge_can_run(self) -> bool:
        """Return whether VAD timing telemetry may be emitted safely."""

        return (
            self.vad_timing_bridge_enabled
            and self.vad_shadow_can_run
            and bool(self.vad_timing_bridge_log_path.strip())
        )

    @property
    def command_asr_shadow_can_run(self) -> bool:
        """Return whether command ASR shadow observation may run safely."""

        return (
            self.command_asr_shadow_bridge_enabled
            and not self.enabled
            and self.mode == "legacy"
            and not self.command_first_enabled
            and self.fallback_to_legacy_enabled
            and self.vosk_command_models_configured
        )

    @property
    def vosk_live_shadow_contract_can_run(self) -> bool:
        """Return whether the Vosk live-shadow contract may observe safely."""

        return (
            self.vosk_live_shadow_contract_enabled
            and self.command_asr_shadow_can_run
        )

    @property
    def vosk_controlled_recognition_can_run(self) -> bool:
        """Return whether controlled Vosk recognition may run as observe-only."""

        return (
            self.vosk_shadow_controlled_recognition_enabled
            and self.vosk_shadow_recognition_preflight_enabled
            and self.command_asr_shadow_can_run
            and not self.vosk_shadow_controlled_recognition_dry_run_enabled
        )

    @property
    def runtime_candidates_can_run(self) -> bool:
        """Return whether guarded runtime candidates may run before legacy fallback."""

        return (
            self.runtime_candidates_enabled
            and not self.enabled
            and self.mode == "legacy"
            and not self.command_first_enabled
            and self.fallback_to_legacy_enabled
            and bool(self.runtime_candidate_intent_allowlist)
        )

    @property
    def pre_stt_shadow_can_run(self) -> bool:
        """Return whether the pre-STT shadow hook may observe safely."""

        return (
            self.pre_stt_shadow_enabled
            and not self.enabled
            and self.mode == "legacy"
            and not self.command_first_enabled
            and self.fallback_to_legacy_enabled
        )

    @property
    def vosk_command_models_configured(self) -> bool:
        """Return whether both language-specific Vosk command model paths exist in config."""

        return bool(
            self.vosk_command_english_model_path.strip()
            and self.vosk_command_polish_model_path.strip()
        )

    @property
    def vosk_command_model_paths(self) -> dict[str, str]:
        """Return language-specific Vosk command model paths for status metadata."""

        return {
            "en": self.vosk_command_english_model_path,
            "pl": self.vosk_command_polish_model_path,
        }

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> VoiceEngineSettings:
        raw = settings.get("voice_engine", settings)
        vosk_paths = raw.get("vosk_command_model_paths", {})
        if not isinstance(vosk_paths, dict):
            vosk_paths = {}

        return cls(
            enabled=bool(raw.get("enabled", False)),
            version=str(raw.get("version", "v2")),
            mode=str(raw.get("mode", "legacy")),
            realtime_audio_bus_enabled=bool(
                raw.get("realtime_audio_bus_enabled", False)
            ),
            faster_whisper_audio_bus_tap_enabled=bool(
                raw.get("faster_whisper_audio_bus_tap_enabled", False)
            ),
            faster_whisper_audio_bus_tap_max_duration_seconds=float(
                raw.get("faster_whisper_audio_bus_tap_max_duration_seconds", 3.0)
            ),
            vad_endpointing_enabled=bool(raw.get("vad_endpointing_enabled", False)),
            vad_shadow_enabled=bool(raw.get("vad_shadow_enabled", False)),
            vad_shadow_max_frames_per_observation=int(
                raw.get("vad_shadow_max_frames_per_observation", 96)
            ),
            vad_shadow_speech_threshold=float(
                raw.get("vad_shadow_speech_threshold", 0.5)
            ),
            vad_shadow_min_speech_ms=int(raw.get("vad_shadow_min_speech_ms", 120)),
            vad_shadow_min_silence_ms=int(raw.get("vad_shadow_min_silence_ms", 250)),
            vad_timing_bridge_enabled=bool(
                raw.get("vad_timing_bridge_enabled", False)
            ),
            vad_timing_bridge_log_path=str(
                raw.get(
                    "vad_timing_bridge_log_path",
                    "var/data/voice_engine_v2_vad_timing_bridge.jsonl",
                )
            ),
            command_first_enabled=bool(raw.get("command_first_enabled", False)),
            command_asr_shadow_bridge_enabled=bool(
                raw.get("command_asr_shadow_bridge_enabled", False)
            ),
            vosk_live_shadow_contract_enabled=bool(
                raw.get("vosk_live_shadow_contract_enabled", False)
            ),
            vosk_shadow_invocation_plan_enabled=bool(
                raw.get("vosk_shadow_invocation_plan_enabled", False)
            ),
            vosk_shadow_pcm_reference_enabled=bool(
                raw.get("vosk_shadow_pcm_reference_enabled", False)
            ),
            vosk_shadow_asr_result_enabled=bool(
                raw.get("vosk_shadow_asr_result_enabled", False)
            ),
            vosk_shadow_recognition_preflight_enabled=bool(
                raw.get("vosk_shadow_recognition_preflight_enabled", False)
            ),
            vosk_shadow_invocation_attempt_enabled=bool(
                raw.get("vosk_shadow_invocation_attempt_enabled", False)
            ),
            vosk_shadow_controlled_recognition_enabled=bool(
                raw.get("vosk_shadow_controlled_recognition_enabled", False)
            ),
            vosk_shadow_controlled_recognition_dry_run_enabled=bool(
                raw.get("vosk_shadow_controlled_recognition_dry_run_enabled", False)
            ),
            vosk_shadow_controlled_recognition_result_enabled=bool(
                raw.get("vosk_shadow_controlled_recognition_result_enabled", False)
            ),
            vosk_shadow_candidate_comparison_enabled=bool(
                raw.get("vosk_shadow_candidate_comparison_enabled", False)
            ),
            vosk_command_english_model_path=str(
                vosk_paths.get("en", _DEFAULT_ENGLISH_VOSK_MODEL_PATH)
            ),
            vosk_command_polish_model_path=str(
                vosk_paths.get("pl", _DEFAULT_POLISH_VOSK_MODEL_PATH)
            ),
            vosk_command_sample_rate=int(
                raw.get("vosk_command_sample_rate", _DEFAULT_VOSK_SAMPLE_RATE)
            ),
            fallback_to_legacy_enabled=bool(
                raw.get("fallback_to_legacy_enabled", True)
            ),
            metrics_enabled=bool(raw.get("metrics_enabled", True)),
            shadow_mode_enabled=bool(raw.get("shadow_mode_enabled", False)),
            shadow_log_path=str(
                raw.get(
                    "shadow_log_path",
                    "var/data/voice_engine_v2_shadow.jsonl",
                )
            ),
            runtime_candidates_enabled=bool(
                raw.get("runtime_candidates_enabled", False)
            ),
            runtime_candidate_intent_allowlist=raw.get(
                "runtime_candidate_intent_allowlist",
                _DEFAULT_RUNTIME_CANDIDATE_INTENT_ALLOWLIST,
            ),
            runtime_candidate_log_path=str(
                raw.get(
                    "runtime_candidate_log_path",
                    "var/data/voice_engine_v2_runtime_candidates.jsonl",
                )
            ),
            pre_stt_shadow_enabled=bool(
                raw.get("pre_stt_shadow_enabled", False)
            ),
            pre_stt_shadow_log_path=str(
                raw.get(
                    "pre_stt_shadow_log_path",
                    "var/data/voice_engine_v2_pre_stt_shadow.jsonl",
                )
            ),
            legacy_removal_stage=str(
                raw.get(
                    "legacy_removal_stage",
                    "after_voice_engine_v2_runtime_acceptance",
                )
            ),
        )

    @staticmethod
    def _normalize_intent_allowlist(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            raw_items = value.split(",")
        elif isinstance(value, (list, tuple, set, frozenset)):
            raw_items = list(value)
        else:
            raw_items = []

        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            cleaned = str(item or "").strip()
            if not cleaned or cleaned in seen:
                continue
            normalized.append(cleaned)
            seen.add(cleaned)

        return tuple(normalized)
