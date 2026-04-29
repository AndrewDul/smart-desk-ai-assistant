from pathlib import Path

SYSTEM_ACTIONS_SOURCE = Path("modules/core/flows/action_flow/system_actions_mixin.py")


def test_ask_time_uses_numeric_only_spoken_template_for_fast_tts() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert 'spoken = now.strftime("%H %M")' in source
    assert 'spoken = f"{now.strftime' not in source
    assert "strftime('%H %M')}." not in source
    assert 'f"Jest {now.strftime' not in source
    assert 'f"It is {now.strftime' not in source


def test_introduce_self_uses_short_spoken_template_for_fast_tts() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert '"Nazywam się NeXa."' in source
    assert '"My name is NeXa."' in source
    assert "Jestem lokalnym asystentem biurkowym" not in source
    assert "I am a local desk assistant running on Raspberry Pi." not in source


def test_ask_time_spoken_template_has_no_terminal_pause() -> None:
    source = SYSTEM_ACTIONS_SOURCE.read_text(encoding="utf-8")

    assert 'spoken = now.strftime("%H %M")' in source
    assert 'spoken = f"{now.strftime' not in source
    assert 'spoken = now.strftime("%H %M.")' not in source
    assert "strftime('%H %M')}." not in source
