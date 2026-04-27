from dataclasses import dataclass

from modules.presentation.visual_shell.controller import (
    VisualShellController,
    VisualShellVoiceCommandRouter,
    VisualVoiceAction,
)
from modules.presentation.visual_shell.service import BatteryReading, TemperatureReading
from modules.presentation.visual_shell.transport import InMemoryVisualShellTransport


@dataclass(slots=True)
class StubMetricsProvider:
    temperature: TemperatureReading | None = TemperatureReading(
        value_c=59,
        raw_value_c=58.95,
        source="stub",
    )
    battery: BatteryReading | None = BatteryReading(
        percent=82,
        source="stub",
    )

    def read_temperature(self) -> TemperatureReading | None:
        return self.temperature

    def read_battery(self) -> BatteryReading | None:
        return self.battery


def test_voice_router_matches_temperature_variants() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "temperatura",
        "jaka jest twoja temperatura",
        "czy jest ci za gorąco",
        "temperature",
        "are you hot",
    ]

    for text in examples:
        match = router.match(text)
        assert match is not None
        assert match.action == VisualVoiceAction.SHOW_TEMPERATURE


def test_voice_router_does_not_match_loose_temp_inside_unrelated_phrase() -> None:
    router = VisualShellVoiceCommandRouter()

    match = router.match("jak zrobić template w pythonie")

    assert match is None


def test_voice_router_matches_battery_variants() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "bateria",
        "ile masz baterii",
        "twoja bateria",
        "czy jesteś zmęczony",
        "battery",
        "are you tired",
    ]

    for text in examples:
        match = router.match(text)
        assert match is not None
        assert match.action == VisualVoiceAction.SHOW_BATTERY


def test_voice_router_matches_show_desktop_variants() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "pulpit",
        "daj pulpit",
        "gdzie mój pulpit",
        "show desktop",
        "desktop",
        "daj dostęp do komputera",
        "daj dostęp do linuxa",
        "pokaż ikony",
        "zdejmij shell",
        "chcę zobaczyć pulpit",
    ]

    for text in examples:
        match = router.match(text)
        assert match is not None
        assert match.action == VisualVoiceAction.SHOW_DESKTOP


def test_voice_router_recovers_common_show_desktop_stt_errors() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "pokaż polpit",
        "pokaz polpit",
        "pokaż pulpid",
        "pokaz pulbid",
        "on cashpour pit",
        "cash pour pit",
        "cash for beat",
        "or cash for beat",
    ]

    for text in examples:
        match = router.match(text)
        assert match is not None, text
        assert match.action == VisualVoiceAction.SHOW_DESKTOP
        assert "pulpit" in match.normalized_text


def test_voice_router_recovers_real_runtime_show_desktop_captures() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        ("die dos temp do linux", "daj dostep do linuxa"),
        ("daj dosy ten dolinów", "daj dostep do linuxa"),
        ("pokaż i konie", "pokaz ikony"),
        ("pokaż u lp", "pokaz pulpit"),
        ("or cars", "pokaz pulpit"),
    ]

    for text, expected_normalized in examples:
        match = router.match(text)
        assert match is not None, text
        assert match.action == VisualVoiceAction.SHOW_DESKTOP
        assert match.normalized_text == expected_normalized


def test_voice_router_does_not_map_too_generic_show_it_phrase_to_desktop() -> None:
    router = VisualShellVoiceCommandRouter()

    match = router.match("pokaż to")

    assert match is None


def test_voice_router_recovers_common_hide_desktop_stt_errors() -> None:
    router = VisualShellVoiceCommandRouter()

    stt_rescue_examples = [
        "schowaj polpit",
        "schowaj pulpid",
        "schowaj pulbit",
        "zchowaj pul bit",
        "schowaj pul bit",
        "z chowaj pul bit",
        "skawaj pulbit",
        "skawaj pul bit",
        "słowaj pul bit",
        "slowaj pulbit",
        "slowaj pul bit",
        "sko wej pulpit",
        "sko wej pul bit",
        "sko wej pulbit",
        "słuchaj pulpit",
        "sluchaj pulpit",
        "sluchaj pul bit",
        "skołwaj u lbid",
        "skolwaj u lbid",
        "skolwaj ulbid",
    ]

    for text in stt_rescue_examples:
        match = router.match(text)
        assert match is not None, text
        assert match.action == VisualVoiceAction.HIDE_DESKTOP
        assert match.normalized_text == "schowaj pulpit"

    semantic_variant_examples = [
        "ukryj polpit",
    ]

    for text in semantic_variant_examples:
        match = router.match(text)
        assert match is not None, text
        assert match.action == VisualVoiceAction.HIDE_DESKTOP
        assert match.normalized_text == "ukryj pulpit"


def test_voice_router_does_not_capture_conceptual_desktop_questions() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "co to jest pulpit",
        "czym jest pulpit w linuxie",
        "wyjaśnij pulpit w systemie operacyjnym",
        "what is desktop",
        "explain desktop in linux",
    ]

    for text in examples:
        match = router.match(text)
        assert match is None, text


def test_voice_router_matches_hide_desktop_variants_before_generic_desktop() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "schowaj pulpit",
        "nie chcę pulpitu",
        "już nie potrzebuję pulpitu",
        "hide desktop",
        "no desktop",
    ]

    for text in examples:
        match = router.match(text)
        assert match is not None
        assert match.action == VisualVoiceAction.HIDE_DESKTOP


