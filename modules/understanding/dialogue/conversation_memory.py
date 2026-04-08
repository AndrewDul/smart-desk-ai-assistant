from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ConversationTurn:
    role: str
    text: str
    language: str
    created_at_iso: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "text": self.text,
            "language": self.language,
            "created_at_iso": self.created_at_iso,
            "metadata": dict(self.metadata),
        }


class ConversationMemory:
    """
    Lightweight short-term conversation memory for NeXa.

    Goals:
    - keep recent context compact and useful
    - avoid low-value repetition
    - provide stable context blocks for prompt building
    - stay deterministic and fast
    """

    def __init__(
        self,
        *,
        max_turns: int = 8,
        max_total_chars: int = 1800,
        max_turn_chars: int = 260,
    ) -> None:
        self.max_turns = max(2, int(max_turns))
        self.max_total_chars = max(200, int(max_total_chars))
        self.max_turn_chars = max(80, int(max_turn_chars))

        self._turns: list[ConversationTurn] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def add_user_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.add_turn(
            role="user",
            text=text,
            language=language,
            metadata=metadata,
        )

    def add_assistant_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.add_turn(
            role="assistant",
            text=text,
            language=language,
            metadata=metadata,
        )

    def add_turn(
        self,
        *,
        role: str,
        text: str,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        cleaned_role = self._normalize_role(role)
        cleaned_language = self._normalize_language(language)
        cleaned_text = self._clean_text(text, max_chars=self.max_turn_chars)
        cleaned_metadata = dict(metadata or {})

        if cleaned_role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported conversation role: {role}")

        if not cleaned_text:
            return

        turn = ConversationTurn(
            role=cleaned_role,
            text=cleaned_text,
            language=cleaned_language,
            created_at_iso=self._now_iso(),
            metadata=cleaned_metadata,
        )

        with self._lock:
            if self._is_consecutive_duplicate(turn):
                return

            self._turns.append(turn)
            self._trim_locked()

    def get_recent_turns(self, limit: int | None = None) -> list[ConversationTurn]:
        with self._lock:
            if limit is None:
                return list(self._turns)

            safe_limit = max(1, int(limit))
            return list(self._turns[-safe_limit:])

    def count(self) -> int:
        with self._lock:
            return len(self._turns)

    def last_turn(self) -> ConversationTurn | None:
        with self._lock:
            return self._turns[-1] if self._turns else None

    def last_user_turn(self) -> ConversationTurn | None:
        with self._lock:
            for turn in reversed(self._turns):
                if turn.role == "user":
                    return turn
        return None

    def last_assistant_turn(self) -> ConversationTurn | None:
        with self._lock:
            for turn in reversed(self._turns):
                if turn.role == "assistant":
                    return turn
        return None

    def build_context_block(
        self,
        *,
        limit: int | None = None,
        preferred_language: str | None = None,
        include_timestamps: bool = False,
    ) -> str:
        turns = self.get_recent_turns(limit=limit)
        if not turns:
            return ""

        normalized_preferred_language = (
            self._normalize_language(preferred_language)
            if preferred_language
            else None
        )

        lines: list[str] = []

        for turn in turns:
            context_text = self._context_text_for_turn(turn)
            if not context_text:
                continue

            role_label = "User" if turn.role == "user" else "Assistant"
            if normalized_preferred_language and turn.language != normalized_preferred_language:
                role_label = f"{role_label} ({turn.language})"

            if include_timestamps:
                lines.append(f"[{turn.created_at_iso}] {role_label}: {context_text}")
            else:
                lines.append(f"{role_label}: {context_text}")

        return "\n".join(lines).strip()

    def build_context_payload(
        self,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []

        for turn in self.get_recent_turns(limit=limit):
            context_text = self._context_text_for_turn(turn)
            if not context_text:
                continue

            payload.append(
                {
                    "role": turn.role,
                    "text": context_text,
                    "language": turn.language,
                    "created_at_iso": turn.created_at_iso,
                    "metadata": dict(turn.metadata),
                }
            )

        return payload

    def summary_for_prompt(
        self,
        *,
        limit: int | None = None,
        preferred_language: str | None = None,
    ) -> str:
        """
        Slightly stricter alias for prompt-building code.
        """
        return self.build_context_block(
            limit=limit,
            preferred_language=preferred_language,
            include_timestamps=False,
        )

    # ------------------------------------------------------------------
    # Internal trimming
    # ------------------------------------------------------------------

    def _trim_locked(self) -> None:
        if not self._turns:
            return

        while len(self._turns) > self.max_turns:
            self._turns.pop(0)

        while self._estimate_total_chars_locked() > self.max_total_chars and len(self._turns) > 1:
            self._turns.pop(0)

    def _estimate_total_chars_locked(self) -> int:
        return sum(
            len(turn.text) + len(turn.role) + len(turn.language)
            for turn in self._turns
        )

    def _is_consecutive_duplicate(self, turn: ConversationTurn) -> bool:
        if not self._turns:
            return False

        last = self._turns[-1]
        return (
            last.role == turn.role
            and last.language == turn.language
            and self._normalize_for_compare(last.text) == self._normalize_for_compare(turn.text)
        )

    # ------------------------------------------------------------------
    # Context filtering
    # ------------------------------------------------------------------

    def _context_text_for_turn(self, turn: ConversationTurn) -> str:
        text = self._clean_text(turn.text, max_chars=self.max_turn_chars)
        if not text:
            return ""

        source = str(turn.metadata.get("source", "")).strip().lower()
        route_kind = str(turn.metadata.get("route_kind", "")).strip().lower()
        phase = str(turn.metadata.get("phase", "")).strip().lower()

        if source in {"system_boot", "system_shutdown"}:
            return ""

        if source == "system" and route_kind in {"system_boot", "startup"}:
            return ""

        if phase in {"retry_yes_no", "reprompt_silence"}:
            return ""

        if route_kind in {"timer_started", "timer_stopped"} and turn.role == "assistant":
            return text

        if phase == "reprompt":
            return text

        return text

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(text: str, *, max_chars: int) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return ""

        if len(cleaned) <= max_chars:
            return cleaned

        shortened = cleaned[:max_chars].rstrip()
        if shortened.endswith((" ", ".", ",", ";", ":")):
            shortened = shortened.rstrip(" .,:;")

        return f"{shortened}..."

    @staticmethod
    def _normalize_for_compare(text: str) -> str:
        return " ".join(str(text or "").lower().split()).strip()

    @staticmethod
    def _normalize_role(role: str | None) -> str:
        return str(role or "").strip().lower()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized.startswith("pl"):
            return "pl"
        return "en"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "ConversationMemory",
    "ConversationTurn",
]