from __future__ import annotations


class TextVoiceInput:
    def listen(self) -> str:
        try:
            return input("You> ").strip()
        except EOFError:
            return ""
