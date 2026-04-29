from pathlib import Path


def test_introduce_self_uses_short_command_safe_templates() -> None:
    source = Path("modules/core/flows/action_flow/system_actions_mixin.py").read_text(
        encoding="utf-8"
    )

    assert '"Nazywam się NeXa."' in source
    assert '"My name is NeXa."' in source
    assert "Jestem lokalnym asystentem biurkowym działającym na Raspberry Pi." not in source
    assert "I am a local desk assistant running on Raspberry Pi." not in source
