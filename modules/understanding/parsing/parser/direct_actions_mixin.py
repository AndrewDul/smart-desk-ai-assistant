from __future__ import annotations

from modules.understanding.parsing.models import IntentResult


class IntentParserDirectActionsMixin:
    def _parse_direct_action(self, normalized: str) -> IntentResult | None:
        direct = self.direct_action_map.get(normalized)
        if direct:
            return IntentResult.from_action(action=direct)

        tokens = set(normalized.split())
        if not tokens:
            return None

        if {"jak", "mozesz", "mi", "pomoc"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"w", "czym", "mozesz", "mi", "pomoc"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"co", "potrafisz"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"how", "can", "you", "help", "me"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"what", "can", "you", "do"}.issubset(tokens):
            return IntentResult.from_action(action="help")

        if "status" in tokens or ("stan" in tokens and "systemu" in tokens):
            return IntentResult.from_action(action="status")

        if {"jak", "sie", "nazywasz"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")
        if {"kim", "jestes"}.issubset(tokens) or {"czym", "jestes"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")
        if {"what", "is", "your", "name"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")
        if {"who", "are", "you"}.issubset(tokens) or {"what", "are", "you"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")

        assistant_target = self._mentions_assistant_target(tokens)
        system_target = self._mentions_system_target(tokens)
        off_or_close = self._mentions_off_or_close(tokens)

        if assistant_target and off_or_close:
            return IntentResult.from_action(action="exit")
        if {"idz", "spac"}.issubset(tokens) or "odpocznij" in tokens or "spij" in tokens:
            return IntentResult.from_action(action="exit")
        if {"go", "to", "sleep"}.issubset(tokens) or {"stop", "listening"}.issubset(tokens):
            return IntentResult.from_action(action="exit")

        if system_target and off_or_close:
            return IntentResult.from_action(action="shutdown")
        if "shutdown" in tokens or ({"shut", "down"}.issubset(tokens) and system_target):
            return IntentResult.from_action(action="shutdown")

        if {"power", "off"}.issubset(tokens):
            if assistant_target and not system_target:
                return IntentResult.from_action(action="exit")
            return IntentResult.from_action(action="shutdown")

        return None