def test_voice_router_distinguishes_look_at_user_from_scanning() -> None:
    router = VisualShellVoiceCommandRouter()

    calm_eye_examples = [
        "spójrz na mnie",
        "patrz na mnie",
        "look at me",
    ]

    scanning_examples = [
        "sprawdź pokój",
        "sprawdź biurko",
        "rozejrzyj się",
        "co widzisz",
        "look around",
        "check room",
        "find my phone",
    ]

    for text in calm_eye_examples:
        match = router.match(text)
        assert match is not None
        assert match.action == VisualVoiceAction.LOOK_AT_USER

    for text in scanning_examples:
        match = router.match(text)
        assert match is not None
        assert match.action == VisualVoiceAction.START_SCANNING


def test_controller_handles_voice_temperature_with_real_metric_action() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(
        transport=transport,
        metrics_provider=StubMetricsProvider(),
    )

    result = controller.handle_voice_text("czy jest ci za gorąco")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_TEMPERATURE",
            "payload": {"value_c": 59},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_handles_voice_battery_with_real_metric_action() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(
        transport=transport,
        metrics_provider=StubMetricsProvider(),
    )

    result = controller.handle_voice_text("czy jesteś zmęczony")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_BATTERY",
            "payload": {"percent": 82},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_reports_degraded_when_voice_battery_is_unavailable() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(
        transport=transport,
        metrics_provider=StubMetricsProvider(battery=None),
    )

    result = controller.handle_voice_text("ile masz baterii")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "REPORT_DEGRADED",
            "payload": {"reason": "battery_unavailable"},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_handles_show_desktop_voice_command() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("gdzie mój pulpit")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_DESKTOP",
            "payload": {},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_handles_show_desktop_stt_rescue_voice_command() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("pokaż polpit")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_DESKTOP",
            "payload": {},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_handles_real_runtime_show_desktop_stt_rescue_voice_command() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("die dos temp do linux")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_DESKTOP",
            "payload": {},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_handles_hide_desktop_voice_command() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("już nie potrzebuję pulpitu")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "HIDE_DESKTOP",
            "payload": {},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_show_self_hides_desktop_before_showing_self() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("pokaż się")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "HIDE_DESKTOP",
            "payload": {},
            "source": "nexa-voice-builtins",
        },
        {
            "command": "SHOW_SELF",
            "payload": {},
            "source": "nexa-voice-builtins",
        },
    ]


def test_controller_look_at_user_uses_calm_eyes_without_hiding_desktop() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("spójrz na mnie")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_EYES",
            "payload": {},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_scanning_command_uses_scanning_eyes() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("sprawdź biurko")

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "START_SCANNING",
            "payload": {},
            "source": "nexa-voice-builtins",
        }
    ]


def test_controller_returns_false_for_unknown_voice_command() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_text("to jest zwykła rozmowa bez komendy")

    assert result is False
    assert transport.sent_messages == []


def test_voice_router_does_not_show_desktop_from_bare_pulpit_substring() -> None:
    router = VisualShellVoiceCommandRouter()

    false_positive_examples = [
        "sluchaj pulpit",
        "slawaj pulpit",
        "random pulpit words",
    ]

    for text in false_positive_examples:
        match = router.match(text)
        if text in {"sluchaj pulpit", "slawaj pulpit"}:
            assert match is not None, text
            assert match.action == VisualVoiceAction.HIDE_DESKTOP
            assert match.normalized_text == "schowaj pulpit"
        else:
            assert match is None, text


def test_voice_router_recovers_english_like_hide_desktop_stt_errors() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "So why pull bit?",
        "So why pul bit?",
        "So bye, cool bit.",
        "So bye pull bit.",
        "Skoławaj Pol bit.",
        "Sławaj pulpit.",
    ]

    for text in examples:
        match = router.match(text)
        assert match is not None, text
        assert match.action == VisualVoiceAction.HIDE_DESKTOP
        assert match.normalized_text == "schowaj pulpit"


def test_voice_router_supports_short_english_hide_command() -> None:
    router = VisualShellVoiceCommandRouter()

    match = router.match("Hide.")
    assert match is not None
    assert match.action == VisualVoiceAction.HIDE_DESKTOP
    assert match.matched_rule == "hide_desktop"

    assert router.match("Hi.") is None


def test_voice_router_recovers_show_desktop_english_spacing_errors() -> None:
    router = VisualShellVoiceCommandRouter()

    examples = [
        "Show Desk Top.",
        "show desk top",
        "show desktop",
        "Szał do skto.",
    ]

    for text in examples:
        match = router.match(text)
        assert match is not None, text
        assert match.action == VisualVoiceAction.SHOW_DESKTOP
        assert match.matched_rule == "show_desktop"


def test_voice_router_recovers_scott_viper_pit_as_hide_desktop() -> None:
    router = VisualShellVoiceCommandRouter()

    match = router.match("Scott Viper Pit")
    assert match is not None
    assert match.action == VisualVoiceAction.HIDE_DESKTOP
    assert match.matched_rule == "hide_desktop"
    assert match.normalized_text == "schowaj pulpit"