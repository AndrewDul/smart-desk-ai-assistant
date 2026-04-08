from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from modules.shared.logging.logger import append_log
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import MEMORY_PATH


@dataclass(slots=True)
class MemoryMatch:
    key: str
    value: str
    score: float
    exact: bool = False
    normalized_query: str = ""
    normalized_key: str = ""


class MemoryService:
    """
    Persistent lightweight memory for NeXa.

    Responsibilities:
    - store key/value memory items safely
    - recall memory by exact or fuzzy match
    - normalize common Polish/English variations
    - keep the API tiny and stable for action_flow

    Public API intentionally mirrors the old service where useful:
    - remember(key, value)
    - recall(key)
    - forget(key)
    - clear()
    - get_all()
    """

    def __init__(self, store: JsonStore[dict[str, str]] | None = None) -> None:
        self.store = store or JsonStore(
            path=MEMORY_PATH,
            default_factory=dict,
        )
        self.store.ensure_exists()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def remember(self, key: str, value: str) -> None:
        key_clean = self._clean_text(key)
        value_clean = self._clean_text(value)

        if not key_clean or not value_clean:
            append_log("Memory save skipped: empty key or value.")
            return

        memory_data = self._load_memory()
        existing_key = self._find_existing_storage_key(memory_data, key_clean)
        target_key = existing_key if existing_key else key_clean

        memory_data[target_key] = value_clean
        self._save_memory(memory_data)

        append_log(f"Memory saved: {target_key} -> {value_clean}")

    def recall(self, key: str) -> str | None:
        match = self.match(key)
        if match is None:
            return None

        query_clean = self._clean_text(key)
        if query_clean and query_clean != match.key:
            append_log(
                f"Memory recall matched '{query_clean}' -> '{match.key}' "
                f"(score={match.score:.2f})"
            )

        return match.value

    def forget(self, key: str) -> tuple[str | None, str | None]:
        memory_data = self._load_memory()
        if not memory_data:
            return None, None

        match = self._find_matching_storage_key(memory_data, key)
        if match is None:
            return None, None

        removed_value = memory_data.pop(match.key, None)
        self._save_memory(memory_data)

        append_log(f"Memory deleted: {match.key}")
        return match.key, removed_value

    def clear(self) -> int:
        memory_data = self._load_memory()
        count = len(memory_data)
        self._save_memory({})
        append_log(f"Memory cleared: removed {count} item(s).")
        return count

    def get_all(self) -> dict[str, str]:
        return self._load_memory()

    def has_any(self) -> bool:
        return bool(self._load_memory())

    def count(self) -> int:
        return len(self._load_memory())

    def match(self, key: str) -> MemoryMatch | None:
        memory_data = self._load_memory()
        if not memory_data:
            return None
        return self._find_matching_storage_key(memory_data, key)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_memory(self) -> dict[str, str]:
        data = self.store.read()
        if not isinstance(data, dict):
            return {}

        clean_data: dict[str, str] = {}
        for key, value in data.items():
            key_text = self._clean_text(str(key))
            value_text = self._clean_text(str(value))
            if key_text and value_text:
                clean_data[key_text] = value_text

        return clean_data

    def _save_memory(self, data: dict[str, str]) -> None:
        normalized: dict[str, str] = {}
        for key, value in data.items():
            key_text = self._clean_text(str(key))
            value_text = self._clean_text(str(value))
            if key_text and value_text:
                normalized[key_text] = value_text

        self.store.write(normalized)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _find_matching_storage_key(
        self,
        memory_data: dict[str, str],
        query: str,
    ) -> MemoryMatch | None:
        query_clean = self._clean_text(query)
        if not query_clean:
            return None

        if query_clean in memory_data:
            return MemoryMatch(
                key=query_clean,
                value=memory_data[query_clean],
                score=1.0,
                exact=True,
                normalized_query=self._normalize_key(query_clean),
                normalized_key=self._normalize_key(query_clean),
            )

        normalized_query = self._normalize_key(query_clean)

        for stored_key, stored_value in memory_data.items():
            normalized_stored = self._normalize_key(stored_key)
            if normalized_stored == normalized_query:
                return MemoryMatch(
                    key=stored_key,
                    value=stored_value,
                    score=0.99,
                    exact=False,
                    normalized_query=normalized_query,
                    normalized_key=normalized_stored,
                )

        return self._find_best_match(memory_data, query_clean)

    def _find_existing_storage_key(
        self,
        memory_data: dict[str, str],
        new_key: str,
    ) -> str | None:
        normalized_new_key = self._normalize_key(new_key)

        for stored_key in memory_data.keys():
            if self._normalize_key(stored_key) == normalized_new_key:
                return stored_key

        return None

    def _find_best_match(
        self,
        memory_data: dict[str, str],
        query: str,
    ) -> MemoryMatch | None:
        normalized_query = self._normalize_key(query)
        query_tokens = self._tokenize(normalized_query)

        best_match: MemoryMatch | None = None
        best_score = 0.0

        for stored_key, stored_value in memory_data.items():
            normalized_stored_key = self._normalize_key(stored_key)
            stored_tokens = self._tokenize(normalized_stored_key)

            if normalized_query in normalized_stored_key or normalized_stored_key in normalized_query:
                return MemoryMatch(
                    key=stored_key,
                    value=stored_value,
                    score=0.92,
                    exact=False,
                    normalized_query=normalized_query,
                    normalized_key=normalized_stored_key,
                )

            overlap_score = self._token_overlap_score(query_tokens, stored_tokens)
            similarity_score = SequenceMatcher(None, normalized_query, normalized_stored_key).ratio()

            combined_score = max(overlap_score, similarity_score)

            if combined_score > best_score:
                best_score = combined_score
                best_match = MemoryMatch(
                    key=stored_key,
                    value=stored_value,
                    score=combined_score,
                    exact=False,
                    normalized_query=normalized_query,
                    normalized_key=normalized_stored_key,
                )

        if best_match is not None and best_score >= 0.58:
            return best_match

        return None

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _token_overlap_score(left_tokens: list[str], right_tokens: list[str]) -> float:
        if not left_tokens or not right_tokens:
            return 0.0

        left_set = set(left_tokens)
        right_set = set(right_tokens)
        common = left_set & right_set

        if not common:
            return 0.0

        return float(len(common) / max(len(left_set), len(right_set)))

    def _normalize_key(self, text: str) -> str:
        normalized = self._clean_text(text)
        normalized = self._strip_leading_fillers(normalized)
        normalized = self._strip_trailing_fillers(normalized)
        normalized = self._singularize_last_token(normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _clean_text(self, text: str) -> str:
        lowered = str(text or "").lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _strip_leading_fillers(text: str) -> str:
        fillers = [
            "my ",
            "moje ",
            "moj ",
            "moja ",
            "numer ",
            "number ",
            "the ",
            "a ",
            "an ",
        ]

        result = text
        changed = True

        while changed:
            changed = False
            for filler in fillers:
                if result.startswith(filler):
                    result = result[len(filler) :].strip()
                    changed = True

        return result

    @staticmethod
    def _strip_trailing_fillers(text: str) -> str:
        fillers = [
            " prosze",
            " please",
        ]

        result = text
        changed = True

        while changed:
            changed = False
            for filler in fillers:
                if result.endswith(filler):
                    result = result[: -len(filler)].strip()
                    changed = True

        return result

    @staticmethod
    def _singularize_last_token(text: str) -> str:
        tokens = text.split()
        if not tokens:
            return text

        last = tokens[-1]

        english_irregular = {
            "keys": "key",
            "glasses": "glasses",
            "phones": "phone",
            "numbers": "number",
        }
        polish_irregular = {
            "klucze": "klucz",
            "okulary": "okulary",
            "telefony": "telefon",
        }

        if last in english_irregular:
            tokens[-1] = english_irregular[last]
            return " ".join(tokens)

        if last in polish_irregular:
            tokens[-1] = polish_irregular[last]
            return " ".join(tokens)

        if len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
            tokens[-1] = last[:-1]
            return " ".join(tokens)

        return " ".join(tokens)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in text.split() if token]


__all__ = [
    "MemoryMatch",
    "MemoryService",
]