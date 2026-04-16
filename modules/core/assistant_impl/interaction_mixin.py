from __future__ import annotations

import time
from typing import Any

from sympy import capture

from modules.core.session.voice_session import VOICE_STATE_ROUTING
from modules.shared.logging.logger import append_log, log_exception


class CoreAssistantInteractionMixin:
    def handle_command(self, text: str) -> bool:
        self.interrupt_controller.clear()

        cleaned = str(text or "").strip()
        if not cleaned:
            return True

        telemetry = self._start_turn_telemetry(cleaned)

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

            fast_lane_started = time.perf_counter()
            fast_lane_result = self._handle_fast_lane(prepared)
            telemetry["fast_lane_ms"] = self._elapsed_ms(fast_lane_started)

            if fast_lane_result is not None:
                telemetry["result"] = "fast_lane"
                return bool(fast_lane_result)

            self.voice_session.transition_to_routing(detail="route_command")

            route_context = {
                "input_source": telemetry.get("input_source", "voice"),
                "capture_phase": telemetry.get("capture_phase", ""),
                "capture_mode": telemetry.get("stt_mode", ""),
                "capture_backend": telemetry.get("stt_backend", ""),
            }

            routing_started = time.perf_counter()
            self._thinking_ack_start(language=command_lang, detail="route_command")
            try:
                routed = self._route_command(
                    routing_text,
                    preferred_language=command_lang,
                    context=route_context,
                )
            finally:
                self._thinking_ack_stop()
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
            return bool(result)

        finally:
            self._finish_turn_telemetry(telemetry)

    def request_interrupt(
        self,
        *,
        reason: str = "manual_interrupt",
        source: str = "assistant",
        metadata: dict | None = None,
    ) -> None:
        self.interrupt_controller.request(
            reason=reason,
            source=source,
            metadata=metadata,
        )
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

    def _consume_last_input_capture(self) -> dict[str, Any]:
        capture = dict(getattr(self, "_last_input_capture", {}) or {})
        self._last_input_capture = {}
        return capture

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
    def _collect_response_stream_report(self) -> Any:
        return getattr(self, "_last_response_stream_report", None)

    def _collect_response_delivery_snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self, "_last_response_delivery_snapshot", None)
        return dict(snapshot or {})
    
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