from __future__ import annotations

import re

from modules.understanding.parsing.models import IntentResult
from modules.understanding.parsing.normalization import clean_text


class IntentParserMemoryMixin:
    def _parse_memory_recall(self, normalized: str) -> IntentResult | None:
        for pattern in (
            r"^(?:where are|where is) (?:my )?(.+)$",
            r"^where did i put (?:my )?(.+)$",
            r"^what do you remember about (.+)$",
            r"^do you remember (.+)$",
            r"^recall (.+)$",
            r"^remember (?:where|what) (.+)$",
            r"^gdzie (?:sa|jest) (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylem (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylam (?:moje |moj |moja )?(.+)$",
            r"^co pamietasz o (.+)$",
            r"^czy pamietasz (.+)$",
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
        prefixes = (
            "remember that ",
            "remember ",
            "zapamietaj ze ",
            "zapamietaj ",
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

        if not matched_prefix or not candidate:
            return None

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