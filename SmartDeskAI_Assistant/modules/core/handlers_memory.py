from __future__ import annotations

import re

from modules.system.utils import append_log


_WEAK_SINGLE_TOKENS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "do",
    "for",
    "from",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "under",
    "with",
    "i",
    "me",
    "you",
    "w",
    "na",
    "pod",
    "przy",
    "obok",
    "do",
    "od",
    "u",
    "i",
    "a",
    "to",
    "jest",
    "sa",
    "moj",
    "moja",
    "moje",
    "mi",
    "mnie",
    "ze",
}

_WEAK_ENDINGS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "under",
    "with",
    "w",
    "na",
    "pod",
    "przy",
    "obok",
    "do",
    "od",
    "u",
    "jest",
    "sa",
    "ze",
}

_MEMORY_FILLER_PREFIXES = (
    "that ",
    "to ",
    "about ",
    "o ",
    "ze ",
)

_MEMORY_FILLER_SUFFIXES = (
    " please",
    " prosze",
)


def _remember_memory_reply(
    assistant,
    *,
    spoken: str,
    lang: str,
    action: str,
    extra_metadata: dict | None = None,
) -> None:
    if not hasattr(assistant, "_remember_assistant_turn"):
        return

    cleaned = " ".join(str(spoken or "").split()).strip()
    if not cleaned:
        return

    metadata = {
        "source": "memory_handler",
        "route_kind": "action",
        "action": action,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    assistant._remember_assistant_turn(
        cleaned,
        language=lang,
        metadata=metadata,
    )


def _speak_and_remember_localized(
    assistant,
    lang: str,
    pl_text: str,
    en_text: str,
    *,
    action: str,
    extra_metadata: dict | None = None,
) -> None:
    assistant._speak_localized(lang, pl_text, en_text)
    spoken = assistant._localized(lang, pl_text, en_text)
    _remember_memory_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action=action,
        extra_metadata=extra_metadata,
    )


