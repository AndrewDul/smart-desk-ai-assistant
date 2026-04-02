from __future__ import annotations

from modules.core.handlers_memory import (
    handle_memory_clear,
    handle_memory_forget,
    handle_memory_list,
    handle_memory_recall,
    handle_memory_store,
)
from modules.core.handlers_reminders import (
    handle_reminder_create,
    handle_reminder_delete,
    handle_reminders_clear,
    handle_reminders_list,
)
from modules.core.handlers_system import (
    handle_exit,
    handle_help,
    handle_introduce_self,
    handle_shutdown,
    handle_status,
)
from modules.core.handlers_time import handle_temporal_intent
from modules.core.handlers_timers import (
    handle_break_start,
    handle_focus_start,
    handle_timer_start,
    handle_timer_stop,
)


TEMPORAL_ACTIONS = {
    "ask_time",
    "show_time",
    "ask_date",
    "show_date",
    "ask_day",
    "show_day",
    "ask_year",
    "show_year",
}


def dispatch_intent(assistant, result, lang: str) -> bool | None:
    action = result.action

    if action == "help":
        return handle_help(assistant, lang)

    if action == "introduce_self":
        return handle_introduce_self(assistant, lang)

    if action in TEMPORAL_ACTIONS:
        return handle_temporal_intent(assistant, result, lang)

    if action == "status":
        return handle_status(assistant, lang)

    if action == "memory_list":
        return handle_memory_list(assistant, lang)

    if action == "memory_clear":
        return handle_memory_clear(assistant, lang)

    if action == "memory_store":
        return handle_memory_store(assistant, result, lang)

    if action == "memory_recall":
        return handle_memory_recall(assistant, result, lang)

    if action == "memory_forget":
        return handle_memory_forget(assistant, result, lang)

    if action == "reminders_list":
        return handle_reminders_list(assistant, lang)

    if action == "reminder_delete":
        return handle_reminder_delete(assistant, result, lang)

    if action == "reminders_clear":
        return handle_reminders_clear(assistant, lang)

    if action == "reminder_create":
        return handle_reminder_create(assistant, result, lang)

    if action == "timer_start":
        return handle_timer_start(assistant, result, lang)

    if action == "focus_start":
        return handle_focus_start(assistant, result, lang)

    if action == "break_start":
        return handle_break_start(assistant, result, lang)

    if action == "timer_stop":
        return handle_timer_stop(assistant, lang)

    if action == "exit":
        return handle_exit(assistant, lang)

    if action == "shutdown":
        return handle_shutdown(assistant, lang)

    return None