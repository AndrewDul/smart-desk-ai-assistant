from __future__ import annotations

from modules.core.session.fast_command_lane import FastCommandLane


class FakeAssistant:
    pending_confirmation = None
    pending_follow_up = None

    @staticmethod
    def _normalize_lang(language: str | None) -> str:
        return "pl" if str(language or "").lower().startswith("pl") else "en"


def _classify(text: str, *, parser_action: str | None = None, language: str = "en"):
    prepared = {
        "raw_text": text,
        "routing_text": text,
        "normalized_text": text.lower().strip("."),
        "language": language,
    }
    if parser_action is not None:
        prepared["parser_result"] = {
            "action": parser_action,
            "confidence": 1.0,
            "payload": {},
        }
    return FastCommandLane(enabled=True).classify(prepared=prepared, assistant=FakeAssistant())


def test_show_system_status_wins_over_old_status_parser_result() -> None:
    decision = _classify("Show system status.", parser_action="status")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.source == "fast_command_lane:diagnostics_alias"
    assert decision.language == "en"


def test_system_status_opens_diagnostics() -> None:
    decision = _classify("system status", parser_action="status")

    assert decision is not None
    assert decision.action == "feedback_on"


def test_plain_status_can_remain_old_status() -> None:
    decision = _classify("status", parser_action="status")

    assert decision is not None
    assert decision.action == "status"


