from __future__ import annotations

import time
from typing import Any


from modules.shared.logging.logger import append_log, log_exception


class CoreAssistantInteractionMixin:
    def handle_command(self, text: str) -> bool:
        self.interrupt_controller.clear()
        self._last_interrupt_snapshot = {}
        self._tick_ai_broker()

        cleaned = str(text or "").strip()
        if not cleaned:
            return True

        telemetry = self._start_turn_telemetry(cleaned)
        self._last_fast_lane_route_snapshot = {}

        try:
            prepared_started = time.perf_counter()
            prepared = self._prepare_command(
                cleaned,
                source=telemetry.get("input_source", "voice"),
                capture_phase=str(telemetry.get("capture_phase", "") or ""),
                capture_mode=str(telemetry.get("stt_mode", "") or ""),
                capture_backend=str(telemetry.get("stt_backend", "") or ""),
                capture_metadata=dict(telemetry.get("capture_metadata", {}) or {}),
            )
            telemetry["prepare_ms"] = self._elapsed_ms(prepared_started)

            if prepared["ignore"]:
                telemetry["result"] = "ignored"
                return True

            language_started = time.perf_counter()
            command_lang = self._commit_language(prepared["language"])
            telemetry["language_commit_ms"] = self._elapsed_ms(language_started)
            telemetry["language"] = command_lang
            telemetry["input_source"] = getattr(prepared["source"], "value", str(prepared["source"]))
            telemetry["capture_phase"] = str(
                prepared.get("capture_phase", telemetry.get("capture_phase", "")) or ""
            )
            telemetry["stt_mode"] = str(
                prepared.get("capture_mode", telemetry.get("stt_mode", "")) or ""
            )
            telemetry["stt_backend"] = str(
                prepared.get("capture_backend", telemetry.get("stt_backend", "")) or ""
            )
            routing_text = prepared["routing_text"]

            if not prepared.get("already_remembered", False):
                remember_started = time.perf_counter()
                self._remember_user_turn(
                    cleaned,
                    language=command_lang,
                    metadata={
                        "source": prepared["source"].value,
                        "normalized_text": prepared["normalized_text"],
                    },
                )
                telemetry["remember_user_ms"] = self._elapsed_ms(remember_started)

            if prepared["cancel_requested"]:
                cancel_started = time.perf_counter()
                result = self._cancel_active_request(command_lang)
                telemetry["cancel_ms"] = self._elapsed_ms(cancel_started)
                telemetry["result"] = "cancel_request"
                return result

            pending_started = time.perf_counter()
            pending_result = self._handle_pending_state(prepared)
            telemetry["pending_ms"] = self._elapsed_ms(pending_started)

            if pending_result is not None:
                telemetry["result"] = "pending_flow"
                return bool(pending_result)

            candidate_started = time.perf_counter()
            candidate_result = self._try_handle_voice_engine_v2_runtime_candidate(
                telemetry=telemetry,
                prepared=prepared,
                transcript=cleaned,
                language=command_lang,
            )
            if candidate_result is not None:
                telemetry["voice_engine_v2_candidate_ms"] = self._elapsed_ms(
                    candidate_started
                )
                telemetry["result"] = "voice_engine_v2_runtime_candidate"
                telemetry["handled"] = bool(candidate_result)
                return bool(candidate_result)

            fast_lane_started = time.perf_counter()
            fast_lane_result = self._handle_fast_lane(prepared)
            telemetry["fast_lane_ms"] = self._elapsed_ms(fast_lane_started)

            if fast_lane_result is not None:
                fast_lane_route = dict(getattr(self, "_last_fast_lane_route_snapshot", {}) or {})
                telemetry["route_kind"] = str(fast_lane_route.get("route_kind", "") or "")
                telemetry["route_confidence"] = float(
                    fast_lane_route.get("route_confidence", 0.0) or 0.0
                )
                telemetry["primary_intent"] = str(
                    fast_lane_route.get("primary_intent", "") or ""
                )
                telemetry["topics"] = list(fast_lane_route.get("topics", []) or [])
                telemetry["route_notes"] = list(fast_lane_route.get("route_notes", []) or [])
                telemetry["route_metadata"] = dict(
                    fast_lane_route.get("route_metadata", {}) or {}
                )

                benchmark_service = getattr(self, "turn_benchmark_service", None)
                if benchmark_service is not None and telemetry["route_kind"]:
                    note_route_resolved = getattr(benchmark_service, "note_route_resolved", None)
                    if callable(note_route_resolved):
                        try:
                            note_route_resolved(
                                route_kind=telemetry["route_kind"],
                                primary_intent=telemetry["primary_intent"],
                                confidence=telemetry["route_confidence"],
                            )
                        except Exception as error:
                            log_exception("Failed to note fast-lane route benchmark telemetry", error)

                telemetry["result"] = "fast_lane"
                telemetry["handled"] = bool(fast_lane_result)
                legacy_result = bool(fast_lane_result)
                self._observe_voice_engine_v2_shadow_turn(
                    telemetry=telemetry,
                    transcript=cleaned,
                    language=command_lang,
                    legacy_route=telemetry["route_kind"],
                    legacy_intent_key=telemetry["primary_intent"] or None,
                    route_turn_id="",
                    route_path="fast_lane",
                )
                return legacy_result

            self.voice_session.transition_to_routing(detail="route_command")

            route_context = {
                "input_source": telemetry.get("input_source", "voice"),
                "capture_phase": telemetry.get("capture_phase", ""),
                "capture_mode": telemetry.get("stt_mode", ""),
                "capture_backend": telemetry.get("stt_backend", ""),
            }

            routing_started = time.perf_counter()
            # Router itself is fast (deterministic + optional semantic classifier).
            # Thinking-ack here used to fire for every non-fast-lane turn, which
            # caused audible overlap with the real reply. The dialogue flow arms
            # its own thinking-ack only when an LLM generation is actually in
            # progress, which is the only case where the user can hear silence.
            routed = self._route_command(
                routing_text,
                preferred_language=command_lang,
                context=route_context,
            )
            telemetry["router_ms"] = self._elapsed_ms(routing_started)

            route = self._coerce_route_decision(
                routed,
                raw_text=cleaned,
                normalized_text=prepared["normalized_text"],
                language=command_lang,
                context=route_context,
            )

            telemetry["route_kind"] = getattr(route.kind, "value", str(route.kind))
            telemetry["route_confidence"] = float(getattr(route, "confidence", 0.0) or 0.0)
            telemetry["primary_intent"] = str(getattr(route, "primary_intent", "") or "")
            telemetry["topics"] = list(getattr(route, "conversation_topics", []) or [])
            telemetry["route_notes"] = list(getattr(route, "notes", []) or [])
            telemetry["route_metadata"] = dict(getattr(route, "metadata", {}) or {})

            route_metadata = dict(getattr(route, "metadata", {}) or {})
            telemetry["capture_phase"] = str(
                route_metadata.get("capture_phase", telemetry.get("capture_phase", "")) or ""
            )
            telemetry["stt_mode"] = str(
                route_metadata.get("capture_mode", telemetry.get("stt_mode", "")) or ""
            )
            telemetry["stt_backend"] = str(
                route_metadata.get("capture_backend", telemetry.get("stt_backend", "")) or ""
            )
            benchmark_service = getattr(self, "turn_benchmark_service", None)
            if benchmark_service is not None:
                note_route_resolved = getattr(benchmark_service, "note_route_resolved", None)
                if callable(note_route_resolved):
                    try:
                        note_route_resolved(
                            route_kind=telemetry["route_kind"],
                            primary_intent=telemetry["primary_intent"],
                            confidence=telemetry["route_confidence"],
                        )
                    except Exception as error:
                        log_exception("Failed to note route benchmark telemetry", error)

            log_route_decision = getattr(self.command_flow, "log_route_decision", None)
            if callable(log_route_decision):
                try:
                    log_route_decision(route)
                except Exception as error:
                    log_exception("Route decision logging failed", error)

            dispatch_started = time.perf_counter()

            if route.kind == self._route_kind_action():
                self.pending_confirmation = None
                result = self._execute_action_route(route, command_lang)
                telemetry["result"] = "action_route"
            elif route.kind == self._route_kind_mixed():
                self.pending_confirmation = None
                result = self._handle_mixed_route(route, command_lang)
                telemetry["result"] = "mixed_route"
            elif route.kind == self._route_kind_conversation():
                self.pending_confirmation = None
                result = self._handle_conversation_route(route, command_lang)
                telemetry["result"] = "conversation_route"
            else:
                result = self._handle_unclear_route(route, command_lang)
                telemetry["result"] = "unclear_route"

            telemetry["dispatch_ms"] = self._elapsed_ms(dispatch_started)
            telemetry["handled"] = bool(result)
            legacy_result = bool(result)
            self._observe_voice_engine_v2_shadow_turn(
                telemetry=telemetry,
                transcript=cleaned,
                language=command_lang,
                legacy_route=telemetry["route_kind"],
                legacy_intent_key=telemetry["primary_intent"] or None,
                route_turn_id=str(getattr(route, "turn_id", "") or ""),
                route_path="normal_route",
            )
            return legacy_result

        finally:
            self._finish_turn_telemetry(telemetry)

    def _try_handle_voice_engine_v2_runtime_candidate(
        self,
        *,
        telemetry: dict[str, Any],
        prepared: dict[str, Any],
        transcript: str,
        language: str,
    ) -> bool | None:
        """Try a guarded Voice Engine v2 runtime candidate.

        This is a partial, allowlisted command-first path. It is fail-open and
        returns None for every disabled, unsafe or uncertain case so the legacy
        runtime continues unchanged. Concrete action behaviour stays in
        ActionFlow; this mixin only orchestrates the candidate gate and generic
        route dispatch.
        """

        if not str(transcript or "").strip():
            return None
        if not self._voice_engine_v2_runtime_candidates_enabled():
            return None

        adapter = self._voice_engine_v2_runtime_candidate_adapter()
        if adapter is None:
            telemetry["voice_engine_v2_candidate_skipped"] = "adapter_unavailable"
            return None

        process_transcript = getattr(adapter, "process_transcript", None)
        if not callable(process_transcript):
            telemetry["voice_engine_v2_candidate_skipped"] = "process_unavailable"
            return None

        candidate_text = str(
            prepared.get("routing_text")
            or prepared.get("raw_text")
            or transcript
            or ""
        ).strip()
        if not candidate_text:
            return None

        try:
            result = process_transcript(
                turn_id=self._voice_engine_v2_shadow_turn_id(
                    telemetry=telemetry,
                    route_turn_id="",
                ),
                transcript=candidate_text,
                language_hint=self._voice_engine_v2_shadow_language_hint(language),
                started_monotonic=self._voice_engine_v2_shadow_started_monotonic(
                    telemetry
                ),
                speech_end_monotonic=self._voice_engine_v2_shadow_speech_end_monotonic(
                    telemetry
                ),
                metadata={
                    "source": "voice_engine_v2_runtime_candidate",
                    "input_source": str(telemetry.get("input_source", "") or ""),
                    "capture_phase": str(telemetry.get("capture_phase", "") or ""),
                    "capture_mode": str(telemetry.get("stt_mode", "") or ""),
                    "capture_backend": str(telemetry.get("stt_backend", "") or ""),
                },
            )
        except Exception as error:
            telemetry["voice_engine_v2_candidate_error"] = type(error).__name__
            log_exception("Voice Engine v2 runtime candidate failed safely", error)
            return None

        telemetry["voice_engine_v2_candidate_invoked"] = True
        telemetry["voice_engine_v2_candidate_accepted"] = bool(
            getattr(result, "accepted", False)
        )
        telemetry["voice_engine_v2_candidate_reason"] = str(
            getattr(result, "reason", "") or ""
        )

        if not bool(getattr(result, "accepted", False)):
            return None

        route = getattr(result, "route_decision", None)
        if route is None:
            telemetry["voice_engine_v2_candidate_skipped"] = "missing_route_decision"
            return None

        self._store_voice_engine_v2_candidate_route_telemetry(
            telemetry=telemetry,
            route=route,
            result=result,
        )
        self._note_voice_engine_v2_candidate_route(telemetry=telemetry)
        self._clear_voice_engine_v2_candidate_context()
        self._mark_voice_engine_v2_candidate_routing(route)
        self._commit_language(str(getattr(route, "language", language) or language))

        return bool(self._execute_action_route(route, str(route.language or language)))

    def _voice_engine_v2_runtime_candidates_enabled(self) -> bool:
        settings = getattr(self, "settings", {})
        if isinstance(settings, dict):
            voice_engine_cfg = settings.get("voice_engine", {})
            if isinstance(voice_engine_cfg, dict):
                return bool(voice_engine_cfg.get("runtime_candidates_enabled", False))
        return False

    def _voice_engine_v2_runtime_candidate_adapter(self) -> Any | None:
        adapter = getattr(self, "voice_engine_v2_runtime_candidate_adapter", None)
        if adapter is not None:
            return adapter

        runtime = getattr(self, "runtime", None)
        runtime_metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}
        if isinstance(runtime_metadata, dict):
            return runtime_metadata.get("voice_engine_v2_runtime_candidate_adapter")
        return None

    @staticmethod
    def _store_voice_engine_v2_candidate_route_telemetry(
        *,
        telemetry: dict[str, Any],
        route: Any,
        result: Any,
    ) -> None:
        telemetry["route_kind"] = str(getattr(route.kind, "value", route.kind) or "")
        telemetry["route_confidence"] = float(getattr(route, "confidence", 0.0) or 0.0)
        telemetry["primary_intent"] = str(getattr(route, "primary_intent", "") or "")
        telemetry["topics"] = list(getattr(route, "conversation_topics", []) or [])
        telemetry["route_notes"] = list(getattr(route, "notes", []) or [])
        telemetry["route_metadata"] = dict(getattr(route, "metadata", {}) or {})

        turn_result = getattr(result, "turn_result", None)
        intent = getattr(turn_result, "intent", None) if turn_result is not None else None
        if intent is not None:
            telemetry["voice_engine_v2_candidate_intent"] = str(
                getattr(intent, "key", "") or ""
            )

    def _note_voice_engine_v2_candidate_route(
        self,
        *,
        telemetry: dict[str, Any],
    ) -> None:
        benchmark_service = getattr(self, "turn_benchmark_service", None)
        if benchmark_service is None:
            return

        note_route_resolved = getattr(benchmark_service, "note_route_resolved", None)
        if not callable(note_route_resolved):
            return

        try:
            note_route_resolved(
                route_kind=str(telemetry.get("route_kind", "") or ""),
                primary_intent=str(telemetry.get("primary_intent", "") or ""),
                confidence=float(telemetry.get("route_confidence", 0.0) or 0.0),
            )
        except Exception as error:
            log_exception(
                "Failed to note Voice Engine v2 candidate route benchmark telemetry",
                error,
            )

    def _clear_voice_engine_v2_candidate_context(self) -> None:
        clear_context = getattr(self, "_clear_interaction_context", None)
        if callable(clear_context):
            try:
                clear_context(close_active_window=False)
                return
            except TypeError:
                try:
                    clear_context()
                    return
                except Exception:
                    pass
            except Exception:
                pass

        if hasattr(self, "pending_confirmation"):
            self.pending_confirmation = None
        if hasattr(self, "pending_follow_up"):
            self.pending_follow_up = None

    def _mark_voice_engine_v2_candidate_routing(self, route: Any) -> None:
        voice_session = getattr(self, "voice_session", None)
        if voice_session is None:
            return

        detail = f"voice_engine_v2_candidate:{getattr(route, 'primary_intent', 'unknown')}"
        set_state = getattr(voice_session, "set_state", None)
        if callable(set_state):
            try:
                set_state("routing", detail=detail)
                return
            except TypeError:
                try:
                    set_state("routing")
                    return
                except Exception:
                    pass
            except Exception:
                pass

        transition_to_routing = getattr(voice_session, "transition_to_routing", None)
        if callable(transition_to_routing):
            try:
                transition_to_routing(detail=detail)
            except Exception:
                pass


    def _observe_voice_engine_v2_shadow_turn(
        self,
        *,
        telemetry: dict[str, Any],
        transcript: str,
        language: str,
        legacy_route: str,
        legacy_intent_key: str | None,
        route_turn_id: str,
        route_path: str,
    ) -> None:
        """Observe a completed legacy turn in Voice Engine v2 shadow mode.

        The legacy live path has already executed before this method is called.
        This method is fail-open and must never change the legacy return value,
        trigger TTS, execute Visual Shell actions, or raise into the live path.
        """

        if not str(transcript or "").strip():
            return
        if not self._voice_engine_v2_shadow_mode_enabled():
            return

        hook = self._voice_engine_v2_shadow_runtime_hook()
        if hook is None:
            telemetry["voice_engine_v2_shadow_skipped"] = "hook_unavailable"
            return

        observe_legacy_turn = getattr(hook, "observe_legacy_turn", None)
        if not callable(observe_legacy_turn):
            telemetry["voice_engine_v2_shadow_skipped"] = "observe_unavailable"
            return

        try:
            result = observe_legacy_turn(
                turn_id=self._voice_engine_v2_shadow_turn_id(
                    telemetry=telemetry,
                    route_turn_id=route_turn_id,
                ),
                transcript=str(transcript or "").strip(),
                legacy_route=str(legacy_route or "").strip(),
                legacy_intent_key=legacy_intent_key,
                language_hint=self._voice_engine_v2_shadow_language_hint(language),
                started_monotonic=self._voice_engine_v2_shadow_started_monotonic(
                    telemetry
                ),
                speech_end_monotonic=self._voice_engine_v2_shadow_speech_end_monotonic(
                    telemetry
                ),
                metadata={
                    "source": "legacy_runtime_transcript_tap",
                    "route_path": str(route_path or "").strip(),
                    "handled": bool(telemetry.get("handled", False)),
                    "legacy_result": str(telemetry.get("result", "") or ""),
                    "route_kind": str(telemetry.get("route_kind", "") or ""),
                    "primary_intent": str(telemetry.get("primary_intent", "") or ""),
                    "dispatch_ms": self._safe_metric_float(
                        telemetry.get("dispatch_ms", 0.0)
                    ),
                    "route_confidence": self._safe_metric_float(
                        telemetry.get("route_confidence", 0.0)
                    ),
                    "input_source": str(telemetry.get("input_source", "") or ""),
                    "capture_phase": str(telemetry.get("capture_phase", "") or ""),
                },
            )
        except Exception as error:
            telemetry["voice_engine_v2_shadow_error"] = type(error).__name__
            log_exception("Voice Engine v2 shadow transcript tap failed safely", error)
            return

        telemetry["voice_engine_v2_shadow_invoked"] = True
        if result is not None:
            telemetry["voice_engine_v2_shadow_enabled"] = bool(
                getattr(result, "enabled", False)
            )
            telemetry["voice_engine_v2_shadow_reason"] = str(
                getattr(result, "reason", "") or ""
            )
            telemetry["voice_engine_v2_shadow_intent"] = str(
                getattr(result, "voice_engine_intent_key", "") or ""
            )
            telemetry["voice_engine_v2_shadow_action_executed"] = bool(
                getattr(result, "action_executed", False)
            )

    def _voice_engine_v2_shadow_mode_enabled(self) -> bool:
        settings = getattr(self, "settings", {})
        if isinstance(settings, dict):
            voice_engine_cfg = settings.get("voice_engine", {})
            if isinstance(voice_engine_cfg, dict):
                return bool(voice_engine_cfg.get("shadow_mode_enabled", False))
        return False

    def _voice_engine_v2_shadow_runtime_hook(self) -> Any | None:
        hook = getattr(self, "voice_engine_v2_shadow_runtime_hook", None)
        if hook is not None:
            return hook

        runtime = getattr(self, "runtime", None)
        runtime_metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}
        if isinstance(runtime_metadata, dict):
            return runtime_metadata.get("voice_engine_v2_shadow_runtime_hook")
        return None

    @staticmethod
    def _voice_engine_v2_shadow_language_hint(language: str):
        from modules.devices.audio.command_asr import CommandLanguage

        normalized = str(language or "").strip().lower()
        if normalized.startswith("pl"):
            return CommandLanguage.POLISH
        if normalized.startswith("en"):
            return CommandLanguage.ENGLISH
        return CommandLanguage.UNKNOWN

    @staticmethod
    def _voice_engine_v2_shadow_turn_id(
        *,
        telemetry: dict[str, Any],
        route_turn_id: str,
    ) -> str:
        for candidate in (
            route_turn_id,
            telemetry.get("benchmark_turn_id", ""),
        ):
            cleaned = str(candidate or "").strip()
            if cleaned:
                return cleaned

        from modules.runtime.contracts import create_turn_id

        return create_turn_id()

    @staticmethod
    def _voice_engine_v2_shadow_started_monotonic(telemetry: dict[str, Any]) -> float:
        try:
            return max(0.0, float(telemetry.get("started_at", 0.0) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _voice_engine_v2_shadow_speech_end_monotonic(
        telemetry: dict[str, Any],
    ) -> float | None:
        capture_metadata = telemetry.get("capture_metadata", {})
        if not isinstance(capture_metadata, dict):
            return None

        for key in (
            "capture_finished_at_monotonic",
            "speech_end_monotonic",
            "ended_at_monotonic",
        ):
            value = capture_metadata.get(key)
            if value is None:
                continue
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                continue
        return None


    def request_interrupt(
        self,
        *,
        reason: str = "manual_interrupt",
        source: str = "assistant",
        metadata: dict | None = None,
    ) -> None:
        interrupt_metadata = dict(metadata or {})
        snapshot = self.interrupt_controller.request(
            reason=reason,
            source=source,
            metadata=interrupt_metadata,
        )
        self._last_interrupt_snapshot = {
            "requested": bool(getattr(snapshot, "requested", True)),
            "generation": int(getattr(snapshot, "generation", 0) or 0),
            "reason": str(getattr(snapshot, "reason", reason) or reason).strip(),
            "source": str(getattr(snapshot, "source", source) or source).strip(),
            "kind": str(interrupt_metadata.get("interrupt_kind", "manual")).strip() or "manual",
            "requested_at_monotonic": float(
                getattr(snapshot, "requested_at_monotonic", 0.0) or 0.0
            ),
            "metadata": interrupt_metadata,
        }

        benchmark_service = getattr(self, "turn_benchmark_service", None)
        annotate = getattr(benchmark_service, "annotate_last_completed_turn", None)
        if callable(annotate):
            try:
                annotate(interrupt_snapshot=dict(self._last_interrupt_snapshot))
            except Exception:
                pass

        mark_interrupt_requested = getattr(self.voice_session, "mark_interrupt_requested", None)
        if callable(mark_interrupt_requested):
            try:
                mark_interrupt_requested(detail=reason)
            except Exception:
                pass

    def _interrupt_requested(self) -> bool:
        return bool(self.interrupt_controller.is_requested())

    def _start_turn_telemetry(self, text: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        benchmark_turn_id = ""
        capture = self._consume_last_input_capture()
        capture_handoff = dict(getattr(self, "_last_capture_handoff", {}) or {})

        input_source = str(capture.get("input_source") or "voice").strip().lower() or "voice"
        capture_language = str(capture.get("language") or self.last_language or "").strip().lower()
        current_language = capture_language or self.last_language
        stt_backend = str(capture.get("backend_label") or "").strip()
        stt_mode = str(capture.get("mode") or "").strip()
        stt_phase = str(capture.get("phase") or "").strip()
        stt_latency_ms = self._safe_metric_float(capture.get("latency_ms"))
        stt_audio_duration_ms = self._safe_metric_float(capture.get("audio_duration_ms"))
        stt_confidence = self._safe_metric_float(capture.get("confidence"))

        benchmark_service = getattr(self, "turn_benchmark_service", None)
        if benchmark_service is not None:
            begin_turn = getattr(benchmark_service, "begin_turn", None)
            if callable(begin_turn):
                try:
                    benchmark_turn_id = str(
                        begin_turn(
                            user_text=str(text or "").strip(),
                            language=current_language,
                            input_source=input_source,
                        )
                        or ""
                    ).strip()
                except Exception as error:
                    log_exception("Failed to begin turn benchmark trace", error)

        self._last_response_stream_report = None

        return {
            "started_at": started_at,
            "benchmark_turn_id": benchmark_turn_id,
            "user_text": str(text or "").strip(),
            "input_source": input_source,
            "language": current_language,
            "prepare_ms": 0.0,
            "language_commit_ms": 0.0,
            "remember_user_ms": 0.0,
            "cancel_ms": 0.0,
            "pending_ms": 0.0,
            "fast_lane_ms": 0.0,
            "router_ms": 0.0,
            "dispatch_ms": 0.0,
            "total_ms": 0.0,
            "route_kind": "",
            "route_confidence": 0.0,
            "primary_intent": "",
            "topics": [],
            "result": "",
            "stt_backend": stt_backend,
            "stt_mode": stt_mode,
            "stt_phase": stt_phase,
            "capture_phase": stt_phase,
            "capture_metadata": dict(capture.get("metadata") or {}),
            "capture_handoff": capture_handoff,
            "stt_latency_ms": stt_latency_ms,
            "stt_audio_duration_ms": stt_audio_duration_ms,
            "stt_confidence": stt_confidence,
        }

    def _finish_turn_telemetry(self, telemetry: dict[str, Any]) -> None:
        try:
            total_ms = (time.perf_counter() - float(telemetry["started_at"])) * 1000.0
        except Exception:
            total_ms = 0.0

        telemetry["total_ms"] = total_ms

        llm_snapshot = self._collect_llm_snapshot()
        response_report = self._collect_response_stream_report()
        response_delivery = self._collect_response_delivery_snapshot()

        if response_delivery:
            telemetry["response_source"] = str(response_delivery.get("source", "") or "").strip()
            telemetry["response_reply_source"] = str(response_delivery.get("reply_source", "") or "").strip()
            telemetry["response_display_title"] = str(response_delivery.get("display_title", "") or "").strip()
            telemetry["response_stream_mode"] = str(response_delivery.get("stream_mode", "") or "").strip()
            telemetry["response_memory_metadata"] = dict(
                response_delivery.get("extra_metadata", {}) or {}
            )

            response_meta = dict(response_delivery.get("extra_metadata", {}) or {})
            telemetry["action_name"] = str(response_meta.get("action", "") or "").strip()
            telemetry["action_source"] = str(response_meta.get("action_source", "") or "").strip()
            telemetry["action_confidence"] = self._safe_metric_float(
                response_meta.get("action_confidence", 0.0)
            )

        skill_snapshot = self._collect_skill_result_snapshot()
        if skill_snapshot:
            telemetry["skill_action"] = str(skill_snapshot.get("action", "") or "").strip()
            telemetry["skill_status"] = str(skill_snapshot.get("status", "") or "").strip()
            telemetry["skill_handled"] = bool(skill_snapshot.get("handled", False))
            telemetry["skill_response_delivered"] = bool(
                skill_snapshot.get("response_delivered", False)
            )
            telemetry["skill_source"] = str(skill_snapshot.get("source", "") or "").strip()
            telemetry["skill_latency_ms"] = self._safe_metric_float(
                skill_snapshot.get("latency_ms", 0.0)
            )
            telemetry["skill_response_kind"] = str(
                skill_snapshot.get("response_kind", "") or ""
            ).strip()
        pending_snapshot = self._collect_pending_flow_snapshot()
        if pending_snapshot:
            telemetry["pending_consumed_by"] = str(
                pending_snapshot.get("consumed_by", "") or ""
            ).strip()
            telemetry["pending_kind"] = str(
                pending_snapshot.get("pending_kind", "") or ""
            ).strip()
            telemetry["pending_type"] = str(
                pending_snapshot.get("pending_type", "") or ""
            ).strip()
            telemetry["pending_language"] = str(
                pending_snapshot.get("language", "") or ""
            ).strip()
            telemetry["pending_keeps_state"] = bool(
                pending_snapshot.get("keeps_pending_state", False)
            )
            telemetry["pending_metadata"] = dict(
                pending_snapshot.get("metadata", {}) or {}
            )

        interrupt_snapshot = self._collect_interrupt_snapshot()
        if interrupt_snapshot:
            telemetry["interrupt_requested"] = bool(interrupt_snapshot.get("requested", False))
            telemetry["interrupt_generation"] = int(
                self._safe_metric_float(interrupt_snapshot.get("generation", 0.0))
            )
            telemetry["interrupt_reason"] = str(
                interrupt_snapshot.get("reason", "") or ""
            ).strip()
            telemetry["interrupt_source"] = str(
                interrupt_snapshot.get("source", "") or ""
            ).strip()
            telemetry["interrupt_kind"] = str(
                interrupt_snapshot.get("kind", "") or ""
            ).strip()
            telemetry["interrupt_metadata"] = dict(
                interrupt_snapshot.get("metadata", {}) or {}
            )

        dialogue_snapshot = self._collect_dialogue_result_snapshot()
        if dialogue_snapshot:
            telemetry["dialogue_status"] = str(dialogue_snapshot.get("status", "") or "").strip()
            telemetry["dialogue_delivered"] = bool(dialogue_snapshot.get("delivered", False))
            telemetry["dialogue_source"] = str(dialogue_snapshot.get("source", "") or "").strip()
            telemetry["dialogue_reply_mode"] = str(
                dialogue_snapshot.get("reply_mode", "") or ""
            ).strip()

        if not self._turn_used_llm(telemetry, llm_snapshot):
            llm_snapshot = {}

        llm_part = ""
        if llm_snapshot:
            llm_part = (
                f" | llm_ok={llm_snapshot.get('ok', False)}"
                f" llm_ms={float(llm_snapshot.get('latency_ms', 0.0) or 0.0):.1f}"
                f" llm_first_chunk_ms={float(llm_snapshot.get('first_chunk_latency_ms', 0.0) or 0.0):.1f}"
                f" llm_source={llm_snapshot.get('source', '')}"
            )
            llm_error = str(llm_snapshot.get("error", "") or "").strip()
            if llm_error:
                llm_part += f" llm_error={llm_error}"

        response_part = ""
        if response_report is not None:
            response_part = (
                f" | first_audio_ms={self._metric_text(getattr(response_report, 'first_audio_latency_ms', 0.0))}"
                f" | first_chunk_ms={self._metric_text(getattr(response_report, 'first_chunk_latency_ms', 0.0))}"
                f" | first_sentence_ms={self._metric_text(getattr(response_report, 'first_sentence_latency_ms', 0.0))}"
                f" | response_ms={self._metric_text(getattr(response_report, 'total_elapsed_ms', 0.0))}"
                f" | chunks={int(getattr(response_report, 'chunks_spoken', 0) or 0)}"
                f" | live={bool(getattr(response_report, 'live_streaming', False))}"
            )

        benchmark_part = ""
        self._reset_llm_turn_snapshot()
        benchmark_service = getattr(self, "turn_benchmark_service", None)
        if benchmark_service is not None:
            finish_turn = getattr(benchmark_service, "finish_turn", None)
            if callable(finish_turn):
                try:
                    sample = finish_turn(
                        telemetry=telemetry,
                        llm_snapshot=llm_snapshot,
                        response_report=response_report,
                    )
                except Exception as error:
                    sample = {}
                    log_exception("Failed to finish turn benchmark trace", error)

                if sample:
                    benchmark_part = (
                        f" | wake_to_listen_ms={self._metric_text(sample.get('wake_to_listen_ms'))}"
                        f" | listen_to_speech_ms={self._metric_text(sample.get('listen_to_speech_ms'))}"
                        f" | speech_to_route_ms={self._metric_text(sample.get('speech_to_route_ms'))}"
                        f" | route_to_first_audio_ms={self._metric_text(sample.get('route_to_first_audio_ms'))}"
                    )

        topics = telemetry.get("topics") or []
        safe_topics = ",".join(str(item) for item in topics[:6]) if topics else "-"

        append_log(
            "TURN telemetry"
            f" | total_ms={total_ms:.1f}"
            f" | result={telemetry.get('result', '')}"
            f" | handled={bool(telemetry.get('handled', False))}"
            f" | input_source={telemetry.get('input_source', '')}"
            f" | language={telemetry.get('language', '')}"
            f" | stt_backend={telemetry.get('stt_backend', '')}"
            f" | stt_mode={telemetry.get('stt_mode', '')}"
            f" | stt_phase={telemetry.get('stt_phase', '')}"
            f" | stt_ms={float(telemetry.get('stt_latency_ms', 0.0) or 0.0):.1f}"
            f" | stt_audio_ms={float(telemetry.get('stt_audio_duration_ms', 0.0) or 0.0):.1f}"
            f" | stt_conf={float(telemetry.get('stt_confidence', 0.0) or 0.0):.2f}"
            f" | route_kind={telemetry.get('route_kind', '')}"
            f" | route_conf={float(telemetry.get('route_confidence', 0.0) or 0.0):.2f}"
            f" | intent={telemetry.get('primary_intent', '')}"
            f" | capture_phase={telemetry.get('capture_phase', '')}"
            f" | stt_backend={telemetry.get('stt_backend', '')}"
            f" | response_source={telemetry.get('response_source', '')}"
            f" | reply_source={telemetry.get('response_reply_source', '')}"
            f" | action={telemetry.get('action_name', '')}"
            f" | action_source={telemetry.get('action_source', '')}"
            f" | prepare_ms={float(telemetry.get('prepare_ms', 0.0) or 0.0):.1f}"
            f" | lang_ms={float(telemetry.get('language_commit_ms', 0.0) or 0.0):.1f}"
            f" | remember_ms={float(telemetry.get('remember_user_ms', 0.0) or 0.0):.1f}"
            f" | cancel_ms={float(telemetry.get('cancel_ms', 0.0) or 0.0):.1f}"
            f" | pending_ms={float(telemetry.get('pending_ms', 0.0) or 0.0):.1f}"
            f" | fast_lane_ms={float(telemetry.get('fast_lane_ms', 0.0) or 0.0):.1f}"
            f" | router_ms={float(telemetry.get('router_ms', 0.0) or 0.0):.1f}"
            f" | dispatch_ms={float(telemetry.get('dispatch_ms', 0.0) or 0.0):.1f}"
            f" | topics={safe_topics}"
            f"{llm_part}"
            f"{response_part}"
            f"{benchmark_part}"
        )
        self._refresh_developer_overlay(reason="turn_finished")
        self._last_response_stream_report = None
        self._last_response_delivery_snapshot = None
        self._last_fast_lane_route_snapshot = {}
        self._last_pending_flow_snapshot = {}

    def _consume_last_input_capture(self) -> dict[str, Any]:
        capture = dict(getattr(self, "_last_input_capture", {}) or {})
        self._last_input_capture = {}
        return capture


    def _collect_pending_flow_snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self, "_last_pending_flow_snapshot", None)
        return dict(snapshot or {})

    def _collect_interrupt_snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self, "_last_interrupt_snapshot", None)
        return dict(snapshot or {})

    def _collect_llm_snapshot(self) -> dict[str, Any]:
        dialogue = getattr(self, "dialogue", None)
        local_llm = getattr(dialogue, "local_llm", None)
        if local_llm is None:
            return {}

        snapshot_method = getattr(local_llm, "last_generation_snapshot", None)
        if callable(snapshot_method):
            try:
                snapshot = snapshot_method()
                if isinstance(snapshot, dict):
                    return dict(snapshot)
            except Exception as error:
                log_exception("Failed to collect LLM generation snapshot", error)

        backend_method = getattr(local_llm, "describe_backend", None)
        if callable(backend_method):
            try:
                snapshot = backend_method()
                if isinstance(snapshot, dict):
                    return {
                        "ok": bool(snapshot.get("last_generation_ok", False)),
                        "latency_ms": float(snapshot.get("last_generation_latency_ms", 0.0) or 0.0),
                        "first_chunk_latency_ms": float(
                            snapshot.get("last_first_chunk_latency_ms", 0.0) or 0.0
                        ),
                        "source": str(snapshot.get("last_generation_source", "") or ""),
                        "error": str(
                            snapshot.get("last_generation_error")
                            or snapshot.get("last_availability_error")
                            or ""
                        ).strip(),
                    }
            except Exception as error:
                log_exception("Failed to collect LLM backend description", error)

        return {}
    

    def _reset_llm_turn_snapshot(self) -> None:
        dialogue = getattr(self, "dialogue", None)
        local_llm = getattr(dialogue, "local_llm", None)
        if local_llm is None:
            return

        reset_method = getattr(local_llm, "reset_generation_snapshot", None)
        if callable(reset_method):
            try:
                reset_method()
            except Exception as error:
                log_exception("Failed to reset LLM generation snapshot", error)

    def _turn_used_llm(self, telemetry: dict[str, Any], llm_snapshot: dict[str, Any]) -> bool:
        if not llm_snapshot:
            return False

        llm_source = str(llm_snapshot.get("source", "") or "").strip().lower()
        if not llm_source:
            return False

        reply_source = str(telemetry.get("response_reply_source", "") or "").strip().lower()
        response_source = str(telemetry.get("response_source", "") or "").strip().lower()
        dialogue_source = str(telemetry.get("dialogue_source", "") or "").strip().lower()
        result = str(telemetry.get("result", "") or "").strip().lower()

        if reply_source == llm_source:
            return True

        if reply_source in {"local_llm", "hailo-ollama", "openai-server", "llama-server"}:
            return True

        if response_source == "dialogue_flow" and dialogue_source == "dialogue_flow":
            return True

        if result in {"conversation_route", "mixed_route", "unclear_route"} and bool(
            telemetry.get("dialogue_delivered", False)
        ):
            return True

        return False




    def _collect_response_stream_report(self) -> Any:
        return getattr(self, "_last_response_stream_report", None)

    def _collect_response_delivery_snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self, "_last_response_delivery_snapshot", None)
        return dict(snapshot or {})

    def _collect_skill_result_snapshot(self) -> dict[str, Any]:
        action_flow = getattr(self, "action_flow", None)
        snapshot = getattr(action_flow, "_last_skill_result", None)
        if snapshot is None:
            return {}
        metadata = dict(getattr(snapshot, "metadata", {}) or {})
        return {
            "action": str(getattr(snapshot, "action", "") or "").strip(),
            "handled": bool(getattr(snapshot, "handled", False)),
            "response_delivered": bool(getattr(snapshot, "response_delivered", False)),
            "status": str(getattr(snapshot, "status", "") or "").strip(),
            "source": str(metadata.get("source", "") or "").strip(),
            "latency_ms": self._safe_metric_float(metadata.get("latency_ms", 0.0)),
            "response_kind": str(metadata.get("response_kind", "") or "").strip(),
        }

    def _collect_dialogue_result_snapshot(self) -> dict[str, Any]:
        dialogue_flow = getattr(self, "dialogue_flow", None)
        snapshot = getattr(dialogue_flow, "_last_dialogue_result", None)
        if snapshot is None:
            return {}
        metadata = dict(getattr(snapshot, "metadata", {}) or {})
        return {
            "handled": bool(getattr(snapshot, "handled", False)),
            "delivered": bool(getattr(snapshot, "delivered", False)),
            "status": str(getattr(snapshot, "status", "") or "").strip(),
            "source": str(getattr(snapshot, "source", "") or "").strip(),
            "reply_mode": str(metadata.get("reply_mode", "") or "").strip(),
        }
    
    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return (time.perf_counter() - float(started_at)) * 1000.0

    @staticmethod
    def _safe_metric_float(value: Any) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _metric_text(value: Any) -> str:
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return "-"    

    @staticmethod
    def _route_kind_action():
        from modules.runtime.contracts import RouteKind

        return RouteKind.ACTION

    @staticmethod
    def _route_kind_mixed():
        from modules.runtime.contracts import RouteKind

        return RouteKind.MIXED

    @staticmethod
    def _route_kind_conversation():
        from modules.runtime.contracts import RouteKind

        return RouteKind.CONVERSATION