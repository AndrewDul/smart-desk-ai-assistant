from __future__ import annotations

import re

from modules.understanding.parsing.models import IntentResult
from modules.understanding.parsing.normalization import clean_text


class IntentParserMemoryMixin:
    _MEMORY_FORGET_TYPE_PREFIXES = {
        "person": "person",
        "object": "object",
        "osoba": "person",
        "osobe": "person",
        "osobę": "person",
        "obiekt": "object",
    }

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
            r"^(?:forget)\s+(.+)$",
            r"^(?:remove|delete)\s+(.+?)\s+from\s+memory$",
            r"^(?:remove|delete)\s+(person|object)\s+(.+?)\s+from\s+memory$",
            r"^(?:forget|remove from memory|delete from memory)\s+(.+)$",
            r"^(?:zapomnij|zapomnij o)\s+(.+)$",
            r"^(?:usun|usuń|skasuj|wykasuj)\s+(.+?)\s+z\s+(?:pamieci|pamięci)$",
            r"^(?:usun z pamieci|usuń z pamięci|skasuj z pamieci|skasuj z pamięci)\s+(.+)$",
        ):
            match = re.match(pattern, normalized)
            if match:
                groups = [group for group in match.groups() if group is not None]
                explicit_type = ""
                raw_key = groups[-1] if groups else ""
                if len(groups) > 1:
                    explicit_type = self._MEMORY_FORGET_TYPE_PREFIXES.get(groups[0], "")

                key, inferred_type = self._cleanup_memory_forget_target(raw_key)
                entity_type = explicit_type or inferred_type
                if key:
                    data = {"key": key}
                    if entity_type:
                        data["entity_type"] = entity_type
                    return IntentResult.from_action(
                        action="memory_forget",
                        data=data,
                    )
        return None

    def _cleanup_memory_forget_target(self, text: str) -> tuple[str, str]:
        key = self._cleanup_subject(text)
        if key.startswith("o "):
            key = key[2:].strip()
        entity_type = ""
        changed = True
        while changed and key:
            changed = False
            parts = key.split(maxsplit=1)
            if not parts:
                break
            mapped_type = self._MEMORY_FORGET_TYPE_PREFIXES.get(parts[0])
            if mapped_type and len(parts) > 1:
                entity_type = entity_type or mapped_type
                key = parts[1].strip()
                changed = True
        return key, entity_type


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
