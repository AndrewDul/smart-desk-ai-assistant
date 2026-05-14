from pathlib import Path

SYSTEM_ACTIONS_SOURCE = Path("modules/core/flows/action_flow/system_actions_mixin.py")


def test_ask_time_uses_numeric_only_spoken_template_for_fast_tts() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert 'spoken = now.strftime("%H %M")' in source
    assert 'spoken = f"{now.strftime' not in source
    assert "strftime('%H %M')}." not in source
    assert 'f"Jest {now.strftime' not in source
    assert 'f"It is {now.strftime' not in source


def test_introduce_self_uses_premium_ai_raspberry_pi_template() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert "Jestem asystentem wykorzystującym AI" in source
    assert "stworzonym na Raspberry Pi 5" in source
    assert "I am an AI-powered assistant" in source
    assert "built on a Raspberry Pi 5" in source


def test_help_uses_full_builtin_capability_guide() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert "focus mode" in source
    assert "break mode" in source
    assert "spójrz na mnie" in source
    assert "look at me" in source
    assert "feedback on" in source
    assert "ile to jest dwa plus dwa" in source
    assert "calculate two plus two" in source


def test_ask_time_spoken_template_has_no_terminal_pause() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert 'spoken = now.strftime("%H %M")' in source
    assert 'spoken = f"{now.strftime' not in source
    assert 'spoken = now.strftime("%H %M.")' not in source
    assert "strftime('%H %M')}." not in source


def test_identity_and_help_templates_do_not_speak_wake_word_triggers() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert "powiedz: NeXa" not in source
    assert "powiedz: Nexa" not in source
    assert "say: NeXa" not in source
    assert "say: Nexa" not in source
    assert "full NeXa screen" not in source
    assert "pełnego ekranu NeXa" not in source
