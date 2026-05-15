from __future__ import annotations

import re

from modules.understanding.parsing.models import IntentResult
from modules.understanding.parsing.normalization import clean_text


class IntentParserMemoryMixin:
    def _parse_memory_recall(self, normalized: str) -> IntentResult | None:
        direct_recall_queries = {
            "jakie obiekty znasz",
            "jakie rzeczy znasz",
            "pokaz zapamietane obiekty",
            "pokaż zapamiętane obiekty",
            "what objects do you know",
            "show known objects",
        }
        if normalized in direct_recall_queries:
            return IntentResult.from_action(
                action="memory_recall",
                data={"key": normalized},
            )

        for pattern in (
            r"^(?:where are|where is) (?:my |the )?(.+)$",
            r"^where did i put (?:my |the )?(.+)$",
            r"^where did i leave (?:my |the )?(.+)$",
            r"^remind me where (?:my |the )?(.+)$",
            r"^what do you remember about (.+)$",
            r"^do you remember where (?:my |the )?(.+)$",
            r"^do you remember (.+)$",
            r"^recall (.+)$",
            r"^remember (?:where|what) (.+)$",
            r"^gdzie (?:sa|jest) (?:moje |moj |moja )?(.+)$",
            r"^gdzie lezy (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylem (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylam (?:moje |moj |moja )?(.+)$",
            r"^przypomnij mi gdzie (?:jest )?(?:moje |moj |moja )?(.+)$",
            r"^przypomnij gdzie (?:jest )?(?:moje |moj |moja )?(.+)$",
            r"^pamietasz gdzie (?:jest )?(?:moje |moj |moja )?(.+)$",
            r"^co pamietasz o (.+)$",
            r"^czy pamietasz (?:gdzie jest )?(.+)$",
        ):
            match = re.match(pattern, normalized)
            if match:
                key = self._cleanup_subject(match.group(1))
                if key:
                    return IntentResult.from_action(
                        action="memory_recall",
                        data={"key": key},
                    )
        return None

    def _parse_memory_forget(self, normalized: str) -> IntentResult | None:
        for pattern in (
            r"^(?:forget|remove from memory|delete from memory)\s+(.+)$",
            r"^(?:forget|remove|delete)\s+(.+?)\s+from\s+memory$",
            r"^(?:zapomnij o|usun z pamieci|skasuj z pamieci)\s+(.+)$",
            r"^(?:usun|skasuj)\s+(.+?)\s+z\s+pamieci$",
        ):
            match = re.match(pattern, normalized)
            if match:
                key = self._cleanup_subject(match.group(1))
                if key:
                    return IntentResult.from_action(
                        action="memory_forget",
                        data={"key": key},
                    )
        return None

    def _parse_memory_store(self, normalized: str) -> IntentResult | None:
        person_enrollment_triggers = {
            "remember me",
            "save me",
            "save me to memory",
            "zapamietaj mnie",
            "zapamiętaj mnie",
            "pamietaj mnie",
            "pamiętaj mnie",
        }
        if normalized in person_enrollment_triggers:
            return IntentResult.from_action(
                action="memory_store",
                data={"guided": True, "person_enrollment": True},
            )

        object_enrollment_triggers = {
            "remember this object": "object",
            "remember this thing": "object",
            "remember this phone": "phone",
            "save this object": "object",
            "save this thing": "object",
            "save this phone": "phone",
            "zapamietaj ten obiekt": "obiekt",
            "zapamiętaj ten obiekt": "obiekt",
            "zapamietaj te rzecz": "rzecz",
            "zapamiętaj tę rzecz": "rzecz",
            "zapamietaj ten telefon": "telefon",
            "zapamiętaj ten telefon": "telefon",
            "zapisz ten obiekt": "obiekt",
            "zapisz ten telefon": "telefon",
        }
        object_hint = object_enrollment_triggers.get(normalized)
        if object_hint:
            return IntentResult.from_action(
                action="memory_store",
                data={"guided": True, "object_enrollment": True, "object_hint": object_hint},
            )

        # Bare trigger words → enter guided mode immediately.
        # ("remember" alone, "zapamiętaj" alone, etc.)
        bare_triggers = {
            "remember",
            "save this",
            "save to memory",
            "zapamietaj",
            "zapamiętaj",
            "zapisz to",
            "zapisz w pamieci",
            "pamietaj",
            "pamiętaj",
        }
        if normalized in bare_triggers:
            return IntentResult.from_action(
                action="memory_store",
                data={"guided": True},
            )

        prefixes = (
            "remember that ",
            "remember ",
            "save that ",
            "save ",
            "zapamietaj ze ",
            "zapamietaj ",
            "zapisz ze ",
            "zapisz ",
            "pamietaj ze ",
            "pamietaj ",
        )

        candidate = normalized
        matched_prefix = False

        for prefix in prefixes:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):].strip()
                matched_prefix = True
                break

        if not matched_prefix:
            return None

        # Trigger-only residues (pronouns / fillers) → guided mode.
        # After stripping "remember " from "remember it" we get "it";
        # after stripping "zapamietaj " from "zapamietaj to" we get "to".
        # These are not real memory contents, they ask NeXa to start
        # guided capture.
        guided_residues = {
            "",
            "co",
            "cos",
            "coś",
            "to",
            "this",
            "that",
            "it",
            "something",
            "anything",
        }
        if candidate in guided_residues:
            return IntentResult.from_action(
                action="memory_store",
                data={"guided": True},
            )

        for pattern in (
            r"^(.+?)\s+(?:is|are|jest|sa)\s+(.+)$",
        ):
            match = re.match(pattern, candidate)
            if match:
                subject = self._cleanup_subject(match.group(1))
                predicate = clean_text(match.group(2))
                if subject and predicate:
                    return IntentResult.from_action(
                        action="memory_store",
                        data={
                            "key": subject,
                            "value": predicate,
                            "memory_text": candidate,
                        },
                    )

        location_markers = (
            " in ",
            " on ",
            " at ",
            " under ",
            " inside ",
            " beside ",
            " near ",
            " obok ",
            " w ",
            " na ",
            " pod ",
            " przy ",
        )
        for marker in location_markers:
            if marker in candidate:
                left, right = candidate.split(marker, 1)
                subject = self._cleanup_subject(left)
                predicate = clean_text(f"{marker.strip()} {right}")
                if subject and right.strip():
                    return IntentResult.from_action(
                        action="memory_store",
                        data={
                            "key": subject,
                            "value": predicate,
                            "memory_text": candidate,
                        },
                    )

        return IntentResult.from_action(
            action="memory_store",
            data={"memory_text": candidate},
        )