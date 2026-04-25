from __future__ import annotations

from random import SystemRandom

from modules.presentation.visual_shell.controller.voice_command_router import VisualVoiceAction

_RANDOM = SystemRandom()


_RESPONSES: dict[str, dict[VisualVoiceAction, tuple[str, ...]]] = {
    "pl": {
        VisualVoiceAction.SHOW_TEMPERATURE: (
            "Wyświetlam temperaturę.",
            "Pokazuję temperaturę.",
            "Już pokazuję temperaturę.",
            "Temperatura jest na ekranie.",
        ),
        VisualVoiceAction.SHOW_BATTERY: (
            "Wyświetlam stan baterii.",
            "Pokazuję baterię.",
            "Już pokazuję poziom baterii.",
            "Stan baterii jest na ekranie.",
        ),
        VisualVoiceAction.SHOW_DESKTOP: (
            "Pokazuję pulpit.",
            "Pulpit jest dostępny.",
            "Odsłaniam pulpit.",
            "Przechodzę do trybu pulpitu.",
        ),
        VisualVoiceAction.HIDE_DESKTOP: (
            "Schowano pulpit.",
            "Wracam do pełnego ekranu NEXA.",
            "Zasłaniam pulpit.",
            "Pulpit jest schowany.",
        ),
        VisualVoiceAction.SHOW_SELF: (
            "Pokazuję się.",
            "Jestem tutaj.",
            "Pokazuję swoją twarz.",
            "Już się pokazuję.",
        ),
        VisualVoiceAction.SHOW_EYES: (
            "Pokazuję oczy.",
            "Już pokazuję oczy.",
            "Oczy są na ekranie.",
            "Patrzę spokojnie.",
        ),
        VisualVoiceAction.LOOK_AT_USER: (
            "Patrzę na Ciebie.",
            "Już patrzę.",
            "Jestem skupiona na Tobie.",
            "Patrzę spokojnie.",
        ),
        VisualVoiceAction.SHOW_FACE_CONTOUR: (
            "Pokazuję kontur twarzy.",
            "Formuję twarz.",
            "Już pokazuję kontur.",
            "Kontur twarzy jest na ekranie.",
        ),
        VisualVoiceAction.START_SCANNING: (
            "Rozglądam się.",
            "Skanuję otoczenie.",
            "Sprawdzam otoczenie.",
            "Uruchamiam tryb obserwacji.",
        ),
        VisualVoiceAction.RETURN_TO_IDLE: (
            "Wracam do trybu spoczynku.",
            "Wracam do spokojnego trybu.",
            "Gotowe.",
            "Wracam do chmury.",
        ),
    },
    "en": {
        VisualVoiceAction.SHOW_TEMPERATURE: (
            "Showing temperature.",
            "Displaying the temperature.",
            "I am showing the temperature now.",
            "The temperature is on screen.",
        ),
        VisualVoiceAction.SHOW_BATTERY: (
            "Showing battery status.",
            "Displaying the battery level.",
            "I am showing the battery now.",
            "Battery status is on screen.",
        ),
        VisualVoiceAction.SHOW_DESKTOP: (
            "Showing desktop.",
            "Desktop is available.",
            "I am revealing the desktop.",
            "Switching to desktop mode.",
        ),
        VisualVoiceAction.HIDE_DESKTOP: (
            "Desktop hidden.",
            "Returning to full screen.",
            "I am hiding the desktop.",
            "NEXA is back in full screen.",
        ),
        VisualVoiceAction.SHOW_SELF: (
            "Showing myself.",
            "I am here.",
            "Showing my face.",
            "I am appearing now.",
        ),
        VisualVoiceAction.SHOW_EYES: (
            "Showing eyes.",
            "My eyes are on screen.",
            "I am showing my eyes now.",
            "Looking calmly.",
        ),
        VisualVoiceAction.LOOK_AT_USER: (
            "I am looking at you.",
            "Looking at you now.",
            "I am focused on you.",
            "I am watching calmly.",
        ),
        VisualVoiceAction.SHOW_FACE_CONTOUR: (
            "Showing face contour.",
            "Forming the face contour.",
            "The face contour is on screen.",
            "I am showing the face outline.",
        ),
        VisualVoiceAction.START_SCANNING: (
            "Looking around.",
            "Scanning the room.",
            "Checking the environment.",
            "Observation mode is active.",
        ),
        VisualVoiceAction.RETURN_TO_IDLE: (
            "Returning to idle.",
            "Back to calm mode.",
            "Done.",
            "Returning to the cloud.",
        ),
    },
}


def choose_visual_shell_response(
    action: VisualVoiceAction,
    *,
    language: str,
) -> str:
    normalized_language = _normalize_language(language)
    responses = _RESPONSES.get(normalized_language, _RESPONSES["en"])
    options = responses.get(action)

    if not options:
        fallback = _RESPONSES[normalized_language][VisualVoiceAction.RETURN_TO_IDLE]
        return _RANDOM.choice(fallback)

    return _RANDOM.choice(options)


def _normalize_language(language: str) -> str:
    value = str(language or "").strip().lower()

    if value.startswith("pl"):
        return "pl"

    return "en"