def test_polish_system_status_opens_diagnostics_in_polish() -> None:
    decision = _classify("pokaż status systemu", parser_action="status", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


# --- Close / hide diagnostics aliases ----------------------------------------


def test_close_system_status_routes_to_feedback_off() -> None:
    decision = _classify("close system status")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.source == "fast_command_lane:diagnostics_close_alias"


def test_close_diagnostics_routes_to_feedback_off() -> None:
    decision = _classify("close diagnostics")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.source == "fast_command_lane:diagnostics_close_alias"


def test_hide_diagnostics_routes_to_feedback_off() -> None:
    decision = _classify("hide diagnostics")

    assert decision is not None
    assert decision.action == "feedback_off"


def test_close_the_window_routes_to_feedback_off() -> None:
    decision = _classify("close the window")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.source == "fast_command_lane:diagnostics_close_alias"


def test_close_the_window_does_not_route_to_exit() -> None:
    decision = _classify("close the window")

    assert decision is not None
    assert decision.action != "exit"
    assert decision.action != "shutdown"


def test_exit_diagnostics_routes_to_feedback_off_not_exit() -> None:
    decision = _classify("exit diagnostics")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.action != "exit"


def test_zamknij_diagnostyke_routes_to_feedback_off() -> None:
    decision = _classify("zamknij diagnostykę", language="pl")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.language == "pl"


def test_zamknij_okno_routes_to_feedback_off() -> None:
    decision = _classify("zamknij okno", language="pl")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.language == "pl"


def test_zamknij_okno_does_not_route_to_exit() -> None:
    decision = _classify("zamknij okno", language="pl")

    assert decision is not None
    assert decision.action != "exit"
    assert decision.action != "shutdown"


def test_wyjdz_z_diagnostyki_routes_to_feedback_off() -> None:
    decision = _classify("wyjdź z diagnostyki", language="pl")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.language == "pl"


def test_wyjdz_z_diagnostyki_does_not_route_to_exit() -> None:
    decision = _classify("wyjdź z diagnostyki", language="pl")

    assert decision is not None
    assert decision.action != "exit"
    assert decision.action != "shutdown"


def test_feedback_mode_off_still_routes_to_feedback_off() -> None:
    decision = _classify("feedback mode off")

    assert decision is not None
    assert decision.action == "feedback_off"


def test_close_aliases_not_routed_to_llm() -> None:
    for phrase in (
        "close system status",
        "close diagnostics",
        "close the window",
        "hide diagnostics",
        "zamknij diagnostykę",
        "zamknij okno",
        "wyjdź z diagnostyki",
        "exit diagnostics",
    ):
        decision = _classify(phrase)
        assert decision is not None, f"Expected fast-lane decision for: {phrase!r}"
        assert decision.action == "feedback_off", (
            f"Expected feedback_off for {phrase!r}, got {decision.action!r}"
        )


# --- Session 2: ASR mishear variants (feedback_on) ----------------------------


def test_shows_system_status_routes_to_feedback_on() -> None:
    """ASR mishear of 'show system status' ('shows' instead of 'show') must open diagnostics."""
    decision = _classify("Shows system status.", parser_action="status")

    assert decision is not None
    assert decision.action == "feedback_on"


def test_pokaz_diagnostyka_routes_to_feedback_on() -> None:
    decision = _classify("Pokaż Diagnostyka.", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_pokaz_diagnostike_routes_to_feedback_on() -> None:
    decision = _classify("pokaż diagnostikę.", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_polkaz_diagnostike_routes_to_feedback_on() -> None:
    """ASR mishear: 'Polkaż diagnostikę.' → feedback_on."""
    decision = _classify("Polkaż diagnostikę.", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_polkaz_diagnostyke_routes_to_feedback_on() -> None:
    decision = _classify("polkaz diagnostyke", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"


def test_plain_status_still_routes_to_status_not_feedback() -> None:
    """'status' alone must not open diagnostics — only full 'show system status' variants."""
    decision = _classify("status", parser_action="status")

    assert decision is not None
    assert decision.action == "status"


# --- Session 3: new ASR mishear aliases (Part C) ------------------------------


def test_pokaz_djagnostyka_routes_to_feedback_on() -> None:
    decision = _classify("pokaz djagnostyka", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_pokaz_djagnostyke_routes_to_feedback_on() -> None:
    decision = _classify("pokaz djagnostyke", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_pokaz_djagnostike_routes_to_feedback_on() -> None:
    decision = _classify("pokaz djagnostike", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_okaz_diagnostyka_routes_to_feedback_on() -> None:
    decision = _classify("okaz diagnostyka", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_okaze_diagnostyka_routes_to_feedback_on() -> None:
    decision = _classify("okaze diagnostyka", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_o_kasz_diagnostyke_routes_to_feedback_on() -> None:
    decision = _classify("o kasz diagnostyke", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_pokasz_logi_routes_to_feedback_on() -> None:
    decision = _classify("pokasz logi", language="pl")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "pl"


def test_open_diagnostic_routes_to_feedback_on() -> None:
    decision = _classify("open diagnostic")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "en"


def test_show_diagnostic_routes_to_feedback_on() -> None:
    decision = _classify("show diagnostic")

    assert decision is not None
    assert decision.action == "feedback_on"
    assert decision.language == "en"


def test_zamknij_diagnostyka_routes_to_feedback_off() -> None:
    decision = _classify("zamknij diagnostyka", language="pl")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.language == "pl"


def test_close_window_routes_to_feedback_off() -> None:
    decision = _classify("close window")

    assert decision is not None
    assert decision.action == "feedback_off"


def test_close_diagnostic_routes_to_feedback_off() -> None:
    decision = _classify("close diagnostic")

    assert decision is not None
    assert decision.action == "feedback_off"


def test_hide_diagnostic_routes_to_feedback_off() -> None:
    decision = _classify("hide diagnostic")

    assert decision is not None
    assert decision.action == "feedback_off"


def test_klaus_system_status_routes_to_feedback_off() -> None:
    """ASR mishear: 'close system status' → 'Klaus system status' must close diagnostics."""
    decision = _classify("Klaus system status.")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.language == "en"


def test_claus_system_status_routes_to_feedback_off() -> None:
    """ASR mishear: 'close system status' → 'Claus system status' must close diagnostics."""
    decision = _classify("Claus system status.")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.language == "en"


# --- Session 4: new alias additions (Part C) ---------------------------------


def test_close_systems_routes_to_feedback_off() -> None:
    """ASR mishear: 'close system status' → 'Close systems.' must close diagnostics."""
    decision = _classify("Close systems.")

    assert decision is not None
    assert decision.action == "feedback_off"


def test_zamien_okno_routes_to_feedback_off() -> None:
    """ASR mishear: 'zamknij okno' → 'zamień okno' (normalized: 'zamien okno')."""
    decision = _classify("zamien okno", language="pl")

    assert decision is not None
    assert decision.action == "feedback_off"
    assert decision.language == "pl"


def test_or_almost_diagnostica_routes_to_feedback_on() -> None:
    """ASR creative mishear: 'or almost diagnostica' → open diagnostics."""
    decision = _classify("or almost diagnostica.")

    assert decision is not None
    assert decision.action == "feedback_on"


def test_all_cash_diagnostics_routes_to_feedback_on() -> None:
    """ASR creative mishear: 'all cash diagnostics' → open diagnostics."""
    decision = _classify("all cash diagnostics.")

    assert decision is not None
    assert decision.action == "feedback_on"
