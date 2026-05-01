from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from modules.core.voice_engine import (
    VoiceEngine,
    VoiceEngineSettings,
    VoiceTurnInput,
    VoiceTurnResult,
    VoiceTurnRoute,
)
from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.contracts import RouteDecision
from modules.runtime.voice_engine_v2.runtime_candidate_executor import (
    RuntimeCandidateExecutionPlan,
    RuntimeCandidateExecutionPlanBuilder,
)
from modules.runtime.voice_engine_v2.runtime_candidate_telemetry import (
    VoiceEngineV2RuntimeCandidateTelemetryRecord,
    VoiceEngineV2RuntimeCandidateTelemetryWriter,
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2RuntimeCandidateRequest:
    """Request for a guarded command-first runtime candidate decision."""

    turn_id: str
    transcript: str
    language_hint: CommandLanguage = CommandLanguage.UNKNOWN
    started_monotonic: float = 0.0
    speech_end_monotonic: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")
        if not self.transcript.strip():
            raise ValueError("transcript must not be empty")
        if self.started_monotonic < 0:
            raise ValueError("started_monotonic must not be negative")
        if self.speech_end_monotonic is not None and self.speech_end_monotonic < 0:
            raise ValueError("speech_end_monotonic must not be negative")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


@dataclass(frozen=True, slots=True)
class VoiceEngineV2RuntimeCandidateResult:
    """Result for a guarded command-first runtime candidate decision."""

    accepted: bool
    reason: str
    legacy_runtime_primary: bool
    request: VoiceEngineV2RuntimeCandidateRequest
    turn_result: VoiceTurnResult | None = None
    execution_plan: RuntimeCandidateExecutionPlan | None = None
    telemetry_written: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
        if self.accepted and self.execution_plan is None:
            raise ValueError("accepted runtime candidate requires execution_plan")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    @property
    def intent_key(self) -> str:
        if self.turn_result is None or self.turn_result.intent is None:
            return ""
        return self.turn_result.intent.key

    @property
    def route_decision(self) -> RouteDecision | None:
        if self.execution_plan is None:
            return None
        return self.execution_plan.route_decision

    def with_telemetry_written(
        self,
        telemetry_written: bool,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        return VoiceEngineV2RuntimeCandidateResult(
            accepted=self.accepted,
            reason=self.reason,
            legacy_runtime_primary=self.legacy_runtime_primary,
            request=self.request,
            turn_result=self.turn_result,
            execution_plan=self.execution_plan,
            telemetry_written=telemetry_written,
            metadata=self.metadata,
        )


class VoiceEngineV2RuntimeCandidateAdapter:
    """Guarded partial runtime adapter for selected command-first candidates."""

    def __init__(
        self,
        *,
        engine: VoiceEngine,
        settings: VoiceEngineSettings,
        execution_plan_builder: RuntimeCandidateExecutionPlanBuilder | None = None,
        telemetry_writer: VoiceEngineV2RuntimeCandidateTelemetryWriter | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._execution_plan_builder = (
            execution_plan_builder or RuntimeCandidateExecutionPlanBuilder()
        )
        self._telemetry_writer = telemetry_writer

    @property
    def settings(self) -> VoiceEngineSettings:
        return self._settings

    @property
    def allowlisted_intents(self) -> tuple[str, ...]:
        return self._settings.runtime_candidate_intent_allowlist

    @property
    def supported_intents(self) -> tuple[str, ...]:
        return self._execution_plan_builder.supported_intents

    @property
    def telemetry_path(self) -> str:
        if self._telemetry_writer is None:
            return ""
        return str(self._telemetry_writer.path)

    def process_transcript(
        self,
        *,
        turn_id: str,
        transcript: str,
        language_hint: CommandLanguage = CommandLanguage.UNKNOWN,
        started_monotonic: float = 0.0,
        speech_end_monotonic: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        request = VoiceEngineV2RuntimeCandidateRequest(
            turn_id=turn_id,
            transcript=transcript,
            language_hint=language_hint,
            started_monotonic=started_monotonic,
            speech_end_monotonic=speech_end_monotonic,
            metadata=metadata or {},
        )
        return self.process_request(request)

    def process_vosk_shadow_result(
        self,
        *,
        turn_id: str,
        result_metadata: Mapping[str, Any],
        started_monotonic: float = 0.0,
        speech_end_monotonic: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        """Evaluate a Vosk observe-only ASR result as a guarded runtime candidate.

        This method never executes an action. It only converts a safe
        observe-only Vosk command result into the existing runtime-candidate
        decision path, which still keeps the legacy runtime primary.
        """

        transcript = self._extract_vosk_shadow_transcript(result_metadata)
        language_hint = self._command_language_from_vosk_result(result_metadata)
        request_metadata = {
            **dict(metadata or {}),
            "candidate_source": "vosk_shadow_asr_result",
            "vosk_shadow_result": self._safe_vosk_shadow_result_summary(
                result_metadata
            ),
        }

        request = VoiceEngineV2RuntimeCandidateRequest(
            turn_id=turn_id,
            transcript=transcript or "<missing_vosk_shadow_transcript>",
            language_hint=language_hint,
            started_monotonic=started_monotonic,
            speech_end_monotonic=speech_end_monotonic,
            metadata=request_metadata,
        )

        if not self._settings.runtime_candidates_enabled:
            return self.process_request(request)

        if not self._settings.runtime_candidates_can_run:
            return self.process_request(request)

        rejection_reason = self._vosk_shadow_result_rejection_reason(
            result_metadata,
            transcript=transcript,
            language_hint=language_hint,
        )
        reminder_intent_key = self._vosk_shadow_result_allowed_reminder_intent_key(
            result_metadata,
            transcript=transcript,
        )
        if reminder_intent_key:
            rejection_reason = None
            language_value = str(result_metadata.get("language", "") or "").strip()
            if language_value not in {"pl", "en"}:
                language_value = language_hint

            if reminder_intent_key in self._settings.runtime_candidate_intent_allowlist:
                matched_phrase = str(result_metadata.get("matched_phrase", "") or "").strip()
                execution_plan = self._execution_plan_builder.build_plan_from_intent(
                    turn_id=request.turn_id,
                    intent_key=reminder_intent_key,
                    transcript=transcript,
                    language=language_value,
                    metadata=request_metadata,
                    confidence=float(result_metadata.get("confidence", 1.0) or 1.0),
                    matched_phrase=matched_phrase,
                )
                if execution_plan is not None:
                    return self._finalize(
                        VoiceEngineV2RuntimeCandidateResult(
                            accepted=True,
                            reason="accepted",
                            legacy_runtime_primary=True,
                            request=request,
                            execution_plan=execution_plan,
                            metadata={
                                **request_metadata,
                                "runtime_candidate": True,
                                "runtime_candidate_source_safe": True,
                                "runtime_candidates_can_run": True,
                                "intent_key": reminder_intent_key,
                                "legacy_action": execution_plan.spec.legacy_action,
                                "tool_name": execution_plan.spec.tool_name,
                                "route": "guided_reminder",
                                "language": language_value,
                                "llm_prevented": True,
                                "faster_whisper_prevented": True,
                                "command_execution_enabled": False,
                                "action_executed": False,
                            },
                        )
                    )

        if rejection_reason is not None:
            return self._finalize(
                self._rejected(
                    request=request,
                    reason=rejection_reason,
                    metadata={
                        **request_metadata,
                        "runtime_candidate": False,
                        "runtime_candidate_source_safe": False,
                    },
                )
            )

        # Dead reminder candidate branch removed: accepted results must include an execution_plan.

        return self.process_request(request)

    @staticmethod
    def _vosk_shadow_result_allowed_reminder_intent_key(
        result_metadata,
        *,
        transcript: str,
    ) -> str:
        """Return a safe guided reminder intent key from a trusted Vosk result."""

        allowed_intents = {"reminder.guided_start", "reminder.time_answer"}

        def safe_text(value: object) -> str:
            return str(value or "").strip()

        def payload_get(payload: object, key: str) -> object:
            getter = getattr(payload, "get", None)
            if callable(getter):
                try:
                    return getter(key)
                except Exception:
                    return None
            return None

        unsafe_boolean_keys = (
            "action_executed",
            "full_stt_prevented",
            "runtime_takeover",
            "runtime_integration",
            "command_execution_enabled",
            "faster_whisper_bypass_enabled",
            "independent_microphone_stream_started",
            "live_command_recognition_enabled",
        )
        for key in unsafe_boolean_keys:
            if bool(payload_get(result_metadata, key)):
                return ""

        if not (
            bool(payload_get(result_metadata, "recognized"))
            or bool(payload_get(result_metadata, "command_matched"))
        ):
            return ""

        payloads = [result_metadata]
        for nested_key in (
            "metadata",
            "result",
            "payload",
            "vosk_shadow_result",
            "vosk_shadow_asr_result",
        ):
            nested = payload_get(result_metadata, nested_key)
            if hasattr(nested, "get"):
                payloads.append(nested)

        for payload in payloads:
            for key in (
                "intent_key",
                "intent",
                "intent_id",
                "canonical_intent",
                "command_intent",
            ):
                intent_key = safe_text(payload_get(payload, key))
                if intent_key in allowed_intents:
                    return intent_key

        try:
            from modules.devices.audio.command_asr.command_grammar import (
                build_default_command_grammar,
            )

            result = build_default_command_grammar().match(transcript)
            if bool(getattr(result, "is_match", False)):
                intent_key = safe_text(getattr(result, "intent_key", ""))
                if intent_key in allowed_intents:
                    return intent_key
        except Exception:
            return ""

        return ""

    @classmethod
    def _vosk_shadow_result_has_allowed_reminder_intent(
        cls,
        result_metadata,
        *,
        transcript: str,
    ) -> bool:
        """Keep backward-compatible boolean reminder policy checks."""

        return bool(
            cls._vosk_shadow_result_allowed_reminder_intent_key(
                result_metadata,
                transcript=transcript,
            )
        )


    def process_request(
        self,
        request: VoiceEngineV2RuntimeCandidateRequest,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        if not self._settings.runtime_candidates_enabled:
            return self._finalize(
                self._rejected(
                    request=request,
                    reason="runtime_candidates_disabled",
                    metadata={"runtime_candidates_enabled": False},
                )
            )

        if not self._settings.runtime_candidates_can_run:
            return self._finalize(
                self._rejected(
                    request=request,
                    reason="runtime_candidates_not_safe",
                    metadata={
                        "runtime_candidates_enabled": self._settings.runtime_candidates_enabled,
                        "runtime_candidates_can_run": False,
                        "enabled": self._settings.enabled,
                        "mode": self._settings.mode,
                        "command_first_enabled": self._settings.command_first_enabled,
                        "fallback_to_legacy_enabled": self._settings.fallback_to_legacy_enabled,
                    },
                )
            )

        turn_result = self._engine.process_shadow_turn(
            VoiceTurnInput(
                turn_id=request.turn_id,
                transcript=request.transcript,
                started_monotonic=request.started_monotonic,
                speech_end_monotonic=request.speech_end_monotonic,
                language_hint=request.language_hint,
                source="voice_engine_v2_runtime_candidate",
            )
        )

        if turn_result.route is not VoiceTurnRoute.COMMAND:
            fallback_reason = ""
            if turn_result.fallback is not None:
                fallback_reason = turn_result.fallback.reason
            return self._finalize(
                self._rejected(
                    request=request,
                    reason=f"fallback_required:{fallback_reason or 'unknown'}",
                    turn_result=turn_result,
                    metadata={
                        "route": turn_result.route.value,
                        "fallback_used": turn_result.metrics.fallback_used,
                        "fallback_reason": turn_result.metrics.fallback_reason,
                    },
                )
            )

        if turn_result.intent is None:
            return self._finalize(
                self._rejected(
                    request=request,
                    reason="missing_intent",
                    turn_result=turn_result,
                    metadata={"route": turn_result.route.value},
                )
            )

        intent_key = turn_result.intent.key
        if (
            intent_key not in self._settings.runtime_candidate_intent_allowlist
            or intent_key not in self._execution_plan_builder.supported_intents
        ):
            return self._finalize(
                self._rejected(
                    request=request,
                    reason=f"intent_not_allowlisted:{intent_key}",
                    turn_result=turn_result,
                    metadata={
                        "route": turn_result.route.value,
                        "intent_key": intent_key,
                        "allowlist": list(
                            self._settings.runtime_candidate_intent_allowlist
                        ),
                        "supported_intents": list(
                            self._execution_plan_builder.supported_intents
                        ),
                    },
                )
            )

        execution_plan = self._execution_plan_builder.build_plan(
            turn_result=turn_result,
            transcript=request.transcript,
            metadata=request.metadata,
        )
        if execution_plan is None:
            return self._finalize(
                self._rejected(
                    request=request,
                    reason=f"unsupported_candidate_intent:{intent_key}",
                    turn_result=turn_result,
                    metadata={
                        "route": turn_result.route.value,
                        "intent_key": intent_key,
                        "supported_intents": list(self.supported_intents),
                    },
                )
            )

        return self._finalize(
            VoiceEngineV2RuntimeCandidateResult(
                accepted=True,
                reason="accepted",
                legacy_runtime_primary=True,
                request=request,
                turn_result=turn_result,
                execution_plan=execution_plan,
                metadata={
                    **dict(request.metadata),
                    "runtime_candidate": True,
                    "runtime_candidates_can_run": True,
                    "intent_key": intent_key,
                    "legacy_action": execution_plan.spec.legacy_action,
                    "tool_name": execution_plan.spec.tool_name,
                    "route": execution_plan.route_decision.kind.value,
                    "language": turn_result.language.value,
                },
            )
        )

    @staticmethod
    def _extract_vosk_shadow_transcript(result_metadata: Mapping[str, Any]) -> str:
        normalized_text = str(result_metadata.get("normalized_text", "") or "").strip()
        if normalized_text:
            return normalized_text

        transcript = str(result_metadata.get("transcript", "") or "").strip()
        return transcript

    @staticmethod
    def _command_language_from_vosk_result(
        result_metadata: Mapping[str, Any],
    ) -> CommandLanguage:
        language = str(result_metadata.get("language", "") or "").strip().lower()
        if language == "en":
            return CommandLanguage.ENGLISH
        if language == "pl":
            return CommandLanguage.POLISH
        return CommandLanguage.UNKNOWN

    @staticmethod
    def _vosk_shadow_result_rejection_reason(
        result_metadata: Mapping[str, Any],
        *,
        transcript: str,
        language_hint: CommandLanguage,
    ) -> str | None:
        unsafe_true_fields = (
            "raw_pcm_included",
            "action_executed",
            "full_stt_prevented",
            "runtime_takeover",
            "runtime_integration",
            "command_execution_enabled",
            "faster_whisper_bypass_enabled",
            "microphone_stream_started",
            "independent_microphone_stream_started",
            "live_command_recognition_enabled",
        )

        for field_name in unsafe_true_fields:
            if bool(result_metadata.get(field_name, False)):
                return f"unsafe_vosk_shadow_result:{field_name}"

        if not bool(result_metadata.get("recognition_attempted", False)):
            return "vosk_shadow_result_not_attempted"

        if not bool(result_metadata.get("recognition_invocation_performed", False)):
            return "vosk_shadow_result_not_invoked"

        if not bool(result_metadata.get("recognized", False)):
            return "vosk_shadow_result_not_recognized"

        if not bool(result_metadata.get("command_matched", False)):
            return "vosk_shadow_result_not_matched"

        if not transcript.strip():
            return "vosk_shadow_result_missing_transcript"

        if language_hint is CommandLanguage.UNKNOWN:
            return "vosk_shadow_result_language_unknown"

        confidence = float(result_metadata.get("confidence", 0.0) or 0.0)
        if confidence < 0.80:
            return "vosk_shadow_result_confidence_below_threshold"

        return None

    @staticmethod
    def _safe_vosk_shadow_result_summary(
        result_metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        safe_fields = (
            "result_stage",
            "result_version",
            "reason",
            "recognizer_name",
            "recognizer_enabled",
            "recognition_invocation_performed",
            "recognition_attempted",
            "recognized",
            "command_matched",
            "transcript",
            "normalized_text",
            "language",
            "confidence",
            "turn_id",
            "hook",
            "source",
            "publish_stage",
            "segment_present",
            "segment_reason",
            "segment_audio_duration_ms",
            "segment_audio_sample_count",
            "segment_published_byte_count",
            "segment_sample_rate",
            "segment_pcm_encoding",
            "pcm_retrieval_performed",
            "raw_pcm_included",
            "action_executed",
            "full_stt_prevented",
            "runtime_takeover",
            "runtime_integration",
            "command_execution_enabled",
            "faster_whisper_bypass_enabled",
            "microphone_stream_started",
            "independent_microphone_stream_started",
            "live_command_recognition_enabled",
        )
        return {
            field_name: result_metadata.get(field_name)
            for field_name in safe_fields
            if field_name in result_metadata
        }

    def _finalize(
        self,
        result: VoiceEngineV2RuntimeCandidateResult,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        if self._telemetry_writer is None:
            return result

        record = self._record_from_result(result)
        telemetry_written = self._telemetry_writer.write_safely(record)
        return result.with_telemetry_written(telemetry_written)

    @staticmethod
    def _record_from_result(
        result: VoiceEngineV2RuntimeCandidateResult,
    ) -> VoiceEngineV2RuntimeCandidateTelemetryRecord:
        turn_result = result.turn_result
        route = ""
        language = ""
        fallback_reason = ""
        metrics: dict[str, Any] = {}
        if turn_result is not None:
            route = turn_result.route.value
            language = turn_result.language.value
            fallback_reason = str(
                getattr(turn_result.metrics, "fallback_reason", "") or ""
            )
            metrics = VoiceEngineV2RuntimeCandidateAdapter._metrics_snapshot(
                turn_result.metrics
            )

        intent_key = ""
        intent_action = ""
        if turn_result is not None and turn_result.intent is not None:
            intent_key = turn_result.intent.key
            intent_action = turn_result.intent.action

        route_kind = ""
        primary_intent = ""
        llm_prevented = False
        if result.route_decision is not None:
            route_kind = str(
                getattr(
                    result.route_decision.kind,
                    "value",
                    result.route_decision.kind,
                )
            )
            primary_intent = str(result.route_decision.primary_intent or "")
            llm_prevented = bool(
                result.route_decision.metadata.get("llm_prevented", False)
            )

        return VoiceEngineV2RuntimeCandidateTelemetryRecord.create(
            turn_id=result.request.turn_id,
            transcript=result.request.transcript,
            accepted=result.accepted,
            reason=result.reason,
            legacy_runtime_primary=result.legacy_runtime_primary,
            voice_engine_route=route,
            voice_engine_intent=intent_key,
            voice_engine_action=intent_action,
            language=language,
            fallback_reason=fallback_reason,
            route_kind=route_kind,
            primary_intent=primary_intent,
            llm_prevented=llm_prevented,
            metrics=metrics,
            metadata={**dict(result.request.metadata), **dict(result.metadata)},
        )



    @staticmethod
    def _metrics_snapshot(metrics: Any) -> dict[str, Any]:
        """Return a stable telemetry snapshot without depending on one metric name.

        Runtime candidate telemetry must never break command execution if the
        VoiceEngineMetrics model changes. Keep both the Stage 20B compatibility
        key and the current canonical metric key when possible.
        """

        speech_end_to_finish_ms = getattr(
            metrics,
            "speech_end_to_finish_ms",
            None,
        )
        speech_end_to_action_ms = getattr(
            metrics,
            "speech_end_to_action_ms",
            speech_end_to_finish_ms,
        )

        command_stt_ms = getattr(
            metrics,
            "command_stt_ms",
            getattr(metrics, "command_recognition_ms", None),
        )
        resolver_ms = getattr(
            metrics,
            "resolver_ms",
            getattr(metrics, "intent_resolver_ms", None),
        )
        action_dispatch_ms = getattr(
            metrics,
            "action_dispatch_ms",
            getattr(metrics, "action_ms", None),
        )

        return {
            "speech_end_to_action_ms": speech_end_to_action_ms,
            "speech_end_to_finish_ms": speech_end_to_finish_ms,
            "command_stt_ms": command_stt_ms,
            "resolver_ms": resolver_ms,
            "action_dispatch_ms": action_dispatch_ms,
            "fallback_used": bool(getattr(metrics, "fallback_used", False)),
            "fallback_reason": str(getattr(metrics, "fallback_reason", "") or ""),
        }


    @staticmethod
    def _rejected(
        *,
        request: VoiceEngineV2RuntimeCandidateRequest,
        reason: str,
        turn_result: VoiceTurnResult | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        return VoiceEngineV2RuntimeCandidateResult(
            accepted=False,
            reason=reason,
            legacy_runtime_primary=True,
            request=request,
            turn_result=turn_result,
            metadata=metadata or {},
        )