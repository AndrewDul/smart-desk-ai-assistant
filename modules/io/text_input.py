from __future__ import annotations


class TextInput:
    def __init__(self) -> None:
        pass

    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        try:
            text = input("You> ").strip()
        except EOFError:
            return None
        except KeyboardInterrupt:
            raise

        return text or None