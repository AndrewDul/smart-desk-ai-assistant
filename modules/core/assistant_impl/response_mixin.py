from __future__ import annotations

import time
from typing import Any
from modules.presentation.response_streamer import StreamExecutionReport
from modules.core.session.visual_shell_state_feedback import notify_visual_shell_voice_event
from modules.presentation.visual_shell.contracts import VisualEventName
from modules.core.session.voice_session import (
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
)
from modules.runtime.contracts import (
    ChunkKind,
    ResponsePlan,
    RouteKind,
    create_turn_id,
)
from modules.shared.logging.logger import append_log, log_exception


class CoreAssistantResponseMixin:
    def _should_prefetch_text_response(
        self,
        *,
        text: str,
    ) -> bool:
        streaming_cfg = getattr(self, "settings", {}).get("streaming", {})
        configured = streaming_cfg.get("prefetch_text_responses")
        if configured is None:
            enabled = True
        else:
            enabled = bool(configured)

        if not enabled:
            return False

        cleaned_text = str(text or "").strip()
        if not cleaned_text:
            return False

        max_chars = int(streaming_cfg.get("prefetch_text_response_max_chars", 220) or 220)
        if len(cleaned_text) > max_chars:
            return False

        return True

    def _prefetch_text_response(
        self,
        *,
        text: str,
        language: str,
        source: str,
    ) -> None:
        if not self._should_prefetch_text_response(text=text):
            return

        prepare_method = getattr(getattr(self, "voice_out", None), "prepare_speech", None)
        if not callable(prepare_method):
            return

        cleaned_text = str(text or "").strip()
        try:
            prepare_method(cleaned_text, language)
            append_log(
                "Text response TTS prefetch queued: "
                f"source={source}, lang={language}, chars={len(cleaned_text)}"
            )
        except Exception as error:
            log_exception("Text response TTS prefetch failed", error)

    def deliver_response_plan(
        self,
        plan: ResponsePlan,
        *,
        source: str,
        remember: bool = True,
        extra_metadata: dict[str, Any] | None = None,
    ) -> bool:
        has_live_stream = self._plan_has_live_stream(plan)
        if not plan.chunks and not plan.tool_results and not has_live_stream:
            append_log("Response delivery skipped: empty plan.")
            return True

        started_at = time.perf_counter()
        route_kind_value = getattr(plan.route_kind, "value", str(plan.route_kind))
        self._last_response_stream_report = None
        self._last_response_delivery_snapshot = None
        self.voice_session.transition_to_speaking(
            detail=f"response:{route_kind_value}",
        )
        notify_visual_shell_voice_event(
            self,
            VisualEventName.SPEAKING_STARTED,
            source="response_delivery",
            detail=f"response:{route_kind_value}",
            payload={
                "route_kind": route_kind_value,
                "response_source": source,
            },
        )

        stream_report = None
        delivered = False
        remembered_text = ""
        display_title = ""
        display_lines: list[str] = []

        try:
            execute_method = getattr(self.response_streamer, "execute", None)
            if callable(execute_method):
                try:
                    stream_report = execute_method(plan)
                    delivered = self._stream_report_delivered(stream_report)
                except Exception as error:
                    log_exception("Response streamer execute failed", error)

            if not delivered:
                deliver_method = getattr(self.response_streamer, "deliver", None)
                if callable(deliver_method):
                    try:
                        delivered = bool(deliver_method(plan))
                    except Exception as error:
                        log_exception("Response streamer deliver failed", error)

            if not delivered:
                stream_method = getattr(self.response_streamer, "stream", None)
                if callable(stream_method):
                    try:
                        delivered = bool(stream_method(plan))
                    except Exception as error:
                        log_exception("Response streamer stream failed", error)

            if not delivered:
                stream_method = getattr(self.response_streamer, "stream", None)
                if callable(stream_method):
                    try:
                        stream_method(plan)
                        delivered = True
                    except Exception as error:
                        log_exception("Response streamer stream failed", error)

            remembered_text = self._extract_streamed_response_text(stream_report, plan)
            display_title, display_lines = self._extract_streamed_display(stream_report)

            if not delivered:
                fallback_text = str(plan.full_text() or "").strip()
                if fallback_text:
                    fallback_started = time.perf_counter()
                    spoken_ok = False

                    try:
                        spoken_ok = bool(
                            self.voice_out.speak(
                                fallback_text,
                                language=plan.language,
                            )
                        )
                    except Exception as error:
                        log_exception("Fallback voice output failed", error)

                    try:
                        self.display.show_block(
                            self.ASSISTANT_NAME,
                            self._display_lines(fallback_text),
                            duration=self.default_overlay_seconds,
                        )
                    except Exception as error:
                        log_exception("Fallback display output failed", error)

                    delivered = bool(spoken_ok or fallback_text)
                    remembered_text = fallback_text

                    append_log(
                        "Response fallback delivery finished: "
                        f"route_kind={route_kind_value}, "
                        f"chars={len(fallback_text)}, "
                        f"elapsed_ms={(time.perf_counter() - fallback_started) * 1000.0:.1f}"
                    )
                else:
                    recovery_started = time.perf_counter()
                    recovery_text = self._localized(
                        plan.language,
                        "Przepraszam, nie udało mi się teraz wygenerować odpowiedzi. Spróbuj ponownie za chwilę.",
                        "Sorry, I could not generate an answer right now. Please try again in a moment.",
                    )
                    spoken_ok = False

                    try:
                        spoken_ok = bool(
                            self.voice_out.speak(
                                recovery_text,
                                language=plan.language,
                            )
                        )
                    except Exception as error:
                        log_exception("Recovery voice output failed", error)

                    try:
                        self.display.show_block(
                            self.ASSISTANT_NAME,
                            self._display_lines(recovery_text),
                            duration=self.default_overlay_seconds,
                        )
                    except Exception as error:
                        log_exception("Recovery display output failed", error)

                    delivered = bool(spoken_ok or recovery_text)
                    remembered_text = recovery_text

                    append_log(
                        "Response recovery delivery finished: "
                        f"route_kind={route_kind_value}, "
                        f"chars={len(recovery_text)}, "
                        f"elapsed_ms={(time.perf_counter() - recovery_started) * 1000.0:.1f}"
                    )

            if remember and remembered_text:
                metadata = {
                    "source": source,
                    "route_kind": route_kind_value,
                    "tool_count": len(plan.tool_results),
                    "stream_mode": getattr(plan.stream_mode, "value", str(plan.stream_mode)),
                }
                if extra_metadata:
                    metadata.update(extra_metadata)

                try:
                    self._remember_assistant_turn(
                        remembered_text,
                        language=plan.language,
                        metadata=metadata,
                    )
                except Exception as error:
                    log_exception("Failed to remember assistant turn after response", error)
            
            finished_at = time.perf_counter()
            self._last_response_stream_report = self._finalize_response_stream_report(
                stream_report=stream_report,
                started_at=started_at,
                finished_at=finished_at,
                full_text=remembered_text,
                display_title=display_title,
                display_lines=display_lines,
                default_chunk_kinds=["content"] if remembered_text else [],
            )

            plan_metadata = dict(getattr(plan, "metadata", {}) or {})
            safe_extra_metadata = dict(extra_metadata or {})
            self._last_response_delivery_snapshot = {
                "source": source,
                "route_kind": route_kind_value,
                "stream_mode": getattr(plan.stream_mode, "value", str(plan.stream_mode)),
                "reply_source": str(plan_metadata.get("reply_source", "") or ""),
                "display_title": display_title or str(plan_metadata.get("display_title", "") or ""),
                "display_lines": list(display_lines or plan_metadata.get("display_lines", []) or []),
                "remembered": bool(remember and remembered_text),
                "delivered": bool(delivered),
                "fallback_used": bool(not self._stream_report_delivered(stream_report)),
                "extra_metadata": safe_extra_metadata,
                "plan_metadata": plan_metadata,
                "full_text_chars": len(remembered_text),
            }

            append_log(
                "Response delivery finished: "
                f"route_kind={route_kind_value}, "
                f"source={source}, "
                f"delivered={delivered}, "
                f"remembered={bool(remember and remembered_text)}, "
                f"chars={len(remembered_text)}, "
                f"display_title={display_title or '-'}, "
                f"display_lines={len(display_lines)}, "
                f"elapsed_ms={(time.perf_counter() - started_at) * 1000.0:.1f}"
            )

            return bool(delivered)
        finally:
            if self.shutdown_requested:
                self.voice_session.transition_to_shutdown(detail="shutdown_requested")
            else:
                self.voice_session.mark_response_finished(detail="response_complete")
                notify_visual_shell_voice_event(
                    self,
                    VisualEventName.SPEAKING_FINISHED,
                    source="response_delivery",
                    detail="response_complete",
                    payload={
                        "route_kind": route_kind_value,
                        "response_source": source,
                    },
                )
           

    def deliver_text_response(
        self,
        text: str,
        *,
        language: str,
        route_kind: RouteKind,
        source: str,
        remember: bool = True,
        chunk_kind: ChunkKind = ChunkKind.CONTENT,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        cleaned_text = str(text or "").strip()
        self._prefetch_text_response(
            text=cleaned_text,
            language=language,
            source=source,
        )

        plan = ResponsePlan(
            turn_id=create_turn_id(),
            language=language,
            route_kind=route_kind,
            stream_mode=self.stream_mode,
        )
        plan.add_text(cleaned_text, kind=chunk_kind, mode=self.stream_mode)
        return self.deliver_response_plan(
            plan,
            source=source,
            remember=remember,
            extra_metadata=metadata,
        )
    @staticmethod
    def _plan_has_live_stream(plan: ResponsePlan) -> bool:
        metadata = dict(getattr(plan, "metadata", {}) or {})
        return callable(metadata.get("live_chunk_factory"))

    @staticmethod
    def _stream_report_delivered(stream_report: Any) -> bool:
        """Return True only when the stream actually produced audible speech.

        A non-empty text payload is not enough to mark delivery as successful.
        Otherwise action handlers can produce a false positive where telemetry
        says the response was delivered but the user hears silence.
        """

        if stream_report is None:
            return False

        try:
            return int(getattr(stream_report, "chunks_spoken", 0) or 0) > 0
        except Exception:
            return False
    
    def _extract_streamed_response_text(
        self,
        stream_report: Any,
        plan: ResponsePlan,
    ) -> str:
        if stream_report is not None:
            try:
                text = str(getattr(stream_report, "full_text", "") or "").strip()
                if text:
                    return text
            except Exception:
                pass

        return plan.full_text()

    def _extract_streamed_display(self, stream_report: Any) -> tuple[str, list[str]]:
        if stream_report is None:
            return "", []

        try:
            title = str(getattr(stream_report, "display_title", "") or "").strip()
        except Exception:
            title = ""

        try:
            raw_lines = getattr(stream_report, "display_lines", []) or []
            lines = [str(line).strip() for line in raw_lines if str(line).strip()]
        except Exception:
            lines = []

        return title, lines
    
    def _finalize_response_stream_report(
        self,
        *,
        stream_report: Any,
        started_at: float,
        finished_at: float,
        full_text: str,
        display_title: str,
        display_lines: list[str],
        default_chunk_kinds: list[str],
    ) -> StreamExecutionReport:
        base_report = stream_report if stream_report is not None else None

        started_at_monotonic = self._report_float(
            base_report,
            "started_at_monotonic",
            fallback=started_at,
        )
        finished_at_monotonic = self._report_float(
            base_report,
            "finished_at_monotonic",
            fallback=finished_at,
        )

        first_audio_started_at_monotonic = self._report_float(
            base_report,
            "first_audio_started_at_monotonic",
        )
        first_audio_latency_ms = self._report_float(
            base_report,
            "first_audio_latency_ms",
        )
        first_chunk_started_at_monotonic = self._report_float(
            base_report,
            "first_chunk_started_at_monotonic",
        )
        first_chunk_latency_ms = self._report_float(
            base_report,
            "first_chunk_latency_ms",
        )
        first_sentence_started_at_monotonic = self._report_float(
            base_report,
            "first_sentence_started_at_monotonic",
        )
        first_sentence_latency_ms = self._report_float(
            base_report,
            "first_sentence_latency_ms",
        )

        if first_audio_started_at_monotonic <= 0.0 and started_at_monotonic > 0.0 and first_audio_latency_ms > 0.0:
            first_audio_started_at_monotonic = started_at_monotonic + (first_audio_latency_ms / 1000.0)

        if first_audio_latency_ms <= 0.0 and first_audio_started_at_monotonic > 0.0 and started_at_monotonic > 0.0:
            first_audio_latency_ms = max(
                0.0,
                (first_audio_started_at_monotonic - started_at_monotonic) * 1000.0,
            )

        if first_chunk_started_at_monotonic <= 0.0 and started_at_monotonic > 0.0 and first_chunk_latency_ms > 0.0:
            first_chunk_started_at_monotonic = started_at_monotonic + (first_chunk_latency_ms / 1000.0)

        if first_chunk_latency_ms <= 0.0 and first_chunk_started_at_monotonic > 0.0 and started_at_monotonic > 0.0:
            first_chunk_latency_ms = max(
                0.0,
                (first_chunk_started_at_monotonic - started_at_monotonic) * 1000.0,
            )

        if first_sentence_started_at_monotonic <= 0.0 and started_at_monotonic > 0.0 and first_sentence_latency_ms > 0.0:
            first_sentence_started_at_monotonic = started_at_monotonic + (first_sentence_latency_ms / 1000.0)

        if first_sentence_latency_ms <= 0.0 and first_sentence_started_at_monotonic > 0.0 and started_at_monotonic > 0.0:
            first_sentence_latency_ms = max(
                0.0,
                (first_sentence_started_at_monotonic - started_at_monotonic) * 1000.0,
            )

        total_elapsed_ms = self._report_float(base_report, "total_elapsed_ms")
        if total_elapsed_ms <= 0.0 and finished_at_monotonic > 0.0 and started_at_monotonic > 0.0:
            total_elapsed_ms = max(
                0.0,
                (finished_at_monotonic - started_at_monotonic) * 1000.0,
            )

        reported_full_text = str(getattr(base_report, "full_text", "") or "").strip()
        safe_full_text = reported_full_text or str(full_text or "").strip()

        reported_title = str(getattr(base_report, "display_title", "") or "").strip()
        safe_display_title = reported_title or str(display_title or "").strip()

        raw_display_lines = getattr(base_report, "display_lines", display_lines) or display_lines
        safe_display_lines = [str(line).strip() for line in raw_display_lines if str(line).strip()]

        raw_chunk_kinds = list(getattr(base_report, "chunk_kinds", []) or default_chunk_kinds or [])
        safe_chunk_kinds = [str(item).strip() for item in raw_chunk_kinds if str(item).strip()]

        chunks_spoken = int(getattr(base_report, "chunks_spoken", 0) or 0)
        if chunks_spoken < 0:
            chunks_spoken = 0

        return StreamExecutionReport(
            chunks_spoken=chunks_spoken,
            full_text=safe_full_text,
            display_title=safe_display_title,
            display_lines=safe_display_lines,
            first_audio_latency_ms=first_audio_latency_ms,
            first_chunk_latency_ms=first_chunk_latency_ms,
            first_sentence_latency_ms=first_sentence_latency_ms,
            total_elapsed_ms=total_elapsed_ms,
            started_at_monotonic=started_at_monotonic,
            first_audio_started_at_monotonic=first_audio_started_at_monotonic,
            first_chunk_started_at_monotonic=first_chunk_started_at_monotonic,
            first_sentence_started_at_monotonic=first_sentence_started_at_monotonic,
            finished_at_monotonic=finished_at_monotonic,
            chunk_kinds=safe_chunk_kinds,
            live_streaming=bool(getattr(base_report, "live_streaming", False)),
        )
    @staticmethod
    def _report_float(
        value: Any,
        name: str,
        *,
        fallback: float = 0.0,
    ) -> float:
        if value is None:
            return float(fallback)

        try:
            raw = getattr(value, name, fallback)
            return float(raw or 0.0)
        except (TypeError, ValueError):
            return float(fallback)


    def _deliver_async_notification(
        self,
        *,
        lang: str,
        spoken_text: str,
        display_title: str,
        display_lines: list[str],
        source: str,
        route_kind: str,
        action: str | None = None,
        display_duration: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        deliver_method = getattr(self.notification_flow, "deliver_async_notification", None)
        if callable(deliver_method):
            deliver_method(
                lang=lang,
                spoken_text=spoken_text,
                display_title=display_title,
                display_lines=display_lines,
                source=source,
                route_kind=route_kind,
                action=action,
                display_duration=display_duration,
                extra_metadata=extra_metadata,
            )
            return

        self.deliver_text_response(
            spoken_text,
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source=source,
            remember=True,
            metadata=extra_metadata,
        )

    def _on_timer_started(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        minutes = self._timer_minutes_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = timer_type
        self.state["focus_mode"] = timer_type == "focus"
        self.state["break_mode"] = timer_type == "break"
        self._save_state()

        if timer_type == "focus":
            self._enter_ai_broker_focus_sentinel_mode(
                reason="focus_timer_started",
            )
            start_focus_vision = getattr(self, "_start_focus_vision_sentinel", None)
            if callable(start_focus_vision):
                start_focus_vision(
                    language=lang,
                    reason="focus_timer_started",
                )

        if timer_type == "focus":
            spoken = self._localized(
                lang,
                f"Rozpoczynam tryb skupienia na {self._minutes_text(minutes, 'pl')}.",
                f"Starting focus mode for {self._minutes_text(minutes, 'en')}.",
            )
            title = "FOCUS"
        elif timer_type == "break":
            spoken = self._localized(
                lang,
                f"Rozpoczynam przerwę na {self._minutes_text(minutes, 'pl')}.",
                f"Starting break mode for {self._minutes_text(minutes, 'en')}.",
            )
            title = "BREAK"
        else:
            spoken = self._localized(
                lang,
                f"Uruchamiam timer na {self._minutes_text(minutes, 'pl')}.",
                f"Starting a timer for {self._minutes_text(minutes, 'en')}.",
            )
            title = "TIMER"

        self._send_timer_countdown_to_visual_shell(
            mode=timer_type,
            remaining_seconds=int(payload.get("remaining_seconds", 0) or 0),
            total_seconds=int(payload.get("total_seconds", 0) or 0),
            source="timer_started",
        )

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title=title,
            display_lines=self._display_lines(spoken),
            source="timer_started",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={
                "minutes": minutes,
                "timer_type": timer_type,
                "total_seconds": int(payload.get("total_seconds", 0) or 0),
            },
        )

    def _on_timer_finished(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        minutes = self._timer_minutes_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        if timer_type == "focus":
            stop_focus_vision = getattr(self, "_stop_focus_vision_sentinel", None)
            if callable(stop_focus_vision):
                stop_focus_vision(reason="focus_timer_finished")
            self._enter_ai_broker_idle_baseline(
                reason="focus_timer_finished",
            )

        self._clear_timer_countdown_from_visual_shell(source="timer_finished")

        if timer_type == "focus":
            self.pending_follow_up = {
                "type": "focus_extend_offer",
                "language": lang,
                "default_minutes": float(getattr(self, "default_focus_minutes", 25.0)),
                "source": "timer_focus_finished",
            }
            spoken = self._localized(
                lang,
                "Czas skupienia dobiega końca. Możesz odpocząć albo przedłużyć. Chcesz przedłużyć?",
                "Focus mode is ending. You can take a break or extend it. Do you want to extend it?",
            )
            title = "FOCUS DONE"
        elif timer_type == "break":
            self.pending_follow_up = {
                "type": "break_extend_offer",
                "language": lang,
                "default_minutes": float(getattr(self, "default_break_minutes", 5.0)),
                "source": "timer_break_finished",
            }
            spoken = self._localized(
                lang,
                "Odpoczynek dobiega końca. Możesz wrócić do skupienia albo go przedłużyć. Chcesz przedłużyć odpoczynek?",
                "Break mode is ending. You can return to focus mode or extend it. Do you want to extend it?",
            )
            title = "BREAK DONE"
        else:
            spoken = self._localized(
                lang,
                f"Timer zakończył się po {self._minutes_text(minutes, 'pl')}.",
                f"Timer finished after {self._minutes_text(minutes, 'en')}.",
            )
            title = "TIMER DONE"

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title=title,
            display_lines=self._display_lines(spoken),
            source="timer_finished",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={
                "minutes": minutes,
                "timer_type": timer_type,
                "follow_up_type": (self.pending_follow_up or {}).get("type"),
                "total_seconds": int(payload.get("total_seconds", 0) or 0),
            },
        )

    def _on_timer_stopped(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        if timer_type == "focus":
            stop_focus_vision = getattr(self, "_stop_focus_vision_sentinel", None)
            if callable(stop_focus_vision):
                stop_focus_vision(reason="focus_timer_stopped")
            self._enter_ai_broker_idle_baseline(
                reason="focus_timer_stopped",
            )

        spoken = self._localized(
            lang,
            "Zatrzymałem aktywny timer.",
            "I stopped the active timer.",
        )

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title="TIMER STOPPED",
            display_lines=self._display_lines(spoken),
            source="timer_stopped",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={"timer_type": timer_type},
        )
    def _on_timer_tick(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        self._send_timer_countdown_to_visual_shell(
            mode=timer_type,
            remaining_seconds=int(payload.get("remaining_seconds", 0) or 0),
            total_seconds=int(payload.get("total_seconds", 0) or 0),
            source="timer_tick",
        )

    def _send_timer_countdown_to_visual_shell(
        self,
        *,
        mode: str,
        remaining_seconds: int,
        total_seconds: int,
        source: str,
    ) -> None:
        if mode not in {"focus", "break"}:
            return

        controller = self._visual_shell_controller_for_timer()
        if controller is None:
            append_log("Timer countdown Visual Shell update skipped: controller unavailable.")
            return

        label = "FOCUS" if mode == "focus" else "BREAK"
        color_state = self._timer_countdown_color_state(
            remaining_seconds=remaining_seconds,
            total_seconds=total_seconds,
        )
        try:
            show = getattr(controller, "show_timer_countdown", None)
            if callable(show):
                show(
                    mode=mode,
                    remaining_seconds=max(0, int(remaining_seconds)),
                    total_seconds=max(0, int(total_seconds)),
                    label=label,
                    color_state=color_state,
                    source=source,
                )
                append_log(
                    "Timer countdown Visual Shell update sent: "
                    f"mode={mode}, remaining_seconds={remaining_seconds}, "
                    f"total_seconds={total_seconds}, color_state={color_state}, source={source}"
                )
        except Exception as error:
            log_exception("Timer countdown Visual Shell update failed", error)

    def _clear_timer_countdown_from_visual_shell(self, *, source: str) -> None:
        controller = self._visual_shell_controller_for_timer()
        if controller is None:
            return
        try:
            clear = getattr(controller, "clear_timer_countdown", None)
            if callable(clear):
                clear(source=source)
                append_log(f"Timer countdown Visual Shell clear sent: source={source}")
        except Exception as error:
            log_exception("Timer countdown Visual Shell clear failed", error)

    def _visual_shell_controller_for_timer(self) -> Any | None:
        fast_lane = getattr(self, "fast_command_lane", None)
        visual_lane = getattr(fast_lane, "visual_shell_lane", None)
        if visual_lane is None:
            visual_lane = getattr(self, "visual_shell_lane", None)
        if visual_lane is None:
            return None
        controller = getattr(visual_lane, "controller", None)
        if controller is not None:
            return controller
        controller_factory = getattr(visual_lane, "_controller", None)
        if callable(controller_factory):
            try:
                return controller_factory()
            except Exception as error:
                log_exception("Timer countdown Visual Shell controller lookup failed", error)
        return None

    @staticmethod
    def _timer_countdown_color_state(*, remaining_seconds: int, total_seconds: int) -> str:
        remaining = max(0, int(remaining_seconds))
        total = max(0, int(total_seconds))
        if total <= 0 or remaining <= 0:
            return "red"
        ratio = remaining / float(total)
        if ratio <= 0.05:
            return "red"
        if remaining <= 20:
            return "orange"
        if ratio < 0.60:
            return "yellow"
        return "white"
