from __future__ import annotations

import re
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


@dataclass(slots=True)
class ConversationState:
    last_topic: str = ""
    last_route_kind: str = ""
    last_user_goal: str = ""
    last_emotional_signal: str = ""
    pending_question: str = ""
    preferred_language: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_topic": self.last_topic,
            "last_route_kind": self.last_route_kind,
            "last_user_goal": self.last_user_goal,
            "last_emotional_signal": self.last_emotional_signal,
            "pending_question": self.pending_question,
            "preferred_language": self.preferred_language,
        }


class ConversationMemory:
    """
    Lightweight short-term conversation memory for NeXa.

    Goals:
    - keep recent context compact and useful
    - avoid low-value repetition
    - provide stable context blocks for prompt building
    - keep a tiny conversation state for better continuity
    - stay deterministic and fast on Raspberry Pi
    """

    _QUESTION_RE = re.compile(r"[?]")

    _LOW_VALUE_ASSISTANT_TEXTS = {
        "okay.",
        "ok.",
        "sure.",
        "jasne.",
        "dobrze.",
        "okej.",
        "oczywiście.",
        "i am here.",
        "jestem tutaj.",
    }

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
        self._state = ConversationState()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._state = ConversationState()

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
            self._update_state_locked(turn)

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

    def conversation_state(self) -> dict[str, Any]:
        with self._lock:
            return self._state.to_dict()

    def build_state_summary(
        self,
        *,
        preferred_language: str | None = None,
    ) -> str:
        with self._lock:
            state = self._state.to_dict()

        lang = self._normalize_language(preferred_language or state.get("preferred_language"))
        parts: list[str] = []

        if state["last_topic"]:
            parts.append(
                self._localized(
                    lang,
                    f"Ostatni temat: {state['last_topic']}.",
                    f"Last topic: {state['last_topic']}.",
                )
            )

        if state["last_user_goal"]:
            parts.append(
                self._localized(
                    lang,
                    f"Cel użytkownika: {state['last_user_goal']}.",
                    f"User goal: {state['last_user_goal']}.",
                )
            )

        if state["last_emotional_signal"]:
            parts.append(
                self._localized(
                    lang,
                    f"Sygnał emocjonalny: {state['last_emotional_signal']}.",
                    f"Emotional signal: {state['last_emotional_signal']}.",
                )
            )

        if state["pending_question"]:
            parts.append(
                self._localized(
                    lang,
                    f"Otwarta kwestia: {state['pending_question']}.",
                    f"Open thread: {state['pending_question']}.",
                )
            )

        return " ".join(part.strip() for part in parts if part.strip()).strip()

    def build_context_block(
        self,
        *,
        limit: int | None = None,
        preferred_language: str | None = None,
        include_timestamps: bool = False,
        include_state_summary: bool = True,
    ) -> str:
        turns = self.get_recent_turns(limit=limit)
        if not turns and not include_state_summary:
            return ""

        normalized_preferred_language = (
            self._normalize_language(preferred_language)
            if preferred_language
            else None
        )

        lines: list[str] = []

        if include_state_summary:
            state_summary = self.build_state_summary(
                preferred_language=normalized_preferred_language,
            )
            if state_summary:
                prefix = "Context" if normalized_preferred_language != "pl" else "Kontekst"
                lines.append(f"{prefix}: {state_summary}")

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

        return "\n".join(line for line in lines if line.strip()).strip()

    def build_context_payload(
        self,
        *,
        limit: int | None = None,
        include_state: bool = True,
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []

        if include_state:
            state = self.conversation_state()
            if any(str(value).strip() for value in state.values()):
                payload.append(
                    {
                        "role": "system_context",
                        "text": self.build_state_summary(
                            preferred_language=state.get("preferred_language", "en")
                        ),
                        "language": state.get("preferred_language", "en"),
                        "created_at_iso": self._now_iso(),
                        "metadata": {"state": state},
                    }
                )

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
        return self.build_context_block(
            limit=limit,
            preferred_language=preferred_language,
            include_timestamps=False,
            include_state_summary=True,
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

    def _update_state_locked(self, turn: ConversationTurn) -> None:
        self._state.preferred_language = turn.language

        route_kind = str(turn.metadata.get("route_kind", "") or "").strip().lower()
        if route_kind:
            self._state.last_route_kind = route_kind

        topics = turn.metadata.get("topics") or turn.metadata.get("conversation_topics") or []
        if isinstance(topics, list):
            normalized_topics = [str(item).strip() for item in topics if str(item).strip()]
            if normalized_topics:
                self._state.last_topic = normalized_topics[0]

        if turn.role == "user":
            inferred_goal = self._infer_user_goal(turn)
            if inferred_goal:
                self._state.last_user_goal = inferred_goal

            inferred_emotion = self._infer_emotional_signal(turn.text)
            if inferred_emotion:
                self._state.last_emotional_signal = inferred_emotion

            if self._looks_like_question(turn.text):
                self._state.pending_question = self._clean_text(
                    turn.text,
                    max_chars=120,
                )
            elif self._state.pending_question and not self._looks_like_follow_up_ack(turn.text):
                # A new non-trivial user message can replace the old open thread.
                self._state.pending_question = self._clean_text(
                    turn.text,
                    max_chars=120,
                )

        elif turn.role == "assistant":
            if self._looks_like_answer(turn.text):
                self._state.pending_question = ""

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

        if turn.role == "assistant" and self._is_low_value_assistant_turn(text=text, source=source):
            return ""

        if route_kind in {"timer_started", "timer_stopped"} and turn.role == "assistant":
            return text

        if phase == "reprompt":
            return text

        return text

    # ------------------------------------------------------------------
    # State heuristics
    # ------------------------------------------------------------------

    def _infer_user_goal(self, turn: ConversationTurn) -> str:
        topics = turn.metadata.get("topics") or turn.metadata.get("conversation_topics") or []
        if isinstance(topics, list):
            normalized_topics = [str(item).strip() for item in topics if str(item).strip()]
            if normalized_topics:
                return normalized_topics[0]

        route_kind = str(turn.metadata.get("route_kind", "") or "").strip().lower()
        if route_kind:
            return route_kind

        lowered = self._normalize_for_compare(turn.text)

        if any(marker in lowered for marker in ("remember", "zapamietaj", "zapamiętaj")):
            return "memory"
        if any(marker in lowered for marker in ("timer", "focus", "break", "przerwa", "skup")):
            return "time_management"
        if self._looks_like_question(turn.text):
            return "knowledge_or_clarification"

        return ""

    @classmethod
    def _infer_emotional_signal(cls, text: str) -> str:
        lowered = cls._normalize_for_compare(text)

        if any(marker in lowered for marker in ("zmecz", "zmęcz", "tired", "exhausted")):
            return "tired"
        if any(marker in lowered for marker in ("stres", "stress", "overwhelmed", "przytlocz", "przytłocz")):
            return "overwhelmed"
        if any(marker in lowered for marker in ("nie wiem", "i do not know", "i don't know", "unsure")):
            return "unsure"
        if any(marker in lowered for marker in ("focus", "concentrat", "skup", "rozprasza")):
            return "focus_struggle"

        return ""

    @classmethod
    def _looks_like_question(cls, text: str) -> bool:
        cleaned = str(text or "").strip()
        if not cleaned:
            return False

        lowered = cls._normalize_for_compare(cleaned)
        if cls._QUESTION_RE.search(cleaned):
            return True

        starters = (
            "what",
            "why",
            "how",
            "when",
            "where",
            "who",
            "czy",
            "jak",
            "dlaczego",
            "kiedy",
            "gdzie",
            "co",
            "kto",
        )
        return lowered.startswith(starters)

    @classmethod
    def _looks_like_follow_up_ack(cls, text: str) -> bool:
        lowered = cls._normalize_for_compare(text)
        return lowered in {
            "ok",
            "okay",
            "yes",
            "no",
            "tak",
            "nie",
            "jasne",
            "okej",
            "dobrze",
        }

    @classmethod
    def _looks_like_answer(cls, text: str) -> bool:
        lowered = cls._normalize_for_compare(text)
        if not lowered:
            return False

        if len(lowered) >= 16:
            return True

        return lowered.endswith((".", "!", "?"))

    @classmethod
    def _is_low_value_assistant_turn(cls, *, text: str, source: str) -> bool:
        normalized = cls._normalize_for_compare(text)
        if normalized in {cls._normalize_for_compare(item) for item in cls._LOW_VALUE_ASSISTANT_TEXTS}:
            return True

        if source in {"ack", "listening_ack"} and len(normalized) <= 24:
            return True

        return False

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
    def _localized(language: str, pl_text: str, en_text: str) -> str:
        return pl_text if str(language).lower().startswith("pl") else en_text

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "ConversationMemory",
    "ConversationState",
    "ConversationTurn",
]