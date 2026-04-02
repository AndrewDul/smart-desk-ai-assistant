from __future__ import annotations

from modules.system.utils import append_log


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


def handle_memory_list(assistant, lang: str) -> bool:
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
        assistant._speak_localized(
            lang,
            "Na razie niczego nie zapamiętałam.",
            "I have not remembered anything yet.",
        )
        return True

    items = list(all_memory.items())
    lines: list[str] = [_memory_count_line(len(items), lang)]

    for key, value in items[:2]:
        lines.append(_short_text(key, limit=20))
        lines.append(_short_text(value, limit=20))

    assistant.display.show_block(
        assistant._localized(lang, "PAMIĘĆ", "MEMORY"),
        lines[:4],
        duration=assistant.default_overlay_seconds,
    )

    assistant._speak_localized(
        lang,
        f"Mam zapisane {_memory_count_line(len(items), 'pl')}.",
        f"I have {_memory_count_line(len(items), 'en')} saved in memory.",
    )
    return True


def handle_memory_clear(assistant, lang: str) -> bool:
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
        assistant._speak_localized(
            lang,
            "Pamięć jest już pusta.",
            "Memory is already empty.",
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

    assistant._speak_localized(
        lang,
        "Czy na pewno mam wyczyścić całą pamięć?",
        "Are you sure I should clear all memory?",
    )
    return True


def handle_memory_store(assistant, result, lang: str) -> bool:
    key = str(result.data.get("key", "")).strip().lower()
    value = str(result.data.get("value", "")).strip()
    memory_text = str(result.data.get("memory_text", "")).strip()

    if key and value:
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

        assistant._speak_localized(
            lang,
            f"Dobrze. Zapamiętałam, że {key} jest {value}.",
            f"Okay. I remembered that {key} is {value}.",
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

        assistant._speak_localized(
            lang,
            "Dobrze. Zapamiętałam tę informację.",
            "Okay. I remembered that information.",
        )
        return True

    assistant._speak_localized(
        lang,
        "Nie usłyszałam, co mam zapamiętać.",
        "I did not catch what I should remember.",
    )
    return True


def handle_memory_recall(assistant, result, lang: str) -> bool:
    key = str(result.data["key"]).strip().lower()
    value = assistant.memory.recall(key)

    if value is None:
        assistant._show_localized_block(
            lang,
            "PAMIĘĆ",
            "MEMORY",
            [
                _short_text(key, limit=22),
                assistant._localized(lang, "brak wyniku", "not found"),
            ],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            f"Nie mam zapisanej informacji dla {key}.",
            f"I do not have anything saved for {key}.",
        )
        return True

    assistant._speak_localized(
        lang,
        f"{key} jest {value}.",
        f"{key} is {value}.",
    )

    assistant._offer_oled_display(
        lang,
        assistant._localized(lang, "ODPOWIEDŹ", "ANSWER"),
        [f"{key}: {value}"],
        speak_prompt=False,
    )
    return True


def handle_memory_forget(assistant, result, lang: str) -> bool:
    key = str(result.data["key"]).strip().lower()
    value = assistant.memory.recall(key)

    if value is None:
        assistant._show_localized_block(
            lang,
            "PAMIĘĆ",
            "MEMORY",
            [
                _short_text(key, limit=22),
                assistant._localized(lang, "brak wyniku", "not found"),
            ],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            f"Nie mam zapisanej informacji dla {key}.",
            f"I do not have anything saved for {key}.",
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

    assistant._speak_localized(
        lang,
        f"Czy na pewno mam usunąć z pamięci {key}?",
        f"Are you sure I should remove {key} from memory?",
    )
    return True