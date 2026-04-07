from __future__ import annotations

import re
import threading
import time
from typing import Any

from modules.core.dispatch import dispatch_intent
from modules.core.followups import (
    ask_for_confirmation,
    extract_name,
    handle_pending_confirmation,
    handle_pending_follow_up,
)
from modules.core.handlers_break import (
    on_break_finished,
    on_break_started,
    on_break_stopped,
    start_break,
)
from modules.core.handlers_focus import (
    on_focus_finished,
    on_focus_started,
    on_focus_stopped,
    start_focus,
)
from modules.core.handlers_timer import (
    on_timer_finished,
    on_timer_started,
    on_timer_stopped,
    start_timer,
)
from modules.core.voice_session import VoiceSessionController
from modules.core.language import (
    context_language,
    detect_language,
    extract_minutes_from_text,
    format_duration_text,
    is_no,
    is_yes,
    localized,
    normalize_text,
    speak_localized,
)
from modules.core.responses import (
    action_label,
    format_temporal_text,
    offer_oled_display,
    show_capabilities,
    show_localized_block,
)
from modules.nlu.router import CompanionRoute
from modules.nlu.semantic_intent_matcher import SemanticIntentMatcher
from modules.nlu.utterance_normalizer import UtteranceNormalizer
from modules.parsing.intent_parser import IntentResult
from modules.runtime_builder import RuntimeBuilder
from modules.services.audio_coordinator import AssistantAudioCoordinator
from modules.services.fast_command_lane import FastCommandLane
from modules.services.conversation_memory import ConversationMemory
from modules.services.interrupt_controller import InteractionInterruptController
from modules.services.response_streamer import StreamingResponseService
from modules.services.thinking_ack import ThinkingAckService
from modules.system.utils import (
    SESSION_STATE_PATH,
    USER_PROFILE_PATH,
    append_log,
    ensure_project_files,
    load_json,
    load_settings,
    save_json,
)


