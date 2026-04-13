from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteKind, StreamMode, normalize_text
from modules.shared.logging.logger import log_exception


class CoreAssistantHelpersMixin:
    def _detect_language(self, text: str) -> str:
        lowered = normalize_text(text)
        tokens = set(lowered.split())

        polish_markers = {
            "jest",
            "czy",
            "pokaz",
            "godzina",
            "czas",
            "data",
            "dzien",
            "przerwa",
            "skupienia",
            "zapamietaj",
            "usun",
            "przypomnij",
            "ktora",
            "jaka",
            "miesiac",
            "rok",
            "pamietasz",
            "pomoc",
            "wytlumacz",
            "wyjasnij",
            "zamknij",
            "wylacz",
            "gdzie",
            "klucze",
        }
        english_markers = {
            "what",
            "time",
            "date",
            "day",
            "month",
            "year",
            "show",
            "help",
            "explain",
            "close",
            "turn",
            "off",
            "remember",
            "remind",
            "where",
            "keys",
            "assistant",
            "shutdown",
            "timer",
            "focus",
            "break",
        }

        polish_hits = len(tokens & polish_markers)
        english_hits = len(tokens & english_markers)

        if polish_hits > english_hits:
            return "pl"
        if english_hits > polish_hits:
            return "en"
        if any(char in text for char in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"):
            return "pl"
        return self._normalize_lang(self.last_language)

    def _normalize_lang(self, language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        if normalized.startswith("pl"):
            return "pl"
        return "en"

    def _commit_language(self, language: str | None) -> str:
        self.last_language = self._normalize_lang(language)
        return self.last_language

    def _localized(self, lang: str, polish_text: str, english_text: str) -> str:
        return polish_text if self._normalize_lang(lang) == "pl" else english_text

    def _looks_like_cancel_request(self, text: str) -> bool:
        if self.voice_session.looks_like_cancel_request(text):
            return True

        normalized = normalize_text(text)
        cancel_markers = {
            "cancel",
            "stop",
            "never mind",
            "leave it",
            "anuluj",
            "zostaw to",
            "niewazne",
            "przestan",
        }
        return normalized in cancel_markers

    def _cancel_active_request(self, lang: str) -> bool:
        had_pending = bool(self.pending_confirmation or self.pending_follow_up)
        self.pending_confirmation = None
        self.pending_follow_up = None

        spoken_text = self._localized(
            lang,
            "Dobrze. Anuluję to." if had_pending else "Nie ma teraz nic do anulowania.",
            "Okay. I will cancel that." if had_pending else "There is nothing to cancel right now.",
        )
        return self.deliver_text_response(
            spoken_text,
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source="assistant_cancel_request",
            metadata={"had_pending": had_pending},
        )

    def _clear_interaction_context(self, *, close_active_window: bool = False) -> None:
        self.pending_confirmation = None
        self.pending_follow_up = None
        self.interrupt_controller.clear()
        if close_active_window:
            self.voice_session.close_active_window()

    def _runtime_status_snapshot(self) -> dict[str, Any]:
        runtime_product = getattr(self, "runtime_product", None)
        if runtime_product is None:
            return {}

        snapshot_method = getattr(runtime_product, "snapshot", None)
        if not callable(snapshot_method):
            return {}

        try:
            snapshot = snapshot_method()
        except Exception as error:
            log_exception("Failed to read runtime product snapshot", error)
            return {}

        return dict(snapshot) if isinstance(snapshot, dict) else {}

    def _runtime_overlay_lines(self) -> list[str]:
        snapshot = self._runtime_status_snapshot()
        lifecycle_state = str(
            snapshot.get("lifecycle_state", "booting") or "booting"
        ).strip().lower()

        if lifecycle_state == "ready":
            status_line = "runtime ready"
        elif lifecycle_state in {"degraded", "failed"}:
            status_line = "runtime degraded"
        elif lifecycle_state == "shutting_down":
            status_line = "runtime stopping"
        else:
            status_line = "runtime booting"

        message = str(snapshot.get("status_message", "") or "").strip()
        if message:
            compact = " ".join(message.split())
            if compact:
                status_line = compact[:20].lower()

        return [
            "starting up...",
            status_line,
        ]

    def _startup_greeting(self, *, report_ok: bool) -> str:
        snapshot = self._runtime_status_snapshot()
        lifecycle_state = str(snapshot.get("lifecycle_state", "") or "").strip().lower()
        blockers = [
            str(item).strip()
            for item in snapshot.get("blockers", [])
            if str(item).strip()
        ]
        degraded = self._degraded_component_names(snapshot=snapshot)

        if lifecycle_state == "ready" and report_ok:
            return (
                f"Hello. I am {self.ASSISTANT_NAME}. "
                "Startup checks look good. Say NeXa when you need me."
            )

        if blockers:
            blocker_text = ", ".join(blockers[:3])
            return (
                f"Hello. I am {self.ASSISTANT_NAME}. "
                f"Some required services need attention: {blocker_text}. "
                "I will start in a limited mode."
            )

        if degraded:
            degraded_text = ", ".join(degraded[:3])
            return (
                f"Hello. I am {self.ASSISTANT_NAME}. "
                f"Startup checks found some degraded modules: {degraded_text}. "
                "I am still ready to help."
            )

        if lifecycle_state == "degraded":
            return (
                f"Hello. I am {self.ASSISTANT_NAME}. "
                "Startup checks completed with some limitations. "
                "I am still ready to help."
            )

        return (
            f"Hello. I am {self.ASSISTANT_NAME}. "
            "Startup checks completed. I am ready to help."
        )

    def _degraded_component_names(self, *, snapshot: dict[str, Any] | None = None) -> list[str]:
        safe_snapshot = snapshot if isinstance(snapshot, dict) else self._runtime_status_snapshot()
        services = safe_snapshot.get("services", {})

        if isinstance(services, dict):
            degraded_names: list[str] = []
            for name, payload in services.items():
                if not isinstance(payload, dict):
                    continue

                state = str(payload.get("state", "") or "").strip().lower()
                if state in {"degraded", "failed"}:
                    degraded_names.append(str(name))

            if degraded_names:
                return degraded_names

        return [
            name
            for name, status in self.backend_statuses.items()
            if (not bool(getattr(status, "ok", False)))
            or bool(getattr(status, "fallback_used", False))
        ]

    def _minutes_text(self, minutes: float | None, language: str) -> str:
        safe_minutes = int(round(float(minutes or 0)))
        if safe_minutes <= 0:
            safe_minutes = 1

        if language == "pl":
            if safe_minutes == 1:
                return "1 minutę"
            return f"{safe_minutes} minut"

        if safe_minutes == 1:
            return "1 minute"
        return f"{safe_minutes} minutes"

    def _display_lines(self, text: str) -> list[str]:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return [""]

        max_chars = int(
            self.settings.get("streaming", {}).get("max_display_chars_per_line", 20)
        )
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
                if len(lines) == 2:
                    break
            else:
                current = candidate

        if current and len(lines) < 2:
            lines.append(current)

        return lines[:2] or [cleaned[:max_chars]]

    def _resolve_stream_mode(self, raw_value: Any) -> StreamMode:
        normalized = str(raw_value or StreamMode.SENTENCE.value).strip().lower()
        for member in StreamMode:
            if member.value == normalized:
                return member
        return StreamMode.SENTENCE

    def _thinking_ack_start(self, *, language: str, detail: str = "thinking") -> None:
        for method_name in ("arm", "start", "schedule"):
            method = getattr(self.thinking_ack_service, method_name, None)
            if not callable(method):
                continue
            try:
                method(language=language, detail=detail)
            except TypeError:
                try:
                    method(language=language)
                except TypeError:
                    method()
            return

    def _thinking_ack_stop(self) -> None:
        for method_name in ("cancel", "stop", "clear"):
            method = getattr(self.thinking_ack_service, method_name, None)
            if callable(method):
                method()
                return

    def _timer_type_from_payload(self, payload: dict[str, Any]) -> str:
        for key in ("timer_type", "mode", "kind", "label", "action"):
            value = payload.get(key)
            if value:
                normalized = normalize_text(str(value))
                if "focus" in normalized:
                    return "focus"
                if "break" in normalized:
                    return "break"
                return "timer"
        return "timer"

    def _timer_minutes_from_payload(self, payload: dict[str, Any]) -> float:
        for key in ("minutes", "duration_minutes", "duration", "length_minutes"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return self.default_focus_minutes

    def _safe_timer_status(self) -> dict[str, Any]:
        status_method = getattr(self.timer, "status", None)
        if callable(status_method):
            try:
                value = status_method()
                if isinstance(value, dict):
                    return value
            except Exception as error:
                log_exception("Failed to read timer status", error)
        return {"running": False}

    def _safe_stop_mobility(self) -> None:
        if self.mobility is None:
            return
        stop_method = getattr(self.mobility, "stop", None)
        if callable(stop_method):
            try:
                stop_method()
            except Exception as error:
                log_exception("Failed to stop mobility backend", error)

    def _safe_close_runtime_components(self) -> None:
        seen_ids: set[int] = set()
        components = [
            ("wake_gate", self.wake_gate),
            ("voice_input", self.voice_in),
            ("voice_output", self.voice_out),
            ("vision", self.vision),
            ("mobility", self.mobility),
            ("display", self.display),
        ]

        for label, component in components:
            if component is None:
                continue

            component_id = id(component)
            if component_id in seen_ids:
                continue
            seen_ids.add(component_id)

            close_method = getattr(component, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception as error:
                    log_exception(f"Failed to close runtime component: {label}", error)