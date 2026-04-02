from __future__ import annotations

from modules.core.language import localized


def handle_memory_list(assistant, lang: str) -> bool:
    all_memory = assistant.memory.get_all()
    if not all_memory:
        assistant._speak_localized(
            lang,
            "Na razie niczego nie zapamiętałam.",
            "I have not remembered anything yet.",
        )
        return True

    memory_lines = [f"{key} -> {value}" for key, value in list(all_memory.items())[:5]]
    assistant.display.show_block(
        assistant._localized(lang, "PAMIĘĆ", "MEMORY"),
        memory_lines,
        duration=assistant.default_overlay_seconds,
    )
    assistant._speak_localized(
        lang,
        "Pokazuję zapisane rzeczy.",
        "I am showing the saved items.",
    )
    return True


def handle_memory_clear(assistant, lang: str) -> bool:
    all_memory = assistant.memory.get_all()
    if not all_memory:
        assistant._speak_localized(
            lang,
            "Pamięć jest już pusta.",
            "Memory is already empty.",
        )
        return True

    assistant.pending_follow_up = {
        "type": "confirm_memory_clear",
        "lang": lang,
    }
    assistant.display.show_block(
        assistant._localized(lang, "WYCZYŚCIĆ PAMIĘĆ?", "CLEAR MEMORY?"),
        [assistant._localized(lang, f"wpisy: {len(all_memory)}", f"items: {len(all_memory)}")],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        "Czy na pewno mam wyczyścić całą pamięć?",
        "Are you sure I should clear all memory?",
    )
    return True


def handle_memory_store(assistant, result, lang: str) -> bool:
    key = result.data.get("key", "").strip().lower()
    value = result.data.get("value", "").strip()
    memory_text = result.data.get("memory_text", "").strip()

    if key and value:
        assistant.memory.remember(key, value)
        spoken_pl = f"Dobrze. Zapamiętałam, że {key} jest {value}."
        spoken_en = f"Okay. I remembered that {key} is {value}."
        title = assistant._localized(lang, "PAMIĘĆ", "MEMORY")
        lines = [key, value]
    elif memory_text:
        assistant.memory.remember(memory_text, memory_text)
        spoken_pl = "Dobrze. Zapamiętałam tę informację."
        spoken_en = "Okay. I remembered that information."
        title = assistant._localized(lang, "PAMIĘĆ", "MEMORY")
        lines = [memory_text]
    else:
        assistant._speak_localized(
            lang,
            "Nie usłyszałam, co mam zapamiętać.",
            "I did not catch what I should remember.",
        )
        return True

    assistant.voice_out.speak(localized(lang, spoken_pl, spoken_en), language=lang)
    assistant.display.show_block(title, lines, duration=8.0)
    return True


def handle_memory_recall(assistant, result, lang: str) -> bool:
    key = result.data["key"].strip().lower()
    value = assistant.memory.recall(key)

    if value is None:
        assistant._speak_localized(
            lang,
            f"Nie mam zapisanej informacji dla {key}.",
            f"I do not have anything saved for {key}.",
        )
        return True

    answer = assistant._localized(lang, f"{key} jest {value}.", f"{key} is {value}.")
    assistant.voice_out.speak(answer, language=lang)
    assistant._offer_oled_display(
        lang,
        assistant._localized(lang, "ODPOWIEDŹ", "ANSWER"),
        [f"{key}: {value}"],
        speak_prompt=False,
    )
    return True


def handle_memory_forget(assistant, result, lang: str) -> bool:
    key = result.data["key"].strip().lower()
    value = assistant.memory.recall(key)

    if value is None:
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
        assistant._localized(lang, "USUNĄĆ?", "DELETE?"),
        [key, value],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        f"Czy na pewno mam usunąć z pamięci {key}?",
        f"Are you sure I should remove {key} from memory?",
    )
    return True