from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from modules.shared.logging.logger import append_log
from modules.runtime.contracts import (
    AssistantChunk,
    ChunkKind,
    ResponsePlan,
    RouteKind,
    StreamMode,
    create_turn_id,
)

from .builders import (
    ActionFollowUpPromptSpec,
    ActionResponseSpec,
    MemorySkillResponseBuilder,
    ReminderSkillResponseBuilder,
    TimerSkillResponseBuilder,
)
from .models import SkillResult


class ActionResponseHelpersMixin:
    def _ask_for_confirmation(
        self,
        *,
        suggestions: list[dict[str, Any]],
        language: str,
        original_text: str = "",
    ) -> bool:
        lang = self.assistant._normalize_lang(language)
        safe_suggestions = self._coerce_suggestions(suggestions)
        if not safe_suggestions:
            return self._deliver_simple_action_response(
                language=lang,
                action="confirm_no",
                spoken_text=self._localized(
                    lang,
                    "Nie mam jeszcze wystarczających sugestii, żeby poprosić o potwierdzenie.",
                    "I do not have enough suggestions yet to ask for confirmation.",
                ),
                display_title="CONFIRMATION",
                display_lines=self._localized_lines(
                    lang,
                    ["brak sugestii"],
                    ["no suggestions"],
                ),
                extra_metadata={"phase": "missing_suggestions"},
            )

        self.assistant.pending_confirmation = {
            "language": lang,
            "suggestions": safe_suggestions,
            "original_text": str(original_text or "").strip(),
        }

        first = self._action_label(
            str(safe_suggestions[0].get("action", "")),
            lang,
            explicit_label=safe_suggestions[0].get("label"),
        )
        second = None
        if len(safe_suggestions) > 1:
            second = self._action_label(
                str(safe_suggestions[1].get("action", "")),
                lang,
                explicit_label=safe_suggestions[1].get("label"),
            )

        if lang == "pl":
            spoken = f"Czy chodziło Ci o {first}"
            lines = [f"1: {first}"]
            if second:
                spoken += f" czy o {second}"
                lines.append(f"2: {second}")
            spoken += "? Powiedz tak albo nie."
            lines.append("powiedz tak lub nie")
        else:
            spoken = f"Did you mean {first}"
            lines = [f"1: {first}"]
            if second:
                spoken += f" or {second}"
                lines.append(f"2: {second}")
            spoken += "? Say yes or no."
            lines.append("say yes or no")

        return self.assistant.deliver_text_response(
            spoken,
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source="action_confirmation_prompt",
            metadata=self._current_action_response_metadata(
                language=lang,
                action="confirmation_prompt",
                extra_metadata={
                    "pending_type": "confirmation",
                    "suggestions": [item["action"] for item in safe_suggestions],
                },
            ),
        )

    def _current_action_response_metadata(
        self,
        *,
        language: str,
        action: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "action": str(action or "").strip(),
            "language": str(language or "").strip().lower(),
        }

        route = getattr(self, "_active_route", None)
        if route is not None:
            route_metadata = dict(getattr(route, "metadata", {}) or {})
            metadata.update(
                {
                    "route_kind": getattr(route.kind, "value", str(route.kind)),
                    "primary_intent": str(getattr(route, "primary_intent", "") or "").strip(),
                    "topics": list(getattr(route, "conversation_topics", []) or []),
                    "route_notes": list(getattr(route, "notes", []) or []),
                    "capture_phase": str(route_metadata.get("capture_phase", "") or ""),
                    "capture_mode": str(route_metadata.get("capture_mode", "") or ""),
                    "capture_backend": str(route_metadata.get("capture_backend", "") or ""),
                    "parser_action": str(route_metadata.get("parser_action", "") or ""),
                    "route_metadata": route_metadata,
                }
            )

        resolved = getattr(self, "_active_resolved_action", None)
        if resolved is not None:
            metadata.update(
                {
                    "action_source": str(getattr(resolved, "source", "") or "").strip(),
                    "action_confidence": float(getattr(resolved, "confidence", 0.0) or 0.0),
                    "resolved_route_kind": str(getattr(resolved, "route_kind", "") or "").strip(),
                    "resolved_primary_intent": str(getattr(resolved, "primary_intent", "") or "").strip(),
                }
            )

        skill_request = getattr(self, "_active_skill_request", None)
        if skill_request is not None:
            metadata.update(
                {
                    "skill_request_turn_id": str(getattr(skill_request, "turn_id", "") or "").strip(),
                    "skill_request_action": str(getattr(skill_request, "action", "") or "").strip(),
                    "skill_request_source": str(getattr(skill_request, "source", "") or "").strip(),
                    "skill_request_confidence": float(getattr(skill_request, "confidence", 0.0) or 0.0),
                    "skill_request_capture_phase": str(getattr(skill_request, "capture_phase", "") or "").strip(),
                    "skill_request_capture_mode": str(getattr(skill_request, "capture_mode", "") or "").strip(),
                    "skill_request_capture_backend": str(getattr(skill_request, "capture_backend", "") or "").strip(),
                }
            )

        if extra_metadata:
            metadata.update(dict(extra_metadata))

        return metadata

    def _accepted_action_result(
        self,
        *,
        action: str,
        status: str = "accepted",
        extra_metadata: dict[str, Any] | None = None,
    ) -> SkillResult:
        metadata = {
            "source": "action_flow",
            "response_kind": "accepted_only",
        }
        if extra_metadata:
            metadata.update(dict(extra_metadata))

        return SkillResult(
            action=str(action or "").strip() or "unknown",
            handled=True,
            response_delivered=False,
            status=str(status or "accepted").strip() or "accepted",
            metadata=metadata,
        )


    def _deliver_action_response_spec(
        self,
        *,
        language: str,
        spec: ActionResponseSpec,
    ) -> bool:
        return self._deliver_simple_action_response(
            language=language,
            action=spec.action,
            spoken_text=spec.spoken_text,
            display_title=spec.display_title,
            display_lines=list(spec.display_lines or []),
            extra_metadata=dict(spec.extra_metadata or {}),
            chunk_kind=spec.chunk_kind,
        )

    def _deliver_action_follow_up_prompt_spec(
        self,
        *,
        language: str,
        spec: ActionFollowUpPromptSpec,
    ) -> SkillResult:
        return self._deliver_action_follow_up_prompt(
            language=language,
            action=spec.action,
            spoken_text=spec.spoken_text,
            source=spec.source,
            follow_up_type=spec.follow_up_type,
            extra_metadata=dict(spec.extra_metadata or {}),
        )


    def _deliver_action_follow_up_prompt(
        self,
        *,
        language: str,
        action: str,
        spoken_text: str,
        source: str,
        follow_up_type: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> SkillResult:
        metadata = self._current_action_response_metadata(
            language=language,
            action=action,
            extra_metadata={
                "follow_up_type": str(follow_up_type or "").strip(),
                **dict(extra_metadata or {}),
            },
        )
        delivered = bool(
            self.assistant.deliver_text_response(
                spoken_text,
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source=str(source or "action_follow_up_prompt").strip() or "action_follow_up_prompt",
                metadata=metadata,
            )
        )
        return SkillResult(
            action=str(action or "").strip() or "unknown",
            handled=True,
            response_delivered=delivered,
            status="awaiting_confirmation",
            metadata={
                "source": str(source or "action_follow_up_prompt").strip() or "action_follow_up_prompt",
                "follow_up_type": str(follow_up_type or "").strip(),
                "response_kind": "follow_up_prompt",
                **dict(extra_metadata or {}),
            },
        )

    def _should_prefetch_action_response(
        self,
        *,
        spoken_text: str,
        immediate_delivery: bool = False,
    ) -> bool:
        streaming_cfg = getattr(self.assistant, "settings", {}).get("streaming", {})
        configured = streaming_cfg.get("prefetch_action_responses")
        if configured is None:
            enabled = True
        else:
            enabled = bool(configured)

        if not enabled:
            return False

        if immediate_delivery:
            return False

        return bool(str(spoken_text or "").strip())

    def _prefetch_action_response(
        self,
        *,
        spoken_text: str,
        language: str,
        action: str,
        immediate_delivery: bool = False,
    ) -> None:
        if not self._should_prefetch_action_response(
            spoken_text=spoken_text,
            immediate_delivery=immediate_delivery,
        ):
            return

        prepare_method = getattr(getattr(self.assistant, "voice_out", None), "prepare_speech", None)
        if not callable(prepare_method):
            return

        try:
            prepare_method(spoken_text, language)
            append_log(
                "Action response TTS prefetch queued: "
                f"action={action}, lang={language}, chars={len(str(spoken_text or '').strip())}"
            )
        except Exception as error:
            append_log(
                "Action response TTS prefetch failed: "
                f"action={action}, error={error}"
            )

    def _deliver_simple_action_response(
        self,
        *,
        language: str,
        action: str,
        spoken_text: str,
        display_title: str,
        display_lines: list[str],
        extra_metadata: dict[str, Any] | None = None,
        chunk_kind: ChunkKind = ChunkKind.CONTENT,
    ) -> bool:
        self._prefetch_action_response(
            spoken_text=spoken_text,
            language=language,
            action=action,
            immediate_delivery=True,
        )

        plan = ResponsePlan(
            turn_id=create_turn_id(),
            language=language,
            route_kind=RouteKind.ACTION,
            stream_mode=StreamMode.SENTENCE,
            metadata={
                "display_title": display_title,
                "display_lines": display_lines,
            },
        )
        plan.chunks.append(
            AssistantChunk(
                text=spoken_text,
                language=language,
                kind=chunk_kind,
                speak_now=True,
                flush=True,
                sequence_index=0,
                metadata={"action": action},
            )
        )
        response_metadata = self._current_action_response_metadata(
            language=language,
            action=action,
            extra_metadata=extra_metadata,
        )

        return bool(
            self.assistant.deliver_response_plan(
                plan,
                source=f"action_flow:{action}",
                remember=True,
                extra_metadata=response_metadata,
            )
        )

    def _deliver_feature_unavailable(self, *, language: str, action: str) -> bool:
        return self._deliver_simple_action_response(
            language=language,
            action=action,
            spoken_text=self._localized(
                language,
                "Ta funkcja nie jest teraz poprawnie podłączona.",
                "That feature is not wired correctly right now.",
            ),
            display_title="FEATURE",
            display_lines=self._localized_lines(
                language,
                ["funkcja", "niedostepna"],
                ["feature", "unavailable"],
            ),
            extra_metadata={"phase": "feature_unavailable"},
        )

    def _memory_items(self) -> dict[str, Any]:
        get_method = self._first_callable(self.assistant.memory, "get_all", "list_all", "items", "export")
        if get_method is None:
            return {}
        try:
            result = get_method()
        except Exception:
            return {}
        return dict(result or {}) if isinstance(result, dict) else {}

    def _reminder_items(self) -> list[dict[str, Any]]:
        list_method = self._first_callable(self.assistant.reminders, "list_all", "all", "items", "list")
        if list_method is None:
            return []
        try:
            result = list_method()
        except Exception:
            return []
        return list(result or []) if isinstance(result, list) else []

    def _timer_status(self) -> dict[str, Any]:
        status_method = self._first_callable(self.assistant.timer, "status", "get_status")
        if status_method is None:
            return {"running": False}
        try:
            result = status_method()
        except Exception:
            return {"running": False}
        return dict(result or {}) if isinstance(result, dict) else {"running": False}

    @staticmethod
    def _first_callable(obj: Any, *names: str):
        for name in names:
            method = getattr(obj, name, None)
            if callable(method):
                return method
        return None

    @staticmethod
    def _result_ok(result: Any) -> bool:
        if isinstance(result, tuple) and result:
            return bool(result[0])
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result["ok"])
            if "success" in result:
                return bool(result["success"])
        return bool(result)

    @staticmethod
    def _result_message(result: Any) -> str:
        if isinstance(result, tuple) and len(result) >= 2:
            return str(result[1] or "").strip()
        if isinstance(result, dict):
            for key in ("message", "detail", "error"):
                value = result.get(key)
                if value:
                    return str(value).strip()
        return ""

    @staticmethod
    def _first_present(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _resolve_minutes(self, payload: dict[str, Any], *, fallback: float) -> float:
        for key in ("minutes", "duration_minutes", "duration", "value"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                parsed = float(value)
                if parsed > 0:
                    return parsed
            except Exception:
                continue

        seconds = payload.get("seconds")
        if seconds is not None:
            try:
                parsed_seconds = int(seconds)
                if parsed_seconds > 0:
                    return max(1.0 / 60.0, parsed_seconds / 60.0)
            except Exception:
                pass

        return max(float(fallback), 0.1)

    def _resolve_reminder_seconds(self, payload: dict[str, Any]) -> int | None:
        for key in ("seconds", "after_seconds"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                parsed = int(float(value))
                if parsed > 0:
                    return parsed
            except Exception:
                continue

        for key in ("minutes", "after_minutes", "duration_minutes"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                parsed = float(value)
                if parsed > 0:
                    return max(1, int(round(parsed * 60)))
            except Exception:
                continue

        hours = payload.get("hours")
        if hours is not None:
            try:
                parsed = float(hours)
                if parsed > 0:
                    return max(1, int(round(parsed * 3600)))
            except Exception:
                pass

        return None

    def _resolve_memory_store_fields(self, payload: dict[str, Any]) -> tuple[str | None, str | None]:
        key = self._first_present(payload, "key", "subject", "item", "name")
        value = self._first_present(payload, "value", "fact", "content", "location", "message")

        if key and value:
            return key, value

        memory_text = self._first_present(payload, "memory_text", "text")
        if not memory_text:
            return key, value

        for separator in (" is ", " are ", " jest ", " sa "):
            if separator in memory_text:
                left, right = memory_text.split(separator, 1)
                left = left.strip()
                right = right.strip()
                if left and right:
                    return left, right

        location_markers = (" in ", " on ", " at ", " under ", " inside ", " w ", " na ", " pod ", " przy ")
        for marker in location_markers:
            if marker in memory_text:
                left, right = memory_text.split(marker, 1)
                left = left.strip()
                right = f"{marker.strip()} {right.strip()}".strip()
                if left and right:
                    return left, right

        return key, value

    def _coerce_suggestions(self, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        coerced: list[dict[str, Any]] = []
        for item in suggestions or []:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "")).strip().lower()
            if not action:
                continue
            suggestion = {"action": action}
            label = str(item.get("label", "")).strip()
            if label:
                suggestion["label"] = label
            payload = item.get("payload")
            if isinstance(payload, dict) and payload:
                suggestion["payload"] = dict(payload)
            coerced.append(suggestion)
        return coerced


    def _get_timer_response_builder(self) -> TimerSkillResponseBuilder:
        builder = getattr(self, "_timer_response_builder", None)
        if builder is None:
            builder = TimerSkillResponseBuilder(
                localize_text=self._localized,
                localize_lines=self._localized_lines,
                display_lines=self._display_lines,
                trim_text=self._trim_text,
                duration_text=self._duration_text,
            )
            self._timer_response_builder = builder
        return builder

    def _get_memory_response_builder(self) -> MemorySkillResponseBuilder:
        builder = getattr(self, "_memory_response_builder", None)
        if builder is None:
            builder = MemorySkillResponseBuilder(
                localize_text=self._localized,
                localize_lines=self._localized_lines,
                display_lines=self._display_lines,
                trim_text=self._trim_text,
                duration_text=self._duration_text,
            )
            self._memory_response_builder = builder
        return builder

    def _get_reminder_response_builder(self) -> ReminderSkillResponseBuilder:
        builder = getattr(self, "_reminder_response_builder", None)
        if builder is None:
            builder = ReminderSkillResponseBuilder(
                localize_text=self._localized,
                localize_lines=self._localized_lines,
                display_lines=self._display_lines,
                trim_text=self._trim_text,
                duration_text=self._duration_text,
            )
            self._reminder_response_builder = builder
        return builder



    def _action_label(
        self,
        action: str,
        language: str,
        *,
        explicit_label: Any | None = None,
    ) -> str:
        label_text = str(explicit_label or "").strip()
        if label_text:
            return label_text

        pl_label, en_label = self.ACTION_LABELS.get(
            str(action).strip().lower(),
            (str(action).replace("_", " "), str(action).replace("_", " ")),
        )
        return pl_label if self.assistant._normalize_lang(language) == "pl" else en_label

    @staticmethod
    def _now_london() -> datetime:
        return datetime.now(ZoneInfo("Europe/London"))

    def _localized(self, language: str, polish_text: str, english_text: str) -> str:
        return polish_text if self.assistant._normalize_lang(language) == "pl" else english_text

    def _localized_lines(self, language: str, polish_lines: list[str], english_lines: list[str]) -> list[str]:
        return polish_lines if self.assistant._normalize_lang(language) == "pl" else english_lines

    def _display_lines(self, text: str) -> list[str]:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return [""]

        max_chars = max(10, self._display_chars_per_line)
        if len(cleaned) <= max_chars:
            return [cleaned]

        words = cleaned.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                lines.append(current)
                current = word
                if len(lines) >= 2:
                    break
            else:
                current = candidate

        if current and len(lines) < 2:
            lines.append(current)

        if not lines:
            return [cleaned[:max_chars]]

        if len(lines) == 2 and len(" ".join(words)) > len(" ".join(lines)):
            lines[1] = self._trim_text(lines[1], max_chars)

        return lines[:2]

    @staticmethod
    def _trim_text(text: str, max_len: int) -> str:
        compact = " ".join(str(text or "").split()).strip()
        if len(compact) <= max_len:
            return compact
        return compact[: max_len - 3].rstrip() + "..."

    def _duration_text(self, seconds: int, language: str) -> str:
        safe_seconds = max(int(seconds), 1)
        if safe_seconds < 60:
            return f"{safe_seconds} sekund" if language == "pl" else f"{safe_seconds} seconds"

        minutes = max(1, int(round(safe_seconds / 60)))
        if language == "pl":
            return "1 minutę" if minutes == 1 else f"{minutes} minut"
        return "1 minute" if minutes == 1 else f"{minutes} minutes"

    @staticmethod
    def _localized_day_name(weekday: int, language: str) -> str:
        polish = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
        english = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_index = max(0, min(int(weekday), 6))
        return polish[day_index] if language == "pl" else english[day_index]

    @staticmethod
    def _localized_month_name(month: int, language: str) -> str:
        polish = [
            "",
            "styczeń",
            "luty",
            "marzec",
            "kwiecień",
            "maj",
            "czerwiec",
            "lipiec",
            "sierpień",
            "wrzesień",
            "październik",
            "listopad",
            "grudzień",
        ]
        english = [
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        month_index = max(1, min(int(month), 12))
        return polish[month_index] if language == "pl" else english[month_index]