class CoreAssistant:
    ASSISTANT_NAME = "NeXa"

    def __init__(self) -> None:
        ensure_project_files()

        self.settings = load_settings()

        voice_input_cfg = self.settings.get("voice_input", {})
        display_cfg = self.settings.get("display", {})
        streaming_cfg = self.settings.get("streaming", {})

        self.voice_listen_timeout = float(voice_input_cfg.get("timeout_seconds", 8))
        self.voice_debug = bool(voice_input_cfg.get("debug", False))
        self.default_overlay_seconds = float(display_cfg.get("default_overlay_seconds", 10))
        self.boot_overlay_seconds = float(display_cfg.get("boot_overlay_seconds", 2.8))

        self.pending_confirmation: dict[str, Any] | None = None
        self.pending_follow_up: dict[str, Any] | None = None
        self.last_language = "en"
        self.shutdown_requested = False
        self.interrupt_controller = InteractionInterruptController()

        audio_cfg = self.settings.get("audio_coordination", {})
        self.audio_coordinator = AssistantAudioCoordinator(
            post_speech_hold_seconds=float(audio_cfg.get("self_hearing_hold_seconds", 0.72)),
            input_poll_interval_seconds=float(audio_cfg.get("listen_resume_poll_seconds", 0.05)),
        )

        self.voice_session = VoiceSessionController(
            wake_phrases=("nexa",),
            wake_acknowledgements=(
                "Yes?",
                "I'm listening.",
                "I'm here.",
            ),
            active_listen_window_seconds=float(voice_input_cfg.get("active_listen_window_seconds", 8.0)),
            thinking_ack_seconds=float(voice_input_cfg.get("thinking_ack_seconds", 1.5)),
        )

        self._last_raw_command_text = ""
        self._last_normalized_command_text = ""

        self.runtime = RuntimeBuilder(self.settings).build(
            on_timer_started=self._on_timer_started,
            on_timer_finished=self._on_timer_finished,
            on_timer_stopped=self._on_timer_stopped,
        )

        self.parser = self.runtime.parser
        self.router = self.runtime.router
        self.dialogue = self.runtime.dialogue
        self.voice_in = self.runtime.voice_input
        self.voice_out = self.runtime.voice_output
        self.display = self.runtime.display
        self._attach_audio_coordinator(self.voice_in)
        self._attach_audio_coordinator(self.voice_out)
        self.memory = self.runtime.memory
        self.reminders = self.runtime.reminders
        self.timer = self.runtime.timer
        self.backend_statuses = dict(self.runtime.backend_statuses)

        self.fast_command_lane = FastCommandLane(
            enabled=bool(self.settings.get("fast_command_lane", {}).get("enabled", True)),
        )

        self.response_streamer = StreamingResponseService(
            voice_output=self.voice_out,
            display=self.display,
            default_display_seconds=self.default_overlay_seconds,
            inter_chunk_pause_seconds=float(streaming_cfg.get("inter_chunk_pause_seconds", 0.05)),
            max_display_lines=int(streaming_cfg.get("max_display_lines", 2)),
            max_display_chars_per_line=int(streaming_cfg.get("max_display_chars_per_line", 20)),
            interrupt_requested=self._interrupt_requested,
        )

        self.thinking_ack_service = ThinkingAckService(
            voice_output=self.voice_out,
            voice_session=self.voice_session,
            delay_seconds=self.voice_session.thinking_ack_seconds,
        )

        self.utterance_normalizer = UtteranceNormalizer()
        self.semantic_matcher = SemanticIntentMatcher()
        self.conversation_memory = ConversationMemory(
            max_turns=int(self.settings.get("conversation", {}).get("max_turns", 8)),
            max_total_chars=int(self.settings.get("conversation", {}).get("max_total_chars", 1800)),
        )

        self.user_profile = load_json(
            USER_PROFILE_PATH,
            {
                "name": "Andrzej",
                "conversation_partner_name": "",
                "project": "Smart Desk AI Assistant",
            },
        )
        self.state = load_json(
            SESSION_STATE_PATH,
            {
                "assistant_running": False,
                "focus_mode": False,
                "break_mode": False,
                "current_timer": None,
            },
        )

        self._boot_report_ok = all(status.ok for status in self.backend_statuses.values())

        self._stop_background = threading.Event()
        self._reminder_thread = threading.Thread(target=self._reminder_loop, daemon=True)

    def boot(self) -> None:
        self.state["assistant_running"] = True
        self._save_state()

        if not self._reminder_thread.is_alive():
            self._reminder_thread.start()

        self.last_language = "en"
        self.pending_confirmation = None
        self.pending_follow_up = None
        self.shutdown_requested = False
        self._last_raw_command_text = ""
        self._last_normalized_command_text = ""
        self.conversation_memory.clear()
        self.voice_session.close_active_window()

        self.display.show_block(
            self.ASSISTANT_NAME,
            [
                "starting up...",
                "voice assistant ready",
            ],
            duration=self.boot_overlay_seconds,
        )

        append_log("Assistant boot sequence started.")

        time.sleep(max(self.boot_overlay_seconds, 0.8))
        self.display.clear_overlay()
        time.sleep(0.15)

        startup_text = self._startup_greeting(report_ok=self._boot_report_ok)
        self.voice_out.speak(startup_text, language="en")

        self._remember_assistant_turn(
            startup_text,
            language="en",
            metadata={
                "source": "system",
                "route_kind": "system_boot",
            },
        )

        append_log("Assistant booted.")

    def shutdown(self) -> None:
        self._stop_background.set()

        if self.timer.status()["running"]:
            self.timer.stop()

        self.state["assistant_running"] = False
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        self.display.show_block(
            "SHUTDOWN",
            [
                "assistant stopped",
                "see you later",
            ],
            duration=2.0,
        )

        shutdown_text = self._localized(
            self.last_language,
            f"Wyłączam {self.ASSISTANT_NAME}.",
            f"Shutting down {self.ASSISTANT_NAME}.",
        )

        self._remember_assistant_turn(
            shutdown_text,
            language=self.last_language,
            metadata={
                "source": "system",
                "route_kind": "system_shutdown",
            },
        )

        self._speak_localized(
            self.last_language,
            f"Wyłączam {self.ASSISTANT_NAME}.",
            f"Shutting down {self.ASSISTANT_NAME}.",
        )

        append_log("Assistant shut down.")
        time.sleep(2.0)
        self.voice_session.set_state("shutdown", detail="assistant_shutdown")
        self.display.close()

    def _save_state(self) -> None:
        save_json(SESSION_STATE_PATH, self.state)

    def _save_user_profile(self) -> None:
        save_json(USER_PROFILE_PATH, self.user_profile)

    def _normalize_text(self, text: str) -> str:
        return normalize_text(self, text)

    def _detect_language(self, text: str) -> str:
        return detect_language(self, text)

    def _localized(self, lang: str, pl_text: str, en_text: str) -> str:
        return localized(lang, pl_text, en_text)

    def _speak_localized(self, lang: str, pl_text: str, en_text: str) -> None:
        speak_localized(self, lang, pl_text, en_text)

    def _context_language(self, text: str, detected_lang: str) -> str:
        return context_language(self, text, detected_lang)

    def _prefer_command_language(
        self,
        routing_text: str,
        detected_lang: str,
        normalizer_language_hint: str,
    ) -> str:
        preferred_detected_lang = normalizer_language_hint or detected_lang
        command_lang = self._context_language(routing_text, preferred_detected_lang)
        return self._normalize_lang(command_lang)

    @staticmethod
    def _contains_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        return any(phrase in normalized for phrase in phrases)

    def _looks_like_shutdown_command(self, normalized_text: str) -> bool:
        shutdown_markers = (
            "wylacz",
            "zamknij",
            "shutdown",
            "shut down",
            "turn off",
            "close assistant",
            "assistant off",
        )
        target_markers = (
            "asystent",
            "asystenta",
            "assistant",
            "system",
            "raspberry pi",
            "komputer",
            "nexa",
        )
        return self._contains_any_phrase(normalized_text, shutdown_markers) and self._contains_any_phrase(
            normalized_text,
            target_markers,
        )

    def _looks_like_humour_request(self, normalized_text: str) -> bool:
        humour_markers = (
            "smiesz",
            "zart",
            "dowcip",
            "funny",
            "joke",
            "humor",
            "humour",
        )
        return self._contains_any_phrase(normalized_text, humour_markers)

    def _looks_like_riddle_request(self, normalized_text: str) -> bool:
        riddle_markers = (
            "zagad",
            "riddle",
            "łamiglow",
            "lamiglow",
        )
        return self._contains_any_phrase(normalized_text, riddle_markers)

    def _format_duration_text(self, total_seconds: int, lang: str) -> str:
        return format_duration_text(total_seconds, lang)

    def _extract_minutes_from_text(self, text: str) -> float | None:
        return extract_minutes_from_text(self, text)

    def _is_yes(self, text: str) -> bool:
        return is_yes(self, text)

    def _is_no(self, text: str) -> bool:
        return is_no(self, text)

    def _action_label(self, action: str, lang: str) -> str:
        return action_label(action, lang)

    def _show_capabilities(self, lang: str) -> None:
        show_capabilities(self, lang)

    def _show_localized_block(
        self,
        lang: str,
        title_pl: str,
        title_en: str,
        lines_pl: list[str],
        lines_en: list[str],
        duration: float | None = None,
    ) -> None:
        show_localized_block(self, lang, title_pl, title_en, lines_pl, lines_en, duration)

    def _offer_oled_display(self, lang: str, title: str, lines: list[str], speak_prompt: bool = True) -> None:
        offer_oled_display(self, lang, title, lines, speak_prompt)

    def _format_temporal_text(self, kind: str, lang: str) -> tuple[str, str, list[str]]:
        return format_temporal_text(kind, lang)

    def _extract_name(self, text: str) -> str | None:
        return extract_name(text)

    def _ask_for_confirmation(self, suggestions: list[dict[str, Any]], lang: str) -> bool:
        return ask_for_confirmation(self, suggestions, lang)

    def _handle_pending_confirmation(self, text: str, current_lang: str) -> bool:
        return handle_pending_confirmation(self, text, current_lang)

    def _handle_pending_follow_up(self, text: str, lang: str) -> bool | None:
        return handle_pending_follow_up(self, text, lang)

    def _delete_all_reminders(self) -> int:
        reminders = self.reminders.list_all()
        count = 0
        for reminder in reminders:
            reminder_id = reminder.get("id")
            if reminder_id and self.reminders.delete(reminder_id):
                count += 1
        return count

    def _start_timer_mode(self, minutes: float, mode: str, lang: str) -> bool:
        if mode == "focus":
            return start_focus(self, minutes, lang)
        if mode == "break":
            return start_break(self, minutes, lang)
        return start_timer(self, minutes, lang)

    def _on_timer_started(self, mode: str, minutes: float) -> None:
        if mode == "focus":
            on_focus_started(self, minutes)
            return
        if mode == "break":
            on_break_started(self, minutes)
            return
        on_timer_started(self, minutes)

    def _on_timer_finished(self, mode: str) -> None:
        if mode == "focus":
            on_focus_finished(self)
            return
        if mode == "break":
            on_break_finished(self)
            return
        on_timer_finished(self)

    def _on_timer_stopped(self, mode: str) -> None:
        if mode == "focus":
            on_focus_stopped(self)
            return
        if mode == "break":
            on_break_stopped(self)
            return
        on_timer_stopped(self)

    def _startup_greeting(self, report_ok: bool) -> str:
        if report_ok:
            return f"Hello. I am {self.ASSISTANT_NAME}. You can ask me at any time how I can help."

        return (
            f"Hello. I am {self.ASSISTANT_NAME}. "
            "I started with some warnings, so a few things may work in limited mode. "
            "You can ask me at any time how I can help."
        )

    def _normalize_lang(self, lang: str | None) -> str:
        normalized = str(lang or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    def _commit_language(self, lang: str | None) -> None:
        normalized = self._normalize_lang(lang)
        self.last_language = normalized

    def _interrupt_requested(self) -> bool:
        return self.interrupt_controller.is_requested()

    def request_interrupt(
        self,
        *,
        reason: str,
        source: str,
        open_active_window: bool = True,
    ) -> None:
        self.interrupt_controller.request(
            reason=reason,
            source=source,
        )

        self.pending_confirmation = None
        self.pending_follow_up = None

        stop_playback = getattr(self.voice_out, "stop_playback", None)
        if callable(stop_playback):
            stop_playback()

        if open_active_window:
            self.voice_session.open_active_window(
                seconds=self.voice_session.active_listen_window_seconds,
            )
            self.voice_session.set_state("listening", detail=f"interrupted:{reason}")

        append_log(
            f"Interrupt requested: reason={reason}, source={source}, open_active_window={open_active_window}"
        )

    def _attach_audio_coordinator(self, backend: Any) -> None:
        if backend is None:
            return

        setter = getattr(backend, "set_audio_coordinator", None)
        if callable(setter):
            setter(self.audio_coordinator)
            return

        try:
            setattr(backend, "audio_coordinator", self.audio_coordinator)
        except Exception:
            return
        
    def _clear_interaction_context(self, *, reason: str, close_active_window: bool = True) -> None:
        had_pending_confirmation = self.pending_confirmation is not None
        had_pending_follow_up = self.pending_follow_up is not None

        self.pending_confirmation = None
        self.pending_follow_up = None

        if close_active_window:
            self.voice_session.close_active_window()
            self.voice_session.set_state("standby", detail=reason)

        if had_pending_confirmation or had_pending_follow_up:
            append_log(
                "Interaction context cleared: "
                f"reason={reason}, had_pending_confirmation={had_pending_confirmation}, "
                f"had_pending_follow_up={had_pending_follow_up}"
            )

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
        normalized_lang = self._normalize_lang(lang)
        cleaned_spoken_text = " ".join(str(spoken_text or "").split()).strip()
        if not cleaned_spoken_text:
            return

        self._clear_interaction_context(
            reason=f"async_notification_{source}",
            close_active_window=True,
        )

        shown_lines = [str(line).strip() for line in display_lines if str(line).strip()]
        if display_title and shown_lines:
            self.display.show_block(
                display_title,
                shown_lines,
                duration=(display_duration if display_duration is not None else self.default_overlay_seconds),
            )

        metadata = {
            "source": source,
            "route_kind": route_kind,
            "delivery_mode": "async_notification",
        }
        if action:
            metadata["action"] = action
        if extra_metadata:
            metadata.update(extra_metadata)

        self._remember_assistant_turn(
            cleaned_spoken_text,
            language=normalized_lang,
            metadata=metadata,
        )

        self.voice_session.set_state("speaking", detail=f"async_notification:{source}")
        self.voice_out.speak(cleaned_spoken_text, language=normalized_lang)
        self.voice_session.close_active_window()
        self.voice_session.set_state("standby", detail=f"async_notification_complete:{source}")

        append_log(
            "Async notification delivered: "
            f"source={source}, lang={normalized_lang}, action={action or ''}, text={cleaned_spoken_text}"
        )

    def _reminder_language(self, reminder: dict[str, Any]) -> str:
        stored = reminder.get("language") or reminder.get("lang")
        return self._normalize_lang(stored or self.last_language)

    def _looks_like_cancel_request(self, text: str) -> bool:
        return self.voice_session.looks_like_cancel_request(text)

    def _cancel_active_request(self, lang: str) -> bool:
        had_pending = bool(self.pending_confirmation or self.pending_follow_up)
        self.pending_confirmation = None
        self.pending_follow_up = None

        if had_pending:
            spoken_text = self._localized(
                lang,
                "Dobrze. Anuluję to.",
                "Okay. I will cancel that.",
            )
        else:
            spoken_text = self._localized(
                lang,
                "Nie ma teraz nic do anulowania.",
                "There is nothing to cancel right now.",
            )

        self._remember_assistant_turn(
            spoken_text,
            language=lang,
            metadata={
                "source": "system_cancel",
                "route_kind": "cancel",
                "had_pending": had_pending,
            },
        )
        self.voice_out.speak(spoken_text, language=lang)
        return True

    def _extract_pending_override_intent(self, text: str) -> IntentResult | None:
        result = self.parser.parse(text)
        if result.action in {"unknown", "unclear", "confirm_yes", "confirm_no"}:
            return None

        return IntentResult(
            action=result.action,
            data=result.data,
            confidence=result.confidence,
            needs_confirmation=result.needs_confirmation,
            suggestions=list(result.suggestions),
            normalized_text=result.normalized_text,
        )

    def _remember_user_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conversation_memory.add_user_turn(
            text,
            language=language,
            metadata=metadata,
        )

    def _remember_assistant_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conversation_memory.add_assistant_turn(
            text,
            language=language,
            metadata=metadata,
        )

    def _remember_dialogue_report(
        self,
        full_text: str,
        *,
        language: str,
        route: CompanionRoute,
        source: str,
    ) -> None:
        cleaned_text = " ".join(str(full_text or "").split()).strip()
        if not cleaned_text:
            return

        self._remember_assistant_turn(
            cleaned_text,
            language=language,
            metadata={
                "source": source,
                "route_kind": route.kind,
                "topics": list(route.conversation_topics),
                "suggested_actions": list(route.suggested_actions),
            },
        )

    def _build_dialogue_user_profile(self, preferred_language: str | None = None) -> dict[str, Any]:
        profile = dict(self.user_profile)
        recent_context_block = self.conversation_memory.build_context_block(
            limit=6,
            preferred_language=self._normalize_lang(preferred_language or self.last_language),
            include_timestamps=False,
        )
        profile["recent_conversation_context"] = recent_context_block
        return profile

    def _reminder_loop(self) -> None:
        while not self._stop_background.is_set():
            due_reminders = self.reminders.check_due_reminders()

            for reminder in due_reminders:
                message = str(reminder.get("message", "Reminder triggered.")).strip() or "Reminder triggered."
                lang = self._reminder_language(reminder)

                spoken_text = self._localized(
                    lang,
                    f"Przypomnienie. {message}",
                    f"Reminder. {message}",
                )

                self._deliver_async_notification(
                    lang=lang,
                    spoken_text=spoken_text,
                    display_title=self._localized(lang, "PRZYPOMNIENIE", "REMINDER"),
                    display_lines=[message],
                    source="reminder",
                    route_kind="reminder",
                    action="reminder_due",
                    display_duration=max(self.default_overlay_seconds, 12.0),
                    extra_metadata={
                        "reminder_id": reminder.get("id"),
                    },
                )

                append_log(
                    f"Reminder triggered: id={reminder.get('id')}, lang={lang}, message={message}"
                )

            time.sleep(1)

    def _build_dialogue_display_lines(self, text: str, max_lines: int = 2, max_chars: int = 20) -> list[str]:
        cleaned = str(text or "").strip()
        if not cleaned:
            return []

        chunks = [
            part.strip()
            for part in re.split(r"[.!?,:;]", cleaned)
            if part and part.strip()
        ]

        if not chunks:
            chunks = [cleaned]

        lines: list[str] = []
        for chunk in chunks:
            shortened = chunk[:max_chars].rstrip()
            if len(chunk) > max_chars:
                shortened = shortened.rstrip() + "..."
            if shortened:
                lines.append(shortened)
            if len(lines) >= max_lines:
                break

        return lines

    def _speak_dialogue_reply(self, reply) -> None:
        if reply.display_title:
            display_lines = reply.display_lines or self._build_dialogue_display_lines(reply.spoken_text)
            if display_lines:
                self.display.show_block(
                    reply.display_title,
                    display_lines,
                    duration=self.default_overlay_seconds,
                )

        if reply.spoken_text:
            spoken_ok = self.voice_out.speak(reply.spoken_text, language=reply.language)
            if not spoken_ok or self._interrupt_requested():
                return

        if reply.follow_up_text:
            follow_up_ok = self.voice_out.speak(reply.follow_up_text, language=reply.language)
            if not follow_up_ok or self._interrupt_requested():
                return
   
    def _run_with_thinking_ack(self, *, language: str, detail: str, operation):
        normalized_language = self._normalize_lang(language)

        ack_handle = self.thinking_ack_service.arm(
            language=normalized_language,
            detail=detail,
        )

        try:
            return operation()
        finally:
            ack_handle.cancel()

    def _build_dialogue_plan(self, route: CompanionRoute, dialogue_user_profile: dict[str, Any]):
        if hasattr(self.dialogue, "build_response_plan"):
            return self.dialogue.build_response_plan(route, dialogue_user_profile)

        reply = self.dialogue.build_reply(route, dialogue_user_profile)

        if hasattr(self.dialogue, "reply_to_plan"):
            return self.dialogue.reply_to_plan(reply, route_kind=route.kind)

        raise RuntimeError("CompanionDialogueService cannot build a response plan.")

    def _execute_dialogue_route(self, route: CompanionRoute, lang: str) -> bool:
        dialogue_user_profile = self._build_dialogue_user_profile(preferred_language=lang)

        try:
            self.voice_session.set_state("routing", detail=f"dialogue_plan:{route.kind}")
            plan = self._run_with_thinking_ack(
                language=lang,
                detail=f"thinking_dialogue_plan:{route.kind}",
                operation=lambda: self._build_dialogue_plan(route, dialogue_user_profile),
            )

            self.voice_session.set_state("speaking", detail=f"dialogue_stream:{route.kind}")
            report = self.response_streamer.execute(plan)

            self._remember_dialogue_report(
                report.full_text,
                language=lang,
                route=route,
                source="streaming_response_service",
            )

            append_log(
                f"Dialogue streamed: route_kind={route.kind}, lang={lang}, "
                f"chunks={report.chunks_spoken}, text={report.full_text}"
            )
        except Exception as error:
            append_log(f"Dialogue streaming failed. Falling back to plain reply. Error: {error}")

            self.voice_session.set_state("routing", detail=f"dialogue_reply_fallback:{route.kind}")
            reply = self._run_with_thinking_ack(
                language=lang,
                detail=f"thinking_dialogue_reply_fallback:{route.kind}",
                operation=lambda: self.dialogue.build_reply(route, dialogue_user_profile),
            )

            self.voice_session.set_state("speaking", detail=f"dialogue_reply_fallback_speaking:{route.kind}")
            self._speak_dialogue_reply(reply)

            fallback_text = " ".join(
                part.strip()
                for part in [reply.spoken_text, reply.follow_up_text]
                if str(part or "").strip()
            ).strip()

            self._remember_dialogue_report(
                fallback_text,
                language=reply.language,
                route=route,
                source="dialogue_reply_fallback",
            )

        self._commit_language(lang)
        return True

    def _choose_default_mixed_action(self, suggested_actions: list[str]) -> str | None:
        if not suggested_actions:
            return None

        priority = [
            "focus_start",
            "break_start",
            "reminder_create",
            "timer_start",
        ]

        for action in priority:
            if action in suggested_actions:
                return action

        return suggested_actions[0]

    def _arm_mixed_follow_up(self, route: CompanionRoute, lang: str) -> None:
        suggested_actions = [str(action).strip() for action in route.suggested_actions if str(action).strip()]
        if not suggested_actions:
            self.pending_follow_up = None
            return

        default_action = self._choose_default_mixed_action(suggested_actions)

        self.pending_follow_up = {
            "type": "mixed_action_offer",
            "lang": self._normalize_lang(lang),
            "suggested_actions": suggested_actions,
            "default_action": default_action,
        }

        append_log(
            f"Armed mixed follow-up: lang={lang}, suggested_actions={suggested_actions}, "
            f"default_action={default_action}"
        )

    def _execute_intent(self, result: IntentResult, lang: str) -> bool:
        command_lang = self._normalize_lang(lang)

        append_log(
            f"Parsed intent: action={result.action}, data={result.data}, text={result.normalized_text}, lang={command_lang}"
        )

        self._commit_language(command_lang)

        handled = dispatch_intent(self, result, command_lang)
        if handled is not None:
            return handled

        if result.action in {"confirm_yes", "confirm_no"}:
            fallback_text = self._localized(
                command_lang,
                "Nie ma teraz nic do potwierdzenia.",
                "There is nothing to confirm right now.",
            )
            self._remember_assistant_turn(
                fallback_text,
                language=command_lang,
                metadata={
                    "source": "intent_fallback",
                    "route_kind": "action",
                    "action": result.action,
                },
            )
            self._speak_localized(
                command_lang,
                "Nie ma teraz nic do potwierdzenia.",
                "There is nothing to confirm right now.",
            )
            return True

        if result.action == "unclear" and result.suggestions:
            return self._ask_for_confirmation(result.suggestions, command_lang)

        fallback_text = self._localized(
            command_lang,
            "Nie mam jeszcze tej funkcji w obecnej wersji, ale nadal mogę Ci pomóc. Mogę ustawić timer, przypomnienie, tryb focus, przerwę albo coś zapamiętać.",
            "I do not have that feature in this version yet, but I can still help you. I can set a timer, a reminder, start focus mode, begin a break, or remember something for you.",
        )
        self._remember_assistant_turn(
            fallback_text,
            language=command_lang,
            metadata={
                "source": "intent_fallback",
                "route_kind": "action",
                "action": result.action,
            },
        )
        self._speak_localized(
            command_lang,
            "Nie mam jeszcze tej funkcji w obecnej wersji, ale nadal mogę Ci pomóc. Mogę ustawić timer, przypomnienie, tryb focus, przerwę albo coś zapamiętać.",
            "I do not have that feature in this version yet, but I can still help you. I can set a timer, a reminder, start focus mode, begin a break, or remember something for you.",
        )
        return True

    def _handle_conversation_route(self, route: CompanionRoute, lang: str) -> bool:
        self.pending_follow_up = None
        return self._execute_dialogue_route(route, lang)

    def _handle_mixed_route(self, route: CompanionRoute, lang: str) -> bool:
        self.pending_follow_up = None
        self._execute_dialogue_route(route, lang)

        if route.has_action:
            return self._execute_intent(route.action_result, lang)

        self._arm_mixed_follow_up(route, lang)
        self._commit_language(lang)
        return True

    def _handle_unclear_route(self, route: CompanionRoute, lang: str) -> bool:
        self.pending_follow_up = None

        if route.action_result.action == "unclear" and route.action_result.suggestions:
            self._commit_language(lang)
            return self._ask_for_confirmation(route.action_result.suggestions, lang)

        normalized = route.normalized_text
        looks_like_feature_request = any(
            phrase in normalized
            for phrase in [
                "can you",
                "could you",
                "will you",
                "czy mozesz",
                "mozesz",
                "potrafisz",
                "zrob",
                "zrobisz",
                "uruchom",
                "wlacz",
                "wlaczysz",
                "turn on",
                "start",
                "open",
                "show",
            ]
        )

        if looks_like_feature_request:
            fallback_text = self._localized(
                lang,
                "Nie mam jeszcze tej funkcji w obecnej wersji, ale nadal jestem do dyspozycji. Mogę ustawić timer, przypomnienie, tryb focus, przerwę albo coś zapamiętać.",
                "I do not have that feature in this version yet, but I am still here to help. I can set a timer, a reminder, start focus mode, begin a break, or remember something for you.",
            )
            self._remember_assistant_turn(
                fallback_text,
                language=lang,
                metadata={
                    "source": "unclear_feature_fallback",
                    "route_kind": "unclear",
                },
            )
            self._speak_localized(
                lang,
                "Nie mam jeszcze tej funkcji w obecnej wersji, ale nadal jestem do dyspozycji. Mogę ustawić timer, przypomnienie, tryb focus, przerwę albo coś zapamiętać.",
                "I do not have that feature in this version yet, but I am still here to help. I can set a timer, a reminder, start focus mode, begin a break, or remember something for you.",
            )
            self._commit_language(lang)
            return True

        return self._execute_dialogue_route(route, lang)

    def _semantic_override(self, routing_text: str, command_lang: str):
        normalized_routing_text = self._normalize_text(routing_text)
        match = self.semantic_matcher.match(routing_text)

        if match is None:
            return None

        append_log(
            f"Semantic match: intent={match.intent_name}, score={match.score:.2f}, "
            f"route_hint={match.route_hint}, example='{match.example_text}', method={match.method}"
        )

        if match.intent_name == "support_tired" and match.score >= 0.68:
            return {
                "mode": "route_text",
                "text": "i feel tired",
                "lang": command_lang,
            }

        if match.intent_name == "talk_request" and match.score >= 0.68:
            return {
                "mode": "route_text",
                "text": "can we talk for a minute",
                "lang": command_lang,
            }

        if match.intent_name == "humour_request" and match.score >= 0.70:
            if not self._looks_like_humour_request(normalized_routing_text):
                return None
            return {
                "mode": "route_text",
                "text": "powiedz cos smiesznego" if command_lang == "pl" else "tell me something funny",
                "lang": command_lang,
            }

        if match.intent_name == "riddle_request" and match.score >= 0.70:
            if not self._looks_like_riddle_request(normalized_routing_text):
                return None
            return {
                "mode": "route_text",
                "text": "zadaj mi zagadke" if command_lang == "pl" else "give me a riddle",
                "lang": command_lang,
            }

        if match.intent_name == "shutdown_request" and match.score >= 0.72:
            if not self._looks_like_shutdown_command(normalized_routing_text):
                return None

            looks_like_system_shutdown = (
                "system" in normalized_routing_text
                or {"raspberry", "pi"}.issubset(set(normalized_routing_text.split()))
                or "komputer" in normalized_routing_text
            )

            if looks_like_system_shutdown:
                return {
                    "mode": "route_text",
                    "text": "wylacz system" if command_lang == "pl" else "shutdown",
                    "lang": command_lang,
                }

            return {
                "mode": "route_text",
                "text": "wylacz asystenta" if command_lang == "pl" else "turn off assistant",
                "lang": command_lang,
            }

        if self.pending_follow_up:
            if match.intent_name == "break_choice" and match.score >= 0.66:
                return {
                    "mode": "follow_up_text",
                    "text": "przerwa" if command_lang == "pl" else "break mode",
                    "lang": command_lang,
                }

            if match.intent_name == "focus_choice" and match.score >= 0.66:
                return {
                    "mode": "follow_up_text",
                    "text": "focus" if command_lang == "pl" else "focus mode",
                    "lang": command_lang,
                }

            if match.intent_name == "decline" and match.score >= 0.66:
                return {
                    "mode": "follow_up_text",
                    "text": "nie" if command_lang == "pl" else "no",
                    "lang": command_lang,
                }

        return None

    def handle_command(self, text: str) -> bool:
        self.interrupt_controller.clear()

        cleaned = text.strip()
        if not cleaned:
            return True

        normalized_utterance = self.utterance_normalizer.normalize(cleaned)
        routing_text = normalized_utterance.canonical_text or cleaned

        self._last_raw_command_text = cleaned
        self._last_normalized_command_text = self._normalize_text(routing_text)

        detected_lang = self._normalize_lang(self._detect_language(cleaned))
        normalizer_language_hint = self._normalize_lang(normalized_utterance.detected_language_hint)

        command_lang = self._prefer_command_language(
            routing_text,
            detected_lang,
            normalizer_language_hint,
        )

        semantic_override = self._semantic_override(routing_text, command_lang)
        if semantic_override is not None:
            routing_text = semantic_override["text"]
            command_lang = self._normalize_lang(semantic_override["lang"])
            self._last_normalized_command_text = self._normalize_text(routing_text)

        parser_result = self.parser.parse(routing_text)

        self._remember_user_turn(
            cleaned,
            language=command_lang,
            metadata={
                "routing_text": routing_text,
                "normalized_text": self._last_normalized_command_text,
                "detected_language": detected_lang,
                "normalizer_language_hint": normalizer_language_hint,
                "corrections": list(normalized_utterance.corrections_applied or []),
            },
        )

        append_log(
            f"User said: {cleaned} | routing_text={routing_text} | normalized={self._last_normalized_command_text} | "
            f"detected_lang={detected_lang} | normalizer_hint={normalizer_language_hint} | command_lang={command_lang} | "
            f"corrections={normalized_utterance.corrections_applied or []}"
        )

        if self.pending_confirmation or self.pending_follow_up:
            if self._looks_like_cancel_request(routing_text):
                self._commit_language(command_lang)
                return self._cancel_active_request(command_lang)

        fast_decision = self.fast_command_lane.classify(
            routing_text,
            parser_result=parser_result,
            pending_confirmation=bool(self.pending_confirmation),
            pending_follow_up=bool(self.pending_follow_up),
        )
        if fast_decision is not None:
            return self.fast_command_lane.execute(self, fast_decision, command_lang)

        if self.pending_confirmation or self.pending_follow_up:
            override_intent = self._extract_pending_override_intent(routing_text)
            if override_intent is not None:
                append_log(
                    "Pending flow interrupted by a new command: "
                    f"action={override_intent.action}, data={override_intent.data}"
                )
                self.pending_confirmation = None
                self.pending_follow_up = None
                self._commit_language(command_lang)
                return self._execute_intent(override_intent, command_lang)

        if self.pending_confirmation:
            handled_confirmation = self._handle_pending_confirmation(routing_text, command_lang)
            self._commit_language(command_lang)
            return handled_confirmation

        if self.pending_follow_up:
            handled_follow_up = self._handle_pending_follow_up(routing_text, command_lang)
            if handled_follow_up is not None:
                self._commit_language(command_lang)
                return handled_follow_up

        route = self.router.route(routing_text, preferred_language=command_lang)

        append_log(
            f"Route decision: kind={route.kind}, reply_mode={route.reply_mode}, "
            f"topics={route.conversation_topics}, suggestions={route.suggested_actions}, "
            f"action={route.action_result.action}, confidence={route.confidence:.2f}"
        )

        if route.kind == "action":
            self.pending_follow_up = None
            return self._execute_intent(route.action_result, command_lang)

        if route.kind == "mixed":
            return self._handle_mixed_route(route, command_lang)

        if route.kind == "conversation":
            return self._handle_conversation_route(route, command_lang)

        return self._handle_unclear_route(route, command_lang)