def _short_text(text: str, limit: int = 22) -> str:
    cleaned = " ".join(str(text).strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _memory_count_line(count: int, lang: str) -> str:
    if lang == "pl":
        if count == 1:
            return "1 wpis"
        if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
            return f"{count} wpisy"
        return f"{count} wpisów"

    return f"{count} item" if count == 1 else f"{count} items"


def _normalize_for_validation(assistant, text: str) -> str:
    normalized = assistant._normalize_text(str(text or "").strip())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _strip_memory_fillers(text: str) -> str:
    cleaned = " ".join(str(text or "").strip().split())

    changed = True
    while changed and cleaned:
        changed = False
        lowered = cleaned.lower()

        for prefix in _MEMORY_FILLER_PREFIXES:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
                break

        lowered = cleaned.lower()
        for suffix in _MEMORY_FILLER_SUFFIXES:
            if lowered.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()
                changed = True
                break

    return cleaned


def _looks_like_truncated_fragment(assistant, text: str) -> bool:
    normalized = _normalize_for_validation(assistant, text)
    if not normalized:
        return True

    tokens = normalized.split()
    if not tokens:
        return True

    if len(tokens) == 1 and tokens[0] in _WEAK_SINGLE_TOKENS:
        return True

    if tokens[-1] in _WEAK_ENDINGS:
        return True

    if len(normalized) <= 2:
        return True

    if len(tokens) == 1 and len(tokens[0]) <= 2:
        return True

    return False


def _clean_memory_key(assistant, key: str) -> str:
    cleaned = _strip_memory_fillers(key)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    normalized = _normalize_for_validation(assistant, cleaned)

    if not normalized:
        return ""

    if normalized in _WEAK_SINGLE_TOKENS:
        return ""

    return cleaned


def _clean_memory_value(assistant, value: str) -> str:
    cleaned = _strip_memory_fillers(value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if _looks_like_truncated_fragment(assistant, cleaned):
        return ""

    return cleaned


def _clean_memory_text(assistant, memory_text: str) -> str:
    cleaned = _strip_memory_fillers(memory_text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    normalized = _normalize_for_validation(assistant, cleaned)
    if not normalized:
        return ""

    tokens = normalized.split()
    if len(tokens) < 2:
        return ""

    if tokens[-1] in _WEAK_ENDINGS:
        return ""

    return cleaned


def _memory_save_failed_reply(assistant, lang: str) -> bool:
    _speak_and_remember_localized(
        assistant,
        lang,
        "Nie zapisałam tego, bo zdanie wygląda na ucięte. Powiedz to jeszcze raz spokojnie.",
        "I did not save that because the sentence looks cut off. Please say it again clearly.",
        action="memory_store",
        extra_metadata={"phase": "save_rejected"},
    )
    return True


def handle_memory_list(assistant, lang: str) -> bool:
    assistant.pending_follow_up = None

    all_memory = assistant.memory.get_all()

    if not all_memory:
        assistant._show_localized_block(
            lang,
            "PAMIĘĆ",
            "MEMORY",
            ["pamiec jest pusta"],
            ["memory is empty"],
            duration=6.0,
        )
        _speak_and_remember_localized(
            assistant,
            lang,
            "Na razie niczego nie zapamiętałam.",
            "I have not remembered anything yet.",
            action="memory_list",
            extra_metadata={"count": 0},
        )
        return True

    items = list(all_memory.items())
    lines_pl: list[str] = [_memory_count_line(len(items), "pl")]
    lines_en: list[str] = [_memory_count_line(len(items), "en")]

    for key, value in items[:2]:
        lines_pl.append(_short_text(key, limit=20))
        lines_pl.append(_short_text(value, limit=20))
        lines_en.append(_short_text(key, limit=20))
        lines_en.append(_short_text(value, limit=20))

    assistant._show_localized_block(
        lang,
        "PAMIĘĆ",
        "MEMORY",
        lines_pl[:4],
        lines_en[:4],
        duration=assistant.default_overlay_seconds,
    )

    _speak_and_remember_localized(
        assistant,
        lang,
        f"Mam zapisane {_memory_count_line(len(items), 'pl')}.",
        f"I have {_memory_count_line(len(items), 'en')} saved in memory.",
        action="memory_list",
        extra_metadata={"count": len(items)},
    )
    return True


def handle_memory_clear(assistant, lang: str) -> bool:
    assistant.pending_follow_up = None

    all_memory = assistant.memory.get_all()

    if not all_memory:
        assistant._show_localized_block(
            lang,
            "PAMIĘĆ",
            "MEMORY",
            ["pamiec jest pusta"],
            ["memory is already empty"],
            duration=6.0,
        )
        _speak_and_remember_localized(
            assistant,
            lang,
            "Pamięć jest już pusta.",
            "Memory is already empty.",
            action="memory_clear",
            extra_metadata={"phase": "already_empty"},
        )
        return True

    count = len(all_memory)

    assistant.pending_follow_up = {
        "type": "confirm_memory_clear",
        "lang": lang,
    }

    assistant.display.show_block(
        assistant._localized(lang, "WYCZYŚCIĆ PAMIĘĆ?", "CLEAR MEMORY?"),
        [
            assistant._localized(lang, f"wpisy: {count}", f"items: {count}"),
            assistant._localized(lang, "powiedz tak lub nie", "say yes or no"),
        ],
        duration=8.0,
    )

    _speak_and_remember_localized(
        assistant,
        lang,
        "Czy na pewno mam wyczyścić całą pamięć?",
        "Are you sure I should clear all memory?",
        action="memory_clear",
        extra_metadata={"phase": "confirmation_request", "count": count},
    )
    return True


def handle_memory_store(assistant, result, lang: str) -> bool:
    assistant.pending_follow_up = None

    raw_key = str(result.data.get("key", "")).strip()
    raw_value = str(result.data.get("value", "")).strip()
    raw_memory_text = str(result.data.get("memory_text", "")).strip()

    key = _clean_memory_key(assistant, raw_key)
    value = _clean_memory_value(assistant, raw_value)
    memory_text = _clean_memory_text(assistant, raw_memory_text)

    if raw_key or raw_value:
        if not key or not value:
            append_log(
                f"Memory save rejected: suspicious structured fragment | raw_key='{raw_key}' raw_value='{raw_value}'"
            )
            return _memory_save_failed_reply(assistant, lang)

        assistant.memory.remember(key, value)
        append_log(f"Memory stored from structured input: {key} -> {value}")

        assistant.display.show_block(
            assistant._localized(lang, "PAMIĘĆ ZAPISANA", "MEMORY SAVED"),
            [
                _short_text(key, limit=20),
                _short_text(value, limit=20),
            ],
            duration=8.0,
        )

        _speak_and_remember_localized(
            assistant,
            lang,
            f"Dobrze. Zapamiętałam, że {key} jest {value}.",
            f"Okay. I remembered that {key} is {value}.",
            action="memory_store",
            extra_metadata={
                "mode": "structured",
                "key": key,
                "value": value,
            },
        )
        return True

    if memory_text:
        assistant.memory.remember(memory_text, memory_text)
        append_log(f"Memory stored from free text: {memory_text}")

        assistant.display.show_block(
            assistant._localized(lang, "PAMIĘĆ ZAPISANA", "MEMORY SAVED"),
            [
                _short_text(memory_text, limit=24),
            ],
            duration=8.0,
        )

        _speak_and_remember_localized(
            assistant,
            lang,
            "Dobrze. Zapamiętałam tę informację.",
            "Okay. I remembered that information.",
            action="memory_store",
            extra_metadata={
                "mode": "free_text",
                "memory_text": memory_text,
            },
        )
        return True

    append_log(
        f"Memory save rejected: empty or suspicious free text | raw_memory_text='{raw_memory_text}'"
    )
    return _memory_save_failed_reply(assistant, lang)


def handle_memory_recall(assistant, result, lang: str) -> bool:
    assistant.pending_follow_up = None

    raw_key = str(result.data["key"]).strip()
    key = _clean_memory_key(assistant, raw_key)

    if not key:
        _speak_and_remember_localized(
            assistant,
            lang,
            "Nie usłyszałam wyraźnie, o co pytasz w pamięci.",
            "I did not clearly catch what you want to recall from memory.",
            action="memory_recall",
            extra_metadata={"phase": "unclear_key"},
        )
        return True

    value = assistant.memory.recall(key)

    if value is None:
        assistant._show_localized_block(
            lang,
            "PAMIĘĆ",
            "MEMORY",
            [
                _short_text(key, limit=22),
                "brak wyniku",
            ],
            [
                _short_text(key, limit=22),
                "not found",
            ],
            duration=6.0,
        )
        _speak_and_remember_localized(
            assistant,
            lang,
            f"Nie mam zapisanej informacji dla {key}.",
            f"I do not have anything saved for {key}.",
            action="memory_recall",
            extra_metadata={"phase": "not_found", "key": key},
        )
        return True

    assistant.display.show_block(
        assistant._localized(lang, "PAMIĘĆ", "MEMORY"),
        [
            _short_text(key, limit=20),
            _short_text(value, limit=20),
        ],
        duration=6.0,
    )

    _speak_and_remember_localized(
        assistant,
        lang,
        f"{key} jest {value}.",
        f"{key} is {value}.",
        action="memory_recall",
        extra_metadata={"phase": "found", "key": key, "value": value},
    )
    return True


def handle_memory_forget(assistant, result, lang: str) -> bool:
    assistant.pending_follow_up = None

    raw_key = str(result.data["key"]).strip()
    key = _clean_memory_key(assistant, raw_key)

    if not key:
        _speak_and_remember_localized(
            assistant,
            lang,
            "Nie usłyszałam wyraźnie, co mam usunąć z pamięci.",
            "I did not clearly catch what I should remove from memory.",
            action="memory_forget",
            extra_metadata={"phase": "unclear_key"},
        )
        return True

    value = assistant.memory.recall(key)

    if value is None:
        assistant._show_localized_block(
            lang,
            "PAMIĘĆ",
            "MEMORY",
            [
                _short_text(key, limit=22),
                "brak wyniku",
            ],
            [
                _short_text(key, limit=22),
                "not found",
            ],
            duration=6.0,
        )
        _speak_and_remember_localized(
            assistant,
            lang,
            f"Nie mam zapisanej informacji dla {key}.",
            f"I do not have anything saved for {key}.",
            action="memory_forget",
            extra_metadata={"phase": "not_found", "key": key},
        )
        return True

    assistant.pending_follow_up = {
        "type": "confirm_memory_forget",
        "lang": lang,
        "key": key,
    }

    assistant.display.show_block(
        assistant._localized(lang, "USUNĄĆ Z PAMIĘCI?", "REMOVE FROM MEMORY?"),
        [
            _short_text(key, limit=20),
            _short_text(value, limit=20),
        ],
        duration=8.0,
    )

    _speak_and_remember_localized(
        assistant,
        lang,
        f"Czy na pewno mam usunąć z pamięci {key}?",
        f"Are you sure I should remove {key} from memory?",
        action="memory_forget",
        extra_metadata={"phase": "confirmation_request", "key": key, "value": value},
    )
    return True