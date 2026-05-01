from __future__ import annotations

from pathlib import Path
import re


def test_command_grammar_does_not_use_short_language_enum_names() -> None:
    source = Path("modules/devices/audio/command_asr/command_grammar.py").read_text()

    assert re.search(r"\bCommandLanguage\.EN\b", source) is None
    assert re.search(r"\bCommandLanguage\.PL\b", source) is None
    assert "CommandLanguage.ENGLISH" in source
    assert "CommandLanguage.POLISH